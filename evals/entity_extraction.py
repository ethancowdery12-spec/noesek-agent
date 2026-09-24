"""Entity-extraction eval (roadmap item 66).

Compares extractors on the frozen fixtures in evals/entity_fixtures.py:
  - deterministic: src.noesek.core.memory_graph.extract_entities (live path)
  - llm: src.noesek.core.memory_graph.llm_extract_entities, only when a
    chat LLM is configured in this environment (skipped otherwise)

Metric per case: precision / recall / F1 over normalized entity strings.
Usage: python -m evals.entity_extraction [--json PATH]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.entity_fixtures import CASES
from noesek.core.memory_graph import extract_entities


def _norm(e: str) -> str:
    return " ".join(e.lower().split())


def score_case(predicted: list[str], expected: list[str]) -> dict:
    pred, exp = {_norm(e) for e in predicted}, set(expected)
    tp = len(pred & exp)
    prec = tp / len(pred) if pred else (1.0 if not exp else 0.0)
    rec = tp / len(exp) if exp else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "missing": sorted(exp - pred), "extra": sorted(pred - exp)}


def evaluate(extractor) -> dict:
    cases = []
    for c in CASES:
        predicted = extractor(c["content"])
        cases.append({"content": c["content"], "predicted": sorted({_norm(e) for e in predicted}),
                      **score_case(predicted, c["expected"])})
    n = len(cases)
    return {"cases": n,
            "precision": round(sum(c["precision"] for c in cases) / n, 4),
            "recall": round(sum(c["recall"] for c in cases) / n, 4),
            "f1": round(sum(c["f1"] for c in cases) / n, 4),
            "worst": sorted(cases, key=lambda c: c["f1"])[:5],
            "detail": cases}


def run() -> dict:
    report = {"extractors": {"deterministic": evaluate(extract_entities)}}
    try:
        from noesek.core.llm import configured_llm
        from noesek.core.memory_graph import llm_extract_entities
        llm = configured_llm()
        report["extractors"]["llm"] = evaluate(
            lambda content: asyncio.run(llm_extract_entities(content, llm=llm)))
    except Exception as e:  # no configured provider keys in this environment
        report["extractors"]["llm"] = {"skipped": f"{type(e).__name__}: {e}"}
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args()
    report = run()
    for name, r in report["extractors"].items():
        if "skipped" in r:
            print(f"{name}: SKIPPED ({r['skipped']})")
        else:
            print(f"{name}: precision={r['precision']:.1%} recall={r['recall']:.1%} f1={r['f1']:.1%} ({r['cases']} cases)")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
