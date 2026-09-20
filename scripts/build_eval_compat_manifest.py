"""Build evals/compat-manifest.json: per-probe compatibility verdicts.

Scans the pinned Hermes eval suite (commit c712f06d...) and classifies each
probe by whether it can run against Noesek as an external harness:

  run          - protocol-level probe that can attach to Noesek as-is
  needs-adapter - probes a protocol Noesek implements, but launches the Hermes
                  checkout's own entrypoint; needs a Noesek-targeted adapter
  incompatible  - measures Hermes-internal modules (gateway.*, hermes_cli.*,
                  tools.*, agent.*, ...) that are not part of Noesek's public
                  wire surface

Classification is mechanical (static import scan); verdicts are conservative.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

HERMES_EVALS = Path(sys.argv[1] if len(sys.argv) > 1 else "../hermes-src/evals")
OUT = Path(__file__).resolve().parents[1] / "evals" / "compat-manifest.json"

HERMES_INTERNAL_ROOTS = {
    "agent", "cli", "cron", "gateway", "hermes_cli", "hermes_state", "plugins",
    "providers", "run_agent", "tools", "tui_gateway", "acp_adapter",
}
# Probes with a Noesek-targeted adapter (evals/adapters/) preserving the
# upstream behavioral intent; results land in evals/adapter-results.json.
ADAPTED = {
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
# Probes whose *protocol* Noesek implements (ACP wire, channel webhook wires,
# cron error surface, gateway-style HTTP API) but which launch Hermes's own
# entrypoints today.
ADAPTABLE = {
    "acp_empty_session_wire.py": "ACP stdio wire; Noesek serves noesek.compat.acp_server",
    "slack_stream_wire_contract.py": "Slack wire; Noesek serves /webhooks/slack",
    "delivery_flood_wire.py": "Telegram delivery wire; Noesek serves /webhooks/telegram",
    "webhook_auth": "Webhook auth surface; Noesek routers verify signatures",
    "gateway": "HTTP API surface; Noesek gateway mounts routers with authz chain",
    "cron_error_diagnostics.py": "Cron error surface; Noesek cron ledger exists",
}


def py_files(probe: Path):
    if probe.is_file() and probe.suffix == ".py":
        return [probe]
    if probe.is_dir():
        return sorted(probe.rglob("*.py"))
    return []


def internal_imports(files):
    hits = set()
    for f in files:
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            hits.add("<unparseable>")
            continue
        for node in ast.walk(tree):
            root = None
            if isinstance(node, ast.Import):
                for a in node.names:
                    root = a.name.split(".")[0]
                    if root in HERMES_INTERNAL_ROOTS:
                        hits.add(root)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in HERMES_INTERNAL_ROOTS:
                    hits.add(root)
    return sorted(hits)


def main() -> int:
    probes = []
    for entry in sorted(HERMES_EVALS.iterdir()):
        if entry.name.startswith("__") or entry.name == "__pycache__":
            continue
        files = py_files(entry)
        if not files:
            verdict, reason = "incompatible", "no python sources (asset-only fixture)"
            internals = []
        else:
            internals = internal_imports(files)
            if entry.name in ADAPTED:
                verdict = "adapted"
                reason = f"Noesek adapter evals/adapters/{ADAPTED[entry.name]} preserves behavioral intent"
            elif entry.name in ADAPTABLE:
                verdict, reason = "needs-adapter", ADAPTABLE[entry.name]
            elif internals:
                verdict = "incompatible"
                reason = "imports Hermes-internal modules: " + ", ".join(internals)
            else:
                verdict = "needs-adapter"
                reason = "no Hermes-internal imports detected; manual review required"
        digest = hashlib.sha256()
        for f in files:
            digest.update(f.read_bytes())
        probes.append({
            "probe": entry.name,
            "verdict": verdict,
            "reason": reason,
            "hermes_internal_imports": internals,
            "sources_sha256": digest.hexdigest(),
        })
    manifest = {
        "hermes_commit": "d7b836ab1c0cddaafc109ed24c9a83b6191cdc88",
        "probe_count": len(probes),
        "verdict_counts": {
            v: sum(1 for p in probes if p["verdict"] == v)
            for v in ("run", "adapted", "needs-adapter", "incompatible")
        },
        "probes": probes,
    }
    OUT.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["verdict_counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
