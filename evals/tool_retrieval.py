"""Tool-retrieval evaluation (Gorilla pattern, roadmap item 82).

Measures how often the right tool is retrievable for a natural-language
query, using the frozen acceptance fixtures in finetune/cases.py (positive
cases only; critical/refusal cases belong to the needle acceptance gate).

Two rankers are compared over the live production registry:
  - keyword: the original ToolRegistry.search tier scoring
  - bm25:    src.noesek.core.tool_rank.BM25 over name+description tokens

Usage: python -m evals.tool_retrieval [--json PATH] [--md PATH]
Exit code is always 0; this is a measurement harness, not a gate
(the gate lives in tests/test_tool_retrieval.py).
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finetune.cases import TEST_CASES
from noesek.core.controller import Controller
from noesek.core.tool_rank import BM25, tokenize


def _corpus(registry):
    names = [n for n in registry.names() if n != "search_tools"]
    docs = []
    for n in names:
        spec = registry.get(n)
        # Name tokens weigh double: a tool's own name is its strongest signal.
        docs.append(tokenize(n) * 2 + tokenize(spec.description or ""))
    return names, docs


def _keyword_rank(registry, query, limit):
    """Frozen re-implementation of the pre-BM25 tier ranking, kept as the
    baseline the eval measures against."""
    q = query.strip().lower()
    if not q:
        return []
    scored = []
    for n in registry.names():
        spec = registry.get(n)
        name, desc = n.lower(), (spec.description or "").lower()
        score = 3 if name == q else 2 if q in name else 1 if q in desc else 0
        if score:
            scored.append((score, n))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [n for _, n in scored[:limit]]


def _bm25_rank(bm25, names, query, limit):
    """The live production path: ToolRegistry.search (BM25)."""
    del bm25, names
    return _REGISTRY.search(query, limit)


def run() -> dict:
    global _REGISTRY
    registry = Controller(llm=None).registry(0)
    _REGISTRY = registry
    names, docs = _corpus(registry)
    bm25 = BM25(docs)
    cases = [c for c in TEST_CASES if not c["critical"] and c["calls"]]

    rankers = {"keyword": lambda q, k: _keyword_rank(registry, q, k),
               "bm25": lambda q, k: _bm25_rank(bm25, names, q, k)}
    report = {"tools": len(names), "cases": len(cases), "rankers": {}}

    for rname, rank in rankers.items():
        hits = {1: 0, 3: 0, 5: 0}
        per_tool = defaultdict(lambda: {"cases": 0, "top5": 0})
        confusion = Counter()
        misses = []
        for c in cases:
            expected = c["calls"][0]
            per_tool[expected]["cases"] += 1
            top5 = rank(c["query"], 5)
            for k in (1, 3, 5):
                if expected in top5[:k]:
                    hits[k] += 1
            if expected in top5:
                per_tool[expected]["top5"] += 1
            else:
                misses.append({"query": c["query"], "expected": expected, "got": top5})
            for other in top5:
                if other != expected:
                    confusion[(expected, other)] += 1
        n = len(cases)
        report["rankers"][rname] = {
            "top1": round(hits[1] / n, 4), "top3": round(hits[3] / n, 4),
            "top5": round(hits[5] / n, 4),
            "misses": misses,
            "worst_tools": sorted(
                ({"tool": t, "hit_rate": round(v["top5"] / v["cases"], 3)}
                 for t, v in per_tool.items() if v["top5"] < v["cases"]),
                key=lambda x: x["hit_rate"]),
            "top_confusions": [{"expected": e, "ranked_instead": o, "count": n_}
                               for (e, o), n_ in confusion.most_common(10)],
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write full report JSON here")
    ap.add_argument("--md", help="write a markdown summary here")
    args = ap.parse_args()
    report = run()
    for rname, r in report["rankers"].items():
        print(f"{rname}: top1={r['top1']:.1%} top3={r['top3']:.1%} top5={r['top5']:.1%} "
              f"({report['cases']} cases, {report['tools']} tools)")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
    if args.md:
        lines = ["# Tool-retrieval evaluation (Gorilla pattern)", "",
                 f"{report['cases']} frozen queries over {report['tools']} production tools.", ""]
        for rname, r in report["rankers"].items():
            lines += [f"## {rname}", f"- top-1 {r['top1']:.1%} / top-3 {r['top3']:.1%} / top-5 {r['top5']:.1%}",
                      f"- misses: {len(r['misses'])}", ""]
        Path(args.md).write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    main()
