"""Manage persistent browser sessions (roadmap item 56).

Cookie bytes are persistent secrets and NEVER pass through chat. Importing
sessions happens ONLY at the dedicated endpoint (the bytes go straight to
the encrypted store): POST the cookies.txt / JSON export file body to
/computer/browser-state/import on the computer server. This chat tool
manages what is already stored: status, per-site enable/disable (the
approval before any logged-in session is used), revoke, clear, audit.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import settings
from ..core import browser_state as bstate

_NO_KEY = ("Persistent browser sessions are not configured: set NOESEK_BROWSER_STATE_KEY "
           "(any long passphrase - it becomes the encryption key for stored sessions).")
_IMPORT_POINTER = ("To import sessions, POST the export file directly to /computer/browser-state/import "
                   "on the computer server (PowerShell: Invoke-RestMethod -Method Post -InFile cookies.txt). "
                   "Never paste or attach cookie exports here - they never belong in chat.")


class BrowserCookiesInput(BaseModel):
    action: str = Field(description="status | enable | disable | revoke | clear | audit | import-help")
    domain: str = Field(default="", max_length=255,
                        description="site domain for enable/disable/revoke, e.g. github.com")


async def browser_cookies(inp: BrowserCookiesInput) -> dict:
    action = inp.action.strip().lower()
    if action == "import-help":
        return {"how_to_import": _IMPORT_POINTER}
    if not (settings.browser_state_key or "").strip():
        return {"error": _NO_KEY}
    if action == "status":
        state = await bstate.load_state()
        if not state:
            return {"sessions": "none stored", "how_to_import": _IMPORT_POINTER}
        return {"stored": True, **bstate.session_summary(state)}
    if action == "audit":
        return {"audit": await bstate.audit_log()}
    if action == "clear":
        await bstate.save_state({"cookies": [], "origins": [], "enabled": []})
        await bstate.audit("clear")
        return {"cleared": True}
    domain = bstate._norm(inp.domain)
    if action in ("enable", "disable", "revoke"):
        if not domain:
            return {"error": f"'{action}' needs a domain, e.g. github.com"}
        state = (await bstate.load_state()) or {"cookies": [], "origins": [], "enabled": []}
        if action == "revoke":
            removed = bstate.revoke_domain(state, domain)
            await bstate.save_state(state)
            await bstate.audit("revoke", domain, f"removed {removed} cookies")
            return {"revoked": domain, "cookies_removed": removed}
        ok = bstate.set_enabled(state, domain, action == "enable")
        if not ok:
            return {"error": f"no stored session for {domain}", "how_to_import": _IMPORT_POINTER}
        await bstate.save_state(state)
        await bstate.audit(action, domain)
        return {action + "d": domain,
                "note": ("enabled sessions are restored only on browse runs whose origin matches the site"
                         if action == "enable" else "session kept but no longer used on browse runs")}
    return {"error": f"unknown action '{inp.action}'",
            "actions": ["status", "enable", "disable", "revoke", "clear", "audit", "import-help"]}
