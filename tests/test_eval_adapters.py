"""Tranche-8 adapter suite: run every Noesek adapter and require clean verdicts."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_all_adapters_pass():
    proc = subprocess.run([sys.executable, str(REPO / "evals" / "run_adapters.py")],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    results = json.loads((REPO / "evals" / "adapter-results.json").read_text())
    assert len(results["adapters"]) == 15
    verdicts = {p: r["result"]["verdict"] for p, r in results["adapters"].items()}
    # "skip" is legitimate where an adapter's external prerequisite is absent
    # (e.g. the pinned hermes-src checkout outside a packaged sdist)
    assert all(v in ("pass", "skip") for v in verdicts.values()), verdicts
    for probe, r in results["adapters"].items():
        assert r["upstream_sha256"], probe
        assert Path(REPO / r["adapter"]).is_file(), probe
