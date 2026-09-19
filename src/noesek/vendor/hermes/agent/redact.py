"""Noesek-authored bridge (NOT upstream Hermes source).

Implements ``agent.redact.redact_sensitive_text`` for the vendored cron delivery
queue, delegating to a conservative local scrubber: secrets, bearer tokens, and
URL credentials are replaced with [REDACTED].
"""
from __future__ import annotations

import re

_URL_CRED = re.compile(r"(https?://)[^/\s:@]+(:[^/\s@]*)?@")
_KEYVAL = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization|auth)"
    r"([\s]*[=:][\s]*)(['\"]?)[^\s'\"]{4,}\3")
_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]+")


def redact_sensitive_text(text: str, force: bool = False, redact_url_credentials: bool = False) -> str:
    out = str(text)
    if redact_url_credentials or force:
        out = _URL_CRED.sub(r"\1[REDACTED]@", out)
    out = _BEARER.sub("Bearer [REDACTED]", out)
    out = _KEYVAL.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", out)
    return out
