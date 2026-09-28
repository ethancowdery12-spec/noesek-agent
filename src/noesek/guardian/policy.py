"""Owner policy override store for the guardian gate.

Lets the owner register untrained tools/connectors and override verdict bands
(allow/escalate/deny) per tool or per connector prefix WITHOUT retraining, per
the owner's feature spec. Design (docs live in the repo wiki/PR):

- Machine-written ONLY by the sanctioned setup questionnaire (noesek
  guardian-setup). Hand edits fail the HMAC signature check.
- HMAC-SHA256 integrity. Key lives in a DPAPI-protected blob on Windows
  (per-user scope); on other platforms a chmod-600 key file (documented
  weaker fallback, used by CI/tests).
- The signature is re-verified on EVERY gate call - no RAM-tamper window.
- Fail closed: file missing/invalid/tampered after setup -> every verdict is
  deny with an error. A signed marker distinguishes "never configured"
  (feature off, model verdicts pass through) from "configured but file
  missing" (fail closed).
- Hard-coded FLOOR (code constants, never in the file): credential_access,
  exfiltration and remote_exec denies at threshold cannot be softened by any
  rule. destructive/external-communication bands stay owner-overridable so
  e.g. a payments-allow pin is possible when the owner explicitly asks.
"""
from __future__ import annotations

import hashlib
import base64
import hmac
import json
import logging
import os
import sys
import tempfile
import time

from ..config import settings

log = logging.getLogger(__name__)

FLOOR_CLASSES = frozenset({"credential_access", "exfiltration", "remote_exec"})
BANDS = ("allow", "escalate", "deny")
_SEVERITY = {"allow": 0, "escalate": 1, "deny": 2}
_RULE_KINDS = ("pin", "floor", "cap")
_MATCH_KINDS = ("tool", "prefix")
_POLICY_VERSION = 1


class PolicyError(Exception):
    """The policy store is missing, unreadable, or failed integrity checks."""


def _dir() -> str:
    return settings.guardian_policy_dir or os.path.join(os.path.expanduser("~"), ".noesek")


def _policy_path() -> str:
    return os.path.join(_dir(), "guardian_policy.json")


def _marker_path() -> str:
    return os.path.join(_dir(), "guardian_policy.configured")


def _key_path() -> str:
    return os.path.join(_dir(), "guardian_policy.key")


def _load_or_create_key(create: bool = False) -> bytes:
    """Raw 32-byte HMAC key. Windows: DPAPI per-user protected blob on disk.
    Other platforms: chmod-600 key file (CI/dev fallback, weaker by design)."""
    path = _key_path()
    if sys.platform.startswith("win"):
        import win32crypt  # type: ignore

        if os.path.exists(path):
            with open(path, "rb") as f:
                return win32crypt.CryptUnprotectData(f.read(), None, None, None, 0)[1]
        if not create:
            raise PolicyError("policy key missing")
        key = os.urandom(32)
        blob = win32crypt.CryptProtectData(key, "noesek-guardian-policy", None, None, None, 0)
        _atomic_write(path, blob)
        return key
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        if len(data) != 32:
            raise PolicyError("policy key corrupt")
        return data
    if not create:
        raise PolicyError("policy key missing")
    key = os.urandom(32)
    _atomic_write(path, key)
    return key


def _atomic_write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows ACLs handle this


def _sign(payload: bytes, key: bytes) -> str:
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _validate_rules(rules) -> list:
    if not isinstance(rules, list):
        raise PolicyError("rules must be a list")
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise PolicyError(f"rule {i} is not an object")
        mk, kind, band = r.get("match"), r.get("kind"), r.get("band")
        pattern = r.get("pattern")
        if mk not in _MATCH_KINDS:
            raise PolicyError(f"rule {i}: bad match kind {mk!r}")
        if kind not in _RULE_KINDS:
            raise PolicyError(f"rule {i}: bad rule kind {kind!r}")
        if band not in BANDS:
            raise PolicyError(f"rule {i}: bad band {band!r}")
        if not isinstance(pattern, str) or not pattern:
            raise PolicyError(f"rule {i}: empty pattern")
        out.append({"match": mk, "pattern": pattern, "kind": kind, "band": band,
                    "note": str(r.get("note") or "")[:200]})
    return out


