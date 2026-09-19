"""Adapter for upstream evals/delegation_group_schema/ (Hermes c712f06d).

Upstream intent: assemble real eager tool definitions per delegation group in
a credential-free home and produce compact-JSON footprint receipts. Upstream
also counts tiktoken tokens; this adapter reports exact byte counts (Noesek
pins no tokenizer) and notes that deviation. Noesek target: worker registries
from workers.runner plus the thin controller's tool surface.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir


def footprints():
    from noesek.workers.runner import WORKERS, worker_registry
    groups = {}
    for name in sorted(WORKERS):
        reg = worker_registry(name)
        blob = json.dumps(reg.schemas(), separators=(",", ":"), sort_keys=True).encode()
        groups[name] = {"tools": reg.names(), "schema_bytes": len(blob)}
    return groups


def main():
    out = out_dir()
    g1, g2 = footprints(), footprints()
    deterministic = g1 == g2
    receipt = {"groups": g1,
               "total_schema_bytes": sum(g["schema_bytes"] for g in g1.values()),
               "deviation": "byte counts instead of tiktoken tokens (no tokenizer pinned)"}
    (out / "schema_footprint.json").write_text(json.dumps(receipt, indent=2) + "\n")
    ok = deterministic and all(g["tools"] for g in g1.values())
    emit("pass" if ok else "fail", deterministic=deterministic,
         groups={k: v["schema_bytes"] for k, v in g1.items()},
         total_schema_bytes=receipt["total_schema_bytes"],
         receipt_path=str(out / "schema_footprint.json"))


if __name__ == "__main__":
    main()
