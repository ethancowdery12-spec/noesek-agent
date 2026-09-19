"""The eval-compat manifest must match a fresh rebuild from the pinned upstream checkout."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES = REPO.parent / "hermes-src" / "evals"


def test_manifest_is_current(tmp_path):
    if not HERMES.is_dir():
        import pytest
        pytest.skip("pinned hermes-src checkout not present")
    import subprocess
    import sys
    out = REPO / "evals" / "compat-manifest.json"
    before = json.loads(out.read_text())
    subprocess.run([sys.executable, str(REPO / "scripts" / "build_eval_compat_manifest.py"),
                    str(HERMES)], check=True, capture_output=True)
    after = json.loads(out.read_text())
    assert before == after
    assert after["probe_count"] == len(after["probes"])
    assert after["hermes_commit"] == "c712f06dcdd24053a4118f38d2090ac53137ecfc"
