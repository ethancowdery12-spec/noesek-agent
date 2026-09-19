"""Import alias: adopted upstream Hermes tests import top-level module names
(tools.*, cron.*, gateway.*, plugins.*, hermes_constants, ...). Resolve those to
the vendored noesek.vendor.hermes namespace so the tests run UNCHANGED against
Noesek's vendored copies."""
import importlib
import importlib.abc
import importlib.machinery
import sys

ALIAS_ROOTS = {"tools", "cron", "gateway", "plugins", "agent", "utils",
               "hermes_constants", "hermes_time", "hermes_state_wal", "hermes_cli"}
VENDOR_NS = "noesek.vendor.hermes"


class _VendorAliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] not in ALIAS_ROOTS:
            return None
        return importlib.machinery.ModuleSpec(fullname, self)

    def create_module(self, spec):
        return importlib.import_module(f"{VENDOR_NS}.{spec.name}")

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _VendorAliasFinder())


# Documented exclusions: test IDs requiring non-vendored Hermes infrastructure,
# skipped with the reason recorded in MANIFEST.json. Adopted files stay byte-identical.
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
    from noesek.vendor.hermes.hermes_constants import set_hermes_home_override
    token = set_hermes_home_override(None)
    yield
    set_hermes_home_override(None)
