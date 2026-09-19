"""Drift checks for adopted upstream tests: adopted files must stay byte-identical
to the pinned upstream commit, and the manifest pin must match VENDORING.md."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "tests/upstream/MANIFEST.json").read_text())


def test_adopted_tests_are_unchanged_upstream_copies():
    assert len(MANIFEST["files"]) >= 12
    for rel, meta in MANIFEST["files"].items():
        f = ROOT / "tests/upstream" / rel
        assert f.exists(), rel
        assert hashlib.sha256(f.read_bytes()).hexdigest() == meta["sha256"], f"adopted test drifted: {rel}"


def test_manifest_pin_matches_vendoring_pin():
    vendoring = (ROOT / "VENDORING.md").read_text()
    assert MANIFEST["upstream"]["commit"] in vendoring


def test_excluded_tests_have_reasons():
    for tid, why in MANIFEST["excluded_tests"].items():
        assert why.strip(), tid
        # excluded IDs reference adopted files
        assert any(tid.split("::")[0].endswith(rel) for rel in MANIFEST["files"]), tid