def write_policy(rules: list, answers_summary: str, known_tools: list | None = None) -> str:
    """The ONLY write path. Validates, signs, atomically writes the policy file
    and the configured marker. Called by the setup questionnaire and tests."""
    key = _load_or_create_key(create=True)
    payload = {
        "version": _POLICY_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "answers_summary": answers_summary[:2000],
        "known_tools": sorted(known_tools or []),
        "rules": _validate_rules(rules),
    }
    blob = _canonical(payload)
    doc = {"payload": payload, "signature": _sign(blob, key)}
    _atomic_write(_policy_path(), json.dumps(doc, indent=2).encode())
    marker = {"configured": True, "created_at": payload["created_at"]}
    mblob = _canonical(marker)
    _atomic_write(_marker_path(), json.dumps({"payload": marker, "signature": _sign(mblob, key)}, indent=2).encode())
    return _policy_path()


def _read_signed(path: str) -> dict:
    if not os.path.exists(path):
        raise PolicyError(f"missing {os.path.basename(path)}")
    try:
        with open(path, "rb") as f:
            doc = json.loads(f.read().decode())
    except Exception as e:  # noqa: BLE001
        raise PolicyError(f"unreadable {os.path.basename(path)}: {type(e).__name__}")
    payload, sig = doc.get("payload"), doc.get("signature")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        raise PolicyError("bad document shape")
    key = _load_or_create_key(create=False)
    if not hmac.compare_digest(_sign(_canonical(payload), key), sig):
        raise PolicyError("signature mismatch (tampered or foreign file)")
    return payload


def is_configured() -> bool:
    """True once the owner ran setup. A missing marker means the feature was
    never set up (guardian runs as without it). An INVALID marker is treated
    as configured so the store fails closed rather than silently off."""
    try:
        _read_signed(_marker_path())
        return True
    except PolicyError as e:
        if "missing" in str(e):
            return False
        log.warning("guardian policy marker invalid: %s - treating as configured (fail closed)", e)
        return True


def load_policy() -> dict:
    """Read + integrity-verify the policy file. Re-verifies the HMAC on every
    call by design; raises PolicyError on any failure."""
    payload = _read_signed(_policy_path())
    if payload.get("version") != _POLICY_VERSION:
        raise PolicyError(f"unsupported version {payload.get('version')!r}")
    payload["rules"] = _validate_rules(payload.get("rules"))
    return payload


def _find_rule(rules: list, tool_name: str):
    exact = [r for r in rules if r["match"] == "tool" and r["pattern"] == tool_name]
    if exact:
        return exact[0]
    prefixes = [r for r in rules if r["match"] == "prefix" and tool_name.startswith(r["pattern"])]
    if prefixes:
        return max(prefixes, key=lambda r: len(r["pattern"]))
    return None


def _resolve_rules(policy: dict, tool_name: str, model_verdict: str) -> tuple[str, str | None]:
    """Rule resolution shared by the file and DB backends (policy already
    loaded and signature-verified)."""
    rule = _find_rule(policy["rules"], tool_name)
    if rule is None:
        known = set(policy.get("known_tools") or [])
        if known and tool_name not in known:
            # Untrained tool with no owner rule: never silently allow.
            sev = max(_SEVERITY[model_verdict], _SEVERITY[settings.guardian_policy_new_tool_default])
            return next(b for b in BANDS if _SEVERITY[b] == sev), "new_tool_default"
        return model_verdict, None
    kind, band = rule["kind"], rule["band"]
    if kind == "pin":
        return band, f"pin:{rule['pattern']}"
    if kind == "floor":
        sev = max(_SEVERITY[model_verdict], _SEVERITY[band])
        return next(b for b in BANDS if _SEVERITY[b] == sev), f"floor:{rule['pattern']}"
    sev = min(_SEVERITY[model_verdict], _SEVERITY[band])
    return next(b for b in BANDS if _SEVERITY[b] == sev), f"cap:{rule['pattern']}"


def apply(tool_name: str, deny_score: float, esc_prob: float, top_risk: str | None,
          model_verdict: str) -> tuple[str, str | None]:
    """File-backend policy overlay. Order: hard floor -> owner rules -> model
    verdict. Returns (verdict, rule_tag). Raises PolicyError when the
    configured store is invalid (caller fails closed)."""
    if top_risk in FLOOR_CLASSES and deny_score >= settings.guardian_deny_threshold:
        return "deny", "floor"
    if not is_configured():
        return model_verdict, None
    return _resolve_rules(load_policy(), tool_name, model_verdict)


def _reset_for_tests():
    """No module-level caching exists (per-call verify); kept for symmetry with
    scorer._reset_for_tests so test fixtures read uniformly."""
