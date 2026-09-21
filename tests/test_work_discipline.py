"""Study queue batch 1: work-discipline block in the system prompt."""
from noesek.core.context import SYSTEM


def test_system_prompt_has_acceptance_gate_rule():
    assert "checks that prove it is done" in SYSTEM


def test_system_prompt_has_assumption_surfacing_rule():
    assert "Surface wrong assumptions, inconsistencies, and tradeoffs" in SYSTEM


def test_system_prompt_has_yagni_rule():
    assert "smallest change that fully satisfies" in SYSTEM
    assert "no speculative features" in SYSTEM


def test_roadmap_batch1_items_closed():
    doc = open("docs/RESEARCH_ROADMAP.md").read()
    for marker in ("**4. Anti-laziness: Unlazy**", "**5. Anti-laziness: Ponytail**",
                   "**8. Karpathy coding rules**", "**20. NVIDIA cross-model KV cache transfer**",
                   "**38. Playwright CLI**", "**40. Unnamed \"browser stuff\" repo**"):
        line = next(l for l in doc.splitlines() if marker in l)
        assert line.startswith("- [x]"), marker
