"""Run every Noesek adapter for the Hermes needs-adapter probes.

Executes each adapter in its own subprocess (isolated homes, no shared state),
collects the JSON verdict line, and writes evals/adapter-results.json
mapping each upstream probe (by content SHA-256 from the compat manifest) to
its Noesek adapter and result.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADAPTERS = REPO / "evals" / "adapters"
RESULTS_DIR = REPO / "evals" / "adapter-results"
OUT = REPO / "evals" / "adapter-results.json"

# upstream probe name -> adapter file
ADAPTER_MAP = {
    "acp_empty_session_wire.py": "acp_wire.py",
    "auth_pool_controls.py": "auth_controls.py",
    "cli_fallback_add_picker_error.py": "config_atomicity.py",
    "codebase_navigability": "codebase_navigability.py",
    "cron_error_diagnostics.py": "cron_errors.py",
    "delegation_group_schema": "schema_footprint.py",
    "delivery_flood_wire.py": "telegram_flood.py",
    "gateway": "session_persistence.py",
    "gemini_type_array_probe.py": "schema_arrays.py",
    "goal_command_parity.py": "command_parity.py",
    "mcp_device_flow.py": "mcp_device_flow.py",
    "process_result_receipt_probe.py": "process_receipt.py",
    "slack_stream_wire_contract.py": "slack_wire.py",
    "toolperf_abeval": "orchestration_overhead.py",
    "webhook_auth": "webhook_signatures.py",
}


def main() -> int:
    only = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    manifest = json.loads((REPO / "evals" / "compat-manifest.json").read_text())
    hashes = {p["probe"]: p["sources_sha256"] for p in manifest["probes"]}
    results = {}
    for probe, adapter in sorted(ADAPTER_MAP.items()):
        if only and probe not in only and adapter not in only:
            continue
        import shutil
        out = RESULTS_DIR / adapter.removesuffix(".py")
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        proc = subprocess.run([sys.executable, str(ADAPTERS / adapter), "--out", str(out)],
                              capture_output=True, text=True, timeout=600)
        wall = round(time.monotonic() - start, 2)
        try:
            verdict = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            verdict = {"verdict": "error", "stderr_tail": proc.stderr[-500:]}
        verdict["wall_seconds"] = wall
        results[probe] = {"adapter": f"evals/adapters/{adapter}",
                          "upstream_sha256": hashes.get(probe), "result": verdict}
        print(f"{probe}: {verdict['verdict']} ({wall}s)")
    OUT.write_text(json.dumps({"upstream_pin": manifest["hermes_commit"],
                               "adapters": results}, indent=2, sort_keys=True) + "\n")
    bad = {p: r["result"]["verdict"] for p, r in results.items()
           if r["result"]["verdict"] not in ("pass", "skip", "feature-absent")}
    print("FAILURES:" if bad else "ALL OK", bad or "")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
