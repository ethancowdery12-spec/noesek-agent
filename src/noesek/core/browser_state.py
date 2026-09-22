"""Persistent browser session state (roadmap item 56, Option A+B).

Cookie bytes are persistent secrets: they NEVER pass through chat, model
context, logs, or tool output. Imports arrive only at the dedicated
/computer/browser-state/import endpoint and go straight into the
Fernet-encrypted store. Every read path (status, audit, errors) exposes
domain names and counts only.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


class BrowserStateError(Exception):
    pass


def _fernet() -> Fernet:
    key = (settings.browser_state_key or "").strip()
    if not key:
        raise BrowserStateError("NOESEK_BROWSER_STATE_KEY is not set")
    derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    return Fernet(derived)


def encrypt_state(state: dict) -> str:
    return _fernet().encrypt(json.dumps(state).encode()).decode()


def decrypt_state(blob: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(blob.encode()).decode())
    except InvalidToken as exc:
        raise BrowserStateError("stored browser state is unreadable (wrong key?)") from exc


def parse_cookies_txt(text: str) -> list[dict]:
    """Netscape cookies.txt -> Playwright cookie dicts. Comments/blanks skipped."""
    cookies: list[dict] = []
    for line in (text or "").splitlines():
        line = line.rstrip("\n")
        http_only = line.startswith("#HttpOnly")
        if not line or (line.startswith("#") and not http_only):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            raise BrowserStateError("not a Netscape cookies.txt line (expected 7 tab fields)")
        domain, _flag, path, secure, expires, name, value = parts
        if http_only and domain.startswith("#HttpOnly_"):
            domain = domain[len("#HttpOnly_"):]
        cookie: dict = {"name": name, "value": value,
                        "domain": domain, "path": path or "/",
                        "secure": secure.upper() == "TRUE",
                        "httpOnly": http_only}
        try:
            exp = int(expires)
            if exp > 0:
                cookie["expires"] = exp
        except ValueError:
            pass
        cookies.append(cookie)
    if not cookies:
        raise BrowserStateError("no cookies found in the import text")
    return cookies


def parse_import(text: str) -> list[dict]:
    """Accept a cookies.txt export, a storage_state JSON, or a JSON cookie array."""
    text = (text or "").strip()
    if not text:
        raise BrowserStateError("empty import")
    if text.startswith("[") or text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("cookies", [])
        if not isinstance(data, list) or not all(isinstance(c, dict) and "name" in c for c in data):
            raise BrowserStateError("JSON import must be a storage_state or a cookie array")
        if not data:
            raise BrowserStateError("no cookies found in the import text")
        return data
    return parse_cookies_txt(text)


def _norm(domain: str) -> str:
    return (domain or "").lstrip(".").lower()


def cookie_domain(cookie: dict) -> str:
    return _norm(cookie.get("domain", ""))


def session_summary(state: dict) -> dict:
    """Domain names and counts only - never cookie names or values."""
    domains = sorted({cookie_domain(c) for c in state.get("cookies", [])} - {""})
    enabled = sorted(state.get("enabled", []))
    return {"domains": domains, "cookie_count": len(state.get("cookies", [])),
            "origin_count": len(state.get("origins", [])),
            "enabled": enabled, "pending": [d for d in domains if d not in enabled]}


def merge_import(state: dict, cookies: list[dict]) -> list[str]:
    """Merge imported cookies (replace on name+domain+path). New domains stay
    DISABLED until explicitly enabled. Returns domains present in the import."""
    key = lambda c: (c.get("name"), (c.get("domain") or "").lower(), c.get("path", "/"))
    merged = {key(c): c for c in state.get("cookies", [])}
    for c in cookies:
        merged[key(c)] = c
    state["cookies"] = list(merged.values())
    state.setdefault("enabled", [])
    return sorted({cookie_domain(c) for c in cookies} - {""})


def set_enabled(state: dict, domain: str, flag: bool) -> bool:
    """Enable/disable a stored domain. Returns False if the domain is not stored."""
    d = _norm(domain)
    domains = {cookie_domain(c) for c in state.get("cookies", [])}
    if d not in domains:
        return False
    enabled = set(state.get("enabled", []))
    enabled.discard(d)
    if flag:
        enabled.add(d)
    state["enabled"] = sorted(enabled)
    return True


def revoke_domain(state: dict, domain: str) -> int:
    """Delete every cookie/origin for a domain and drop its enablement."""
    d = _norm(domain)
    before = len(state.get("cookies", []))
    state["cookies"] = [c for c in state.get("cookies", []) if cookie_domain(c) != d]
    state["origins"] = [o for o in state.get("origins", []) if d not in _norm(o.get("origin", ""))]
    state["enabled"] = [e for e in state.get("enabled", []) if e != d]
    return before - len(state["cookies"])


def state_for_origin(state: dict, origin: str) -> dict:
    """Cookies/origins to restore for a browse run: ENABLED domains matching the
    plan origin only. Approval-before-use is the enable action; nothing else
    leaves the store."""
    host = _norm(origin.split("://")[-1].split("/")[0])
    enabled = set(state.get("enabled", []))
    cookies = [c for c in state.get("cookies", [])
               if cookie_domain(c) in enabled and (host == cookie_domain(c) or host.endswith("." + cookie_domain(c)))]
    origins = [o for o in state.get("origins", []) if _norm(o.get("origin", "").split("://")[-1]) in enabled
               and (host == _norm(o.get("origin", "").split("://")[-1]) or host.endswith("." + _norm(o.get("origin", "").split("://")[-1])))]
    return {"cookies": cookies, "origins": origins}


def merge_export(state: dict, exported: dict, origin: str) -> dict:
    """Fold a post-run storage_state export back in: cookies for the visited
    origin are replaced by the export; other domains are preserved. Enablement
    flags survive. Domains the run touched stay at their current enablement -
    a run cannot silently enable new domains."""
    host = _norm(origin.split("://")[-1].split("/")[0])
    key = lambda c: (c.get("name"), (c.get("domain") or "").lower(), c.get("path", "/"))
    keep = {key(c): c for c in state.get("cookies", [])
            if not (host == cookie_domain(c) or host.endswith("." + cookie_domain(c)))}
    for c in exported.get("cookies", []):
        keep[key(c)] = c
    state["cookies"] = list(keep.values())
    old_origins = [o for o in state.get("origins", []) if host not in _norm(o.get("origin", ""))]
    state["origins"] = old_origins + [o for o in exported.get("origins", [])]
    return state


async def save_state(state: dict) -> None:
    from sqlalchemy import select
    from ..db import BrowserStateRow, Session
    blob = encrypt_state(state)
    async with Session() as s:
        row = (await s.execute(select(BrowserStateRow).where(BrowserStateRow.id == 1))).scalar_one_or_none()
        if row is None:
            s.add(BrowserStateRow(id=1, blob=blob))
        else:
            row.blob = blob
        await s.commit()


async def load_state() -> dict | None:
    from sqlalchemy import select
    from ..db import BrowserStateRow, Session
    async with Session() as s:
        row = (await s.execute(select(BrowserStateRow).where(BrowserStateRow.id == 1))).scalar_one_or_none()
    if row is None:
        return None
    return decrypt_state(row.blob)


async def audit(action: str, domain: str = "", detail: str = "") -> None:
    """Best-effort audit append. Callers pass domains/counts only - never values."""
    from ..db import BrowserAuditRow, Session
    try:
        async with Session() as s:
            s.add(BrowserAuditRow(action=action[:32], domain=_norm(domain)[:255], detail=detail[:255]))
            await s.commit()
    except Exception:
        pass  # auditing must never break a browse run


async def audit_log(limit: int = 50) -> list[dict]:
    from sqlalchemy import select
    from ..db import BrowserAuditRow, Session
    async with Session() as s:
        rows = (await s.execute(select(BrowserAuditRow).order_by(BrowserAuditRow.id.desc()).limit(limit))).scalars().all()
    return [{"ts": r.ts.isoformat() if r.ts else "", "action": r.action, "domain": r.domain, "detail": r.detail}
            for r in reversed(rows)]


def restore_script(origins: list[dict]) -> str:
    """Init script that replays stored localStorage entries on matching origins."""
    entries = []
    for origin in origins or []:
        for item in origin.get("localStorage", []):
            entries.append({"origin": origin.get("origin", ""), "name": item.get("name", ""), "value": item.get("value", "")})
    payload = json.dumps(entries)
    return (
        "(() => { const data = " + payload + ";"
        "for (const e of data) {"
        "  if (location.origin === e.origin) { try { localStorage.setItem(e.name, e.value); } catch (_) {} }"
        "}})();"
  )
