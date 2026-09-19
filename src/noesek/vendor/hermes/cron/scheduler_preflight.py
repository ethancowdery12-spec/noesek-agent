"""Noesek-authored bridge (NOT upstream Hermes source).

Contains a verbatim port of upstream's ``_is_transient_provider_resolve_error``
(cron/scheduler_preflight.py @ c712f06d, MIT, Nous Research); the vendored
unreachable_retry module uses it. The full preflight stack is not vendored.
"""
from typing import Optional

_TRANSIENT_NET_EXC_NAMES = frozenset({
    "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout",
    "NetworkError", "TemporaryFailure", "ServiceUnavailable",
})
_TRANSIENT_HTTP_NEEDLES = ("timed out", "timeout", "connection reset", "connection refused",
                           "temporarily unavailable", "dns", "name resolution")
_TRANSIENT_ERRNOS = frozenset({111, 101, 10061, 110, 113})  # refused, unreach, timedout, no-route


def _is_transient_provider_resolve_error(exc: BaseException) -> bool:
    """True when primary provider resolution failed for a transient network reason (DNS blip,
    ConnectError...). Verbatim port of the upstream classifier."""
    import socket

    eai_transient = {
        getattr(socket, n) for n in ("EAI_NONAME", "EAI_AGAIN", "EAI_FAIL", "EAI_NODATA")
        if hasattr(socket, n)
    }
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        module = type(cur).__module__ or ""
        msg = str(cur).lower()
        if type(cur).__name__ in _TRANSIENT_NET_EXC_NAMES:
            return True
        if any(m in module for m in ("httpx", "httpcore", "aiohttp")) and any(
            needle in msg for needle in _TRANSIENT_HTTP_NEEDLES):
            return True
        if isinstance(cur, OSError):
            if isinstance(cur, socket.gaierror):
                if cur.errno in eai_transient:
                    return True
            elif getattr(cur, "errno", None) in _TRANSIENT_ERRNOS:
                return True
        cur = cur.__cause__ or cur.__context__
    return False
