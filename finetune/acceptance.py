"""Acceptance gate for tuned (or base) needle weights against noesek's tools.

Runs the frozen TEST_CASES through the SAME stub machinery production uses
(noesek.tools.needle_router._stub_for over the real registry), compares the
engine's proposed tool set per case, and prints the verdict against the bar:
>= 90% overall pass AND zero critical failures.

Usage (repo root, needs `pip install needle==3.0.4`):
    python -m finetune.acceptance                     # base weights (before)
    python -m finetune.acceptance --weights tuned.cact  # tuned (after)
    python -m finetune.acceptance --weights tuned.cact --json out.json

One engine.run is ~10-15s of CPU, so a full 88-case pass is ~20 min. Use
--category or --limit for a quick smoke while iterating.
"""
import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.append(os.path.join(_ROOT, "vendor", "hermes-agent"))

from finetune.cases import PASS_BAR, TEST_CASES  # noqa: E402
from finetune.dump_tools import production_specs  # noqa: E402


def run(cases, weights=None, max_steps=3):
    os.environ["NEEDLE_TELEMETRY"] = "0"
    import needle
    from noesek.tools.needle_router import _stub_for

    specs = production_specs()
    stubs = [_stub_for(s) for s in specs]
    engine = needle.Needle(tools=stubs, weights=weights)
    results = []
    for i, case in enumerate(cases, 1):
        try:
            resp = engine.run(case["query"], max_steps=max_steps)
            names = sorted({
                fc["name"] for fc in (resp.get("function_calls") or [])
                if isinstance(fc, dict) and fc.get("name")
            })
        except Exception as exc:  # engine error = failed case, never crash the run
            names, resp = [], {"error": str(exc)}
        expected = case["calls"]
        passed = names == expected
        results.append({**case, "got": names, "passed": passed})
        flag = "ok " if passed else ("CRIT" if case["critical"] else "FAIL")
        print(f"[{i}/{len(cases)}] {flag} {case['category']:<9} "
              f"want={expected} got={names} :: {case['query'][:60]}", flush=True)
    return results


def per_tool_report(results):
    """Per-tool trust table for the free auto-execute gate: for every tool,
    hits (proposed when expected), misses (expected but not proposed) and
    false fires (proposed when NOT expected, with the query as evidence).
    A tool qualifies for auto-execute only with high hit rate AND zero
    false fires on critical-leaning traffic - see docs/NEEDLE_TUNING.md."""
    table = {}
    for r in results:
        expected = set(r["calls"])
        got = set(r["got"])
        for name in expected | got:
            row = table.setdefault(name, {"expected": 0, "hit": 0, "false_fire": []})
        for name in expected:
            table[name]["expected"] += 1
            if name in got:
                table[name]["hit"] += 1
        for name in got - expected:
            table[name]["false_fire"].append(r["query"][:80])
    return table


def verdict(results):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    crit_fail = [r for r in results if r["critical"] and not r["passed"]]
    rate = passed / total if total else 0.0
    ok = rate >= PASS_BAR and not crit_fail
    return {
        "verdict": "PASS" if ok else "FAIL",
        "pass_rate": round(rate, 4),
        "passed": passed,
        "total": total,
        "critical_failures": [r["query"] for r in crit_fail],
        "bar": f">= {PASS_BAR:.0%} pass and zero critical failures",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=None, help="tuned .cact; omit for base weights")
    ap.add_argument("--category", default=None, help="only run one category")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", default=None, help="write full results JSON here")
    args = ap.parse_args()
    cases = TEST_CASES
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]
    results = run(cases, weights=args.weights)
    v = verdict(results)
    v["per_tool"] = per_tool_report(results)
    print(json.dumps(v, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"verdict": v, "results": results}, f, indent=2)
    sys.exit(0 if v["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
