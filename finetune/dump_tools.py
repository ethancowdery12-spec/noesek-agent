"""Dump noesek's production tool registry as needle-format tools JSON.

The training set MUST be generated from the exact schemas production routes
against, so this script instantiates the real Controller registry (no server,
no DB writes - handlers are only constructed, never invoked) and serializes
every ToolSpec as {"name", "description", "parameters"}.

Usage (repo root):
    python -m finetune.dump_tools --out finetune/tools.json
"""
import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.append(os.path.join(_ROOT, "vendor", "hermes-agent"))  # vendored imports, last


def production_specs(conversation_id: int = 1):
    """Return the ToolSpecs production would see for a fresh conversation."""
    from noesek.core.controller import Controller

    class _NoopLLM:
        provider = "finetune-dump"
        model = "none"

        async def complete(self, *a, **k):
            raise RuntimeError("dump_tools never calls the LLM")

    controller = Controller(_NoopLLM())
    registry = controller.registry(conversation_id)
    return [registry.get(name) for name in sorted(registry.names())]


def to_needle_tools(specs) -> list:
    return [
        {
            "name": s.name,
            "description": s.description,
            "parameters": s.input_model.model_json_schema(),
        }
        for s in specs
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="finetune/tools.json")
    args = ap.parse_args()
    tools = to_needle_tools(production_specs())
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)
    print(f"wrote {len(tools)} tools to {args.out}")
    for t in tools:
        print(f"  {t['name']}")


if __name__ == "__main__":
    main()
