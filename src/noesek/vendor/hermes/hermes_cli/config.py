"""Noesek-authored bridge (NOT upstream Hermes source).

Implements the ``hermes_cli.config`` surface used by the vendored approval
modules: ``cfg_get`` (dotted-path lookup) and ``load_config_readonly`` (a
read-only config mapping). The config is sourced from Noesek settings and
defaults to deny-by-default: no approvals mode/off/yolo bypass is active
unless explicitly configured.
"""
from __future__ import annotations

from typing import Any

_cached: dict[str, Any] | None = None


def _build() -> dict[str, Any]:
    # Deny-by-default: approvals stay interactive. Noesek owns approval
    # persistence/expiry; the vendored stack supplies classification.
    return {"approvals": {"mode": "prompt"}, "security": {"approval": {}}}


def load_config_readonly() -> dict[str, Any]:
    """Return the cached read-only config mapping (callers must not mutate)."""
    global _cached
    if _cached is None:
        _cached = _build()
    return _cached


def cfg_get(cfg: dict[str, Any], *path: str, default: Any = None) -> Any:
    node: Any = cfg or {}
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def reset_cache() -> None:
    global _cached
    _cached = None


def load_config() -> dict:
    """Upstream contract: full config mapping. Noesek supplies an empty mapping;
    cron tuning falls back to upstream defaults."""
    return {}


def _secure_dir(path) -> None:
    """Owner-only directory (0700), the POSIX core of upstream's helper."""
    import os
    os.chmod(path, 0o700)


def _secure_file(path) -> None:
    """Owner-only file (0600), the POSIX core of upstream's helper."""
    import os
    os.chmod(path, 0o600)


def get_hermes_home():
    """Re-export of the vendored hermes_constants home resolution."""
    from ..hermes_constants import get_hermes_home as _g
    return _g()


def save_config(cfg: dict) -> None:
    """Noesek does not persist Hermes-shaped config; writes are refused."""
    raise NotImplementedError("Noesek manages its own settings; Hermes config writes are unsupported")


def save_env_value(*a, **kw):
    """Noesek owns configuration; the pairing store's env allowlist mirror is refused."""
    raise RuntimeError(
        "hermes_cli.config.save_env_value is refused in Noesek: Noesek is the single "
        "configuration owner; write allowlists through Noesek settings, not Hermes .env mirrors."
    )


def remove_env_value(*a, **kw):
    """Noesek owns configuration; the pairing store's env allowlist mirror is refused."""
    raise RuntimeError(
        "hermes_cli.config.remove_env_value is refused in Noesek: Noesek is the single "
        "configuration owner; write allowlists through Noesek settings, not Hermes .env mirrors."
    )
