"""Noesek-authored bridge (NOT upstream Hermes source). No Hermes plugin discovery."""


def discover_plugins(*a, **kw) -> list:
    return []


def _get_disabled_plugins() -> set:
    return set()


def get_plugin_manager():
    return None
