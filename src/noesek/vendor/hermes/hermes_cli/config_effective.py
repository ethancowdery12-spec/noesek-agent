"""Noesek-authored bridge (NOT upstream Hermes source).

``load_user_config_effective`` is called lazily by vendored hermes_time only to
look up a configured timezone. Noesek carries timezone in its own settings;
returning an empty mapping keeps the vendored clock on its env/UTC fallbacks.
"""
from typing import Any


def load_user_config_effective(path=None) -> dict[str, Any]:
    return {}
