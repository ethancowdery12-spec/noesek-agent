"""Tranche-8 adapter suite: run every Noesek adapter and require clean verdicts."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_all_adapters_pass():
    proc = subprocess.run([sys.executable, str(REPO / "evals" / "run_adapters.py")],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        # Surface failing adapters' full verdicts (incl. stderr_tail) - the
        # one-line summary alone made an ACP startup hang undiagnosable in CI.
        detail = ""
        try:
            results = json.loads((REPO / "evals" / "adapter-results.json").read_text())
            bad = {p: r["result"] for p, r in results["adapters"].items()
                   if r["result"].get("verdict") not in ("pass", "skip", "feature-absent")}
            detail = json.dumps(bad, indent=2)[-3500:]
        except Exception:
            pass
        raise AssertionError(proc.stdout[-2000:] + proc.stderr[-2000:] + "\n" + detail)
    results = json.loads((REPO / "evals" / "adapter-results.json").read_text())
    assert len(results["adapters"]) == 15
    verdicts = {p: r["result"]["verdict"] for p, r in results["adapters"].items()}
    # "skip" is legitimate where an adapter's external prerequisite is absent
    # (e.g. the pinned hermes-src checkout outside a packaged sdist)
    assert all(v in ("pass", "skip") for v in verdicts.values()), verdicts
    for probe, r in results["adapters"].items():
        assert r["upstream_sha256"], probe
        assert Path(REPO / r["adapter"]).is_file(), probe