# ---------------------------------------------------------------------------
# DB backend: when guardian_policy_key is set, the signed documents live in
# the guardian_policy_store table of the app's database instead of files, so
# they survive stateless deploys. Same HMAC scheme, same semantics; every
# store/verify error raises PolicyError and the gate fails closed.


def _db_mode() -> bool:
    return bool(settings.guardian_policy_key.strip())


def _load_key_db() -> bytes:
    """Decode the env-provided HMAC key (base64url, decodes to 32 bytes)."""
    raw = settings.guardian_policy_key.strip()
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception as e:  # noqa: BLE001
        raise PolicyError(f"guardian_policy_key is not valid base64 ({type(e).__name__})")
    if len(key) != 32:
        raise PolicyError(f"guardian_policy_key decodes to {len(key)} bytes, need 32")
    return key


def _verify_doc(doc, key: bytes, what: str) -> dict:
    """Verify a signed document envelope {payload, signature}."""
    if not isinstance(doc, dict):
        raise PolicyError(f"bad {what} document shape")
    payload, sig = doc.get("payload"), doc.get("signature")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        raise PolicyError(f"bad {what} document shape")
    if not hmac.compare_digest(_sign(_canonical(payload), key), sig):
        raise PolicyError(f"{what} signature mismatch (tampered or foreign document)")
    return payload


async def _aread_signed(row_key: str) -> dict:
    """Load + verify one signed document row from guardian_policy_store."""
    from .. import db as _db  # deferred: sqlalchemy session only needed in DB mode
    try:
        async with _db.Session() as s:
            row = await s.get(_db.GuardianPolicyRow, row_key)
    except PolicyError:
        raise
    except Exception as e:  # noqa: BLE001 - DB down/driver error fails closed
        raise PolicyError(f"policy store read failed ({type(e).__name__})")
    if row is None:
        raise PolicyError(f"missing guardian_policy_store.{row_key} row")
    return _verify_doc(row.doc, _load_key_db(), row_key)


async def ais_configured() -> bool:
    """DB-mode mirror of is_configured(): valid marker row -> configured.
    Missing marker -> unconfigured (pass-through). Invalid marker -> treat as
    configured so the gate fails closed instead of silently disabling policy."""
    try:
        await _aread_signed("marker")
        return True
    except PolicyError as e:
        if "missing" in str(e):
            return False
        log.warning("guardian policy marker invalid: %s - treating as configured (fail closed)", e)
        return True


async def aload_policy() -> dict:
    """DB-mode mirror of load_policy(): read + verify + validate the policy row."""
    payload = await _aread_signed("policy")
    if payload.get("version") != _POLICY_VERSION:
        raise PolicyError(f"unsupported version {payload.get('version')!r}")
    payload["rules"] = _validate_rules(payload.get("rules"))
    return payload


async def awrite_policy(rules: list, answers_summary: str, known_tools: list | None = None) -> str:
    """DB-mode write path (setup questionnaire): validates, signs and upserts
    the policy + marker rows in one transaction."""
    from .. import db as _db
    key = _load_key_db()
    payload = {
        "version": _POLICY_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "answers_summary": answers_summary[:2000],
        "known_tools": sorted(known_tools or []),
        "rules": _validate_rules(rules),
    }
    docs = {"policy": {"payload": payload, "signature": _sign(_canonical(payload), key)}}
    marker = {"configured": True, "created_at": payload["created_at"]}
    docs["marker"] = {"payload": marker, "signature": _sign(_canonical(marker), key)}
    async with _db.Session() as s:
        for k, d in docs.items():
            row = await s.get(_db.GuardianPolicyRow, k)
            if row is None:
                s.add(_db.GuardianPolicyRow(key=k, doc=d))
            else:
                row.doc = d
        await s.commit()
    return "db:guardian_policy_store"


async def apply_async(tool_name: str, deny_score: float, esc_prob: float, top_risk: str | None,
                      model_verdict: str) -> tuple[str, str | None]:
    """Gate entry point. File backend when guardian_policy_key is unset
    (unchanged behavior); DB backend otherwise. Store/verify failures raise
    PolicyError; the gate catches it and fails closed."""
    if not _db_mode():
        return apply(tool_name, deny_score, esc_prob, top_risk, model_verdict)
    if top_risk in FLOOR_CLASSES and deny_score >= settings.guardian_deny_threshold:
        return "deny", "floor"
    if not await ais_configured():
        return model_verdict, None
    return _resolve_rules(await aload_policy(), tool_name, model_verdict)
