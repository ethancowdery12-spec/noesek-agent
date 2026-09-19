"""Adapter for upstream evals/gemini_type_array_probe.py (Hermes c712f06d).

Upstream intent: tool schemas with array-typed fields must validate against
the provider SDK's schema rules (arrays require item types). Narrowed scope:
Noesek has no Gemini transport, so this adapter enforces the same invariant
against Noesek's own tool schemas - every array node must declare `items`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir


def walk(node, path, violations):
    if isinstance(node, dict):
        if node.get("type") == "array" and "items" not in node:
            violations.append(path or "<root>")
        for k, v in node.items():
            walk(v, f"{path}.{k}", violations)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", violations)


def main():
    out = out_dir()
    from noesek.workers.runner import _all_tool_specs
    violations = []
    specs = _all_tool_specs()
    for name, spec in sorted(specs.items()):
        schema = spec.input_model.model_json_schema()
        walk(schema, name, violations)
    (out / "array_check.json").write_text(json.dumps(
        {"tools": sorted(specs), "violations": violations}, indent=2) + "\n")
    emit("pass" if not violations else "fail", tools_checked=len(specs),
         violations=violations,
         deviation="Noesek tool schemas instead of Gemini SDK validation (no Gemini transport)")


if __name__ == "__main__":
    main()
