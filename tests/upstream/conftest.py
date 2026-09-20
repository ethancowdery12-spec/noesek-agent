"""Adopted upstream tests import top-level module names (tools.*, cron.*,
gateway.*, plugins.*, agent, utils, hermes_constants, ...). Since v3 S2 the
full vendored upstream tree at vendor/hermes-agent provides those top-level
packages directly (pytest pythonpath), so no import aliasing is needed.

Documented exclusions: test IDs requiring non-vendored Hermes infrastructure,
skipped with the reason recorded in MANIFEST.json. Adopted files stay
byte-identical to upstream at the pinned commit d7b836ab.
"""
import json
from pathlib import Path
_MANIFEST = json.loads((Path(__file__).parent / "MANIFEST.json").read_text())
_EXCLUDED = _MANIFEST["excluded_tests"]


def pytest_collection_modifyitems(items):
    import pytest
    for item in items:
        tid = item.nodeid.split("::", 1)[-1]
        full = item.nodeid
        for excl_id, why in _EXCLUDED.items():
            if full.endswith(excl_id.split("/", 1)[-1]) or excl_id.endswith(full):
                item.add_marker(pytest.mark.skip(reason=why))
                break


import pytest


@pytest.fixture(autouse=True)
def _clear_noesek_home_override():
    # Noesek's own tests pin the vendored state home through the hermes home
    # override contextvar; upstream tests drive home resolution through the
    # HERMES_HOME env var instead. Clear the override so env wins, and restore
    # a clean slate afterwards (Noesek tests set their own overrides).
    from hermes_constants import set_hermes_home_override
    token = set_hermes_home_override(None)
    yield
    set_hermes_home_override(None)
