"""Tests for the playbook tool (roadmap item 55)."""
from noesek.tools.playbook import PLAYBOOKS, PlaybookInput, playbook


def test_list_and_load():
    out = playbook(PlaybookInput(action="list"))
    assert set(out["playbooks"]) == {"interview_coach", "debate", "writing_tutor", "teacher", "critic"}
    loaded = playbook(PlaybookInput(action="load", name="debate"))
    assert loaded["loaded"] == "debate" and len(loaded["brief"]) > 100


def test_errors():
    assert "error" in playbook(PlaybookInput(action="load", name="nope"))
    assert "error" in playbook(PlaybookInput(action="bogus"))


def test_briefs_are_own_words():
    # prompts.chat entries open with the signature "I want you to act as" - our
    # distillations must share zero phrasing with the pack (CC0 or not).
    for name, pb in PLAYBOOKS.items():
        b = pb["brief"].lower()
        assert "i want you to act as" not in b, name
        assert "do not write explanations" not in b, name
        assert 200 < len(pb["brief"]) < 1200, name
