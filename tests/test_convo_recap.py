from noesek.tools.convo_recap import ConvoRecapInput as I, convo_recap as f

T = [dict(role="user", text="I need a Python function that parses invoices. It must handle CSV."),
     dict(role="assistant", text="```python\ndef parse(): pass\n```\nHere is the complete solution."),
     dict(role="user", text="Also, never use pandas. Keep it under 40 lines."),
     dict(role="assistant", text="Sure."),
     dict(role="user", text="Actually keep it under 60 lines. What do you think?")]


def test_recap_collects_requirements_in_order_and_skips_questions():
    r = f(I(turns=T))
    txt = [x["text"] for x in r["requirements"]]
    assert txt[0].startswith("I need a Python function") and any("never use pandas" in t for t in txt)
    assert not any("What do you think" in t for t in txt)
    assert r["recap_turn"].startswith("Here is everything") and "1. I need" in r["recap_turn"]


def test_flags_answered_early_and_conflicting_numbers():
    pats = {x["pattern"] for x in f(I(turns=T))["flags"]}
    assert {"answered_early", "conflicting_numbers"} <= pats
    c = [x for x in f(I(turns=T))["flags"] if x["pattern"] == "conflicting_numbers"][0]
    assert "40" in c["detail"] and "60" in c["detail"]


def test_long_reply_flag_and_dedupe():
    turns = [dict(role="user", text="Use 3 bullets. Use 3 bullets."), dict(role="assistant", text="word " * 400)]
    r = f(I(turns=turns))
    assert len(r["requirements"]) == 1 and any(x["pattern"] == "long_reply" for x in r["flags"])


def test_no_requirements_and_truncation():
    r = f(I(turns=[dict(role="assistant", text="hi")]))
    assert r["recap_turn"] == "" and r["user_turns"] == 0
    many = [dict(role="user", text=" ".join(f"Use item {n}." for n in range(10)))]
    r = f(I(turns=many, max_requirements=3))
    assert len(r["requirements"]) == 3 and r["truncated"] is True and r["executed"] is False
