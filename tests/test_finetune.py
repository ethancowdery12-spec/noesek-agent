"""Pipeline unit tests for the needle fine-tuning lane (finetune/)."""
import json

from finetune.cases import TEST_CASES
from finetune.dump_tools import production_specs, to_needle_tools
from finetune.gen_data import subsets
from finetune.acceptance import verdict


def test_dump_matches_production_registry():
    specs = production_specs()
    names = [s.name for s in specs]
    assert len(specs) == 45, names
    for expected in ("gmail_send", "recall", "geo_audit", "switch_model"):
        assert expected in names
    tools = to_needle_tools(specs)
    for t in tools:
        assert set(t) == {"name", "description", "parameters"}
        assert t["parameters"].get("properties") is not None


def test_cases_cover_every_tool_and_only_known_tools():
    known = {t["name"] for t in to_needle_tools(production_specs())}
    used = {n for c in TEST_CASES for n in c["calls"]}
    assert used <= known
    assert used == known, f"uncovered tools: {known - used}"


def test_critical_cases_expect_refusal():
    criticals = [c for c in TEST_CASES if c["critical"]]
    assert len(criticals) >= 6
    assert all(c["calls"] == [] for c in criticals)


def test_subsets_rotate_targets_with_distractors():
    tools = [{"name": n, "description": "", "parameters": {}}
             for n in ("a", "b", "c", "d", "e", "f", "g", "h")]
    gen = subsets(tools, distractors=3, seed=1)
    targets = []
    for _ in range(8):
        target, subset = next(gen)
        targets.append(target)
        assert target in [t["name"] for t in subset]
        assert len(subset) == 4  # target + 3 distractors
    assert targets == list("abcdefgh")  # every tool targeted once per pass


def test_verdict_bar():
    ok = [{"passed": True, "critical": False}] * 91 + [{"passed": False, "critical": False}] * 9
    assert verdict(ok)["verdict"] == "PASS"
    crit = [{"passed": True, "critical": False}] * 99 + [
        {"passed": False, "critical": True, "query": "x"}]
    v = verdict(crit)
    assert v["verdict"] == "FAIL" and v["critical_failures"] == ["x"]
    low = [{"passed": True, "critical": False}] * 80 + [{"passed": False, "critical": False}] * 20
    assert verdict(low)["verdict"] == "FAIL"


def test_router_weights_path_env(monkeypatch, tmp_path):
    from noesek.tools import needle_router as nr
    monkeypatch.delenv("NOESEK_NEEDLE_WEIGHTS", raising=False)
    assert nr._weights_path() is None
    monkeypatch.setenv("NOESEK_NEEDLE_WEIGHTS", str(tmp_path / "tuned.cact"))
    assert nr._weights_path().endswith("tuned.cact")


def test_per_tool_report_counts_hits_and_false_fires():
    from finetune.acceptance import per_tool_report
    results = [
        {"query": "check my calendar", "calls": ["calendar_read"],
         "got": ["calendar_read"], "category": "positive", "critical": False},
        {"query": "what's up today", "calls": ["calendar_read"],
         "got": ["list_tasks"], "category": "positive", "critical": False},
        {"query": "email him", "calls": [], "got": ["gmail_send"],
         "category": "critical", "critical": True},
    ]
    table = per_tool_report(results)
    assert table["calendar_read"]["expected"] == 2
    assert table["calendar_read"]["hit"] == 1
    assert table["list_tasks"]["false_fire"] == ["what's up today"]
    assert table["gmail_send"]["false_fire"] == ["email him"]
