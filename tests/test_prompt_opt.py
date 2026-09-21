"""P5: deterministic prompt optimizer."""
from noesek.tools.prompt_opt import (OptimizePromptInput, detect_type,
                                     extract_constraints, optimize_prompt,
                                     optimize_prompt_text)


def test_detect_type_coding():
    assert detect_type("write a python function that parses csv") == "coding"


def test_detect_type_writing_and_hint():
    assert detect_type("draft an email to my landlord") == "writing"
    assert detect_type("make this better", hint="research") == "research"


def test_detect_type_general_fallback():
    assert detect_type("hello there friend") == "general"


def test_extract_constraints_finds_rules_and_quantities():
    cs = extract_constraints("Summarize this. Must be under 200 words. Never use jargon. Give me 3 examples.")
    joined = " ".join(cs).lower()
    assert "200 words" in joined
    assert "never use jargon" in joined
    assert "3 examples" in joined


def test_extract_constraints_empty_on_plain_text():
    assert extract_constraints("tell me about the moon") == []


def test_optimize_structure_and_grounding():
    out = optimize_prompt_text("Compare Postgres and SQLite for a small app. Must cite sources.")
    assert out["detected_type"] == "research"
    body = out["optimized_prompt"]
    for section in ("## Objective", "## Approach", "## Constraints", "## Ground rules", "## Output format"):
        assert section in body
    assert "Compare Postgres and SQLite" in body
    assert "must cite sources" in body.lower()
    assert "do not invent facts" in body
    assert "task-type detection" in out["applied_techniques"]


async def test_optimize_prompt_handler():
    out = await optimize_prompt(OptimizePromptInput(prompt="write a script that backs up my photos"))
    assert out["detected_type"] == "coding"
    assert "Working code" in out["optimized_prompt"]


def test_optimize_prompt_registered_on_controller():
    import inspect
    import noesek.core.controller as C
    src = inspect.getsource(C)
    assert '"optimize_prompt"' in src
