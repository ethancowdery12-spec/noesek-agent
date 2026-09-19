"""Noesek-authored bridge (NOT upstream Hermes source).

Single-profile behavior of upstream gateway/platforms/_shared.py: Noesek runs one
profile with no multiplexing, so the upstream per-profile secret-scope rungs collapse
to their documented single-profile behavior (plain os.environ, then config extra).
``decode_json_list_literal`` is verbatim upstream.
"""
import json
import os


def platform_gate_env(name: str, default: str = "") -> str:
    """Allow/deny gate env read, single-profile form (upstream: plain os.getenv, stripped)."""
    if not name:
        return default
    return (os.getenv(name) or default).strip()


def decode_json_list_literal(value):
    """Verbatim upstream: decode a JSON-encoded allowlist, passing malformed values through."""
    if isinstance(value, str) and value.lstrip()[:1] == "[":
        try:
            loaded = json.loads(value)
        except ValueError:
            return value
        if isinstance(loaded, list):
            return loaded
    return value


def extra_or_secret(extra, key: str, env: str, default="", *, blank_is_unset: bool = True):
    """Single-profile per-profile setting reader: explicit env -> config extra -> default."""
    if env:
        env_value = os.getenv(env)
        if env_value is not None and str(env_value).strip():
            return env_value
    value = (extra or {}).get(key)
    if value is None:
        return default
    if blank_is_unset and isinstance(value, str) and not value.strip():
        return default
    return value
