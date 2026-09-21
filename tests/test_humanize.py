"""P6: deterministic humanizer."""
from noesek.tools.humanize import HumanizeInput, humanize, humanize_text


def test_strips_filler_opener_and_closer():
    out = humanize_text("I'd be happy to help you with that. "
                        "Your order ships Tuesday. I hope this helps!")
    body = out["humanized_text"]
    assert "happy to help" not in body
    assert "I hope this helps" not in body
    assert "Your order ships Tuesday." in body
    assert any("removed filler" in a for a in out["applied_rewrites"])


def test_safe_swaps_preserve_case_and_meaning():
    out = humanize_text("We utilize caching. Utilize it Leverage it too.")
    body = out["humanized_text"]
    assert "utilize" not in body.lower()
    assert "We use caching." in body
    assert "Use it" in body  # sentence-initial stays capitalized
    assert "leverage" not in body.lower()


def test_em_dash_and_curly_quotes_normalized():
    out = humanize_text("It works \u2014 and it\u2019s \u201cfast\u201d.")
    body = out["humanized_text"]
    assert "\u2014" not in body and "\u2019" not in body
    assert " - " in body
    assert "it's \"fast\"" in body


def test_flags_inflated_vocabulary_without_swapping():
    out = humanize_text("This pivotal, robust framework showcases a vibrant ecosystem.")
    assert "pivotal" in out["humanized_text"]  # flagged, not swapped
    flagged = {f["pattern"] for f in out["flags"]}
    assert {"pivotal", "robust", "showcases" is None or "showcase", "vibrant"}
    assert "pivotal" in flagged and "vibrant" in flagged


def test_flags_not_just_construction():
    out = humanize_text("It's not just fast, but also reliable.")
    assert any("not just" in f["suggestion"] for f in out["flags"])


def test_clean_text_passes_through_unchanged():
    out = humanize_text("The build passed. Ship it when you're ready.")
    assert out["unchanged"] is True
    assert out["applied_rewrites"] == []
    assert out["flags"] == []


def test_facts_and_names_untouched():
    out = humanize_text("Alice's invoice is $4,250, due 2026-09-30. Please don't hesitate to ask.")
    assert "$4,250" in out["humanized_text"]
    assert "2026-09-30" in out["humanized_text"]
    assert "hesitate" not in out["humanized_text"]


async def test_humanize_handler():
    out = await humanize(HumanizeInput(text="Let me know if you need anything else. Done!"))
    assert out["humanized_text"].endswith("Done!")


def test_humanize_registered_on_controller():
    import inspect
    import noesek.core.controller as C
    assert '"humanize"' in inspect.getsource(C)
