"""Noesek-authored bridge (NOT upstream Hermes source): one-shot deprecation warnings."""
import warnings

_warned: set[tuple] = set()


def warn_once(module: str, name: str, target_module: str, target_name: str) -> None:
    key = (module, name)
    if key in _warned:
        return
    _warned.add(key)
    warnings.warn(
        f"{module}.{name} is a plugin-compat alias for {target_module}.{target_name}",
        DeprecationWarning, stacklevel=2)
