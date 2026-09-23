"""Tests for the playbook tool (roadmap item 55)."""
from noesek.tools.playbook import PLAYBOOKS, PlaybookInput, playbook


def test_list_and_load():
    out = playbook(PlaybookInput(action="list"))
    assert set(out["playbooks"]) == {"interview_coach", "debate", "writing_tutor", "teacher", "critic", "terse", "spec_first", "tdd_flow", "verify_done", "storyscope"}
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


def test_terse_mode_preserves_load_bearing_parts():
    # caveman (MIT skills/) studied Sep 22: our terse brief is own-words, but
    # must carry the two rules that make compression safe - code byte-exact,
    # structure intact.
    b = PLAYBOOKS["terse"]["brief"].lower()
    assert "byte-exact" in b
    assert "code" in b and "paths" in b and "urls" in b
    assert "structure stays" in b
    # own-words guard: zero phrasing lifted from the upstream skill file
    assert "why use many token" not in b
    assert "throat-clearing" in b  # our phrasing, present


def test_dev_workflow_briefs_carry_the_discipline():
    # superpowers (obra/superpowers, MIT) studied Sep 22: the adoptable core is
    # the discipline layer - spec before code, red/green TDD, verify before done.
    b1 = PLAYBOOKS["spec_first"]["brief"].lower()
    assert "out of scope" in b1 and "build nothing until" in b1
    b2 = PLAYBOOKS["tdd_flow"]["brief"].lower()
    assert "failing test first" in b2 and "smallest" in b2
    b3 = PLAYBOOKS["verify_done"]["brief"].lower()
    assert "real numbers" in b3 and "unverified" in b3
    # own-words guard against upstream phrasing
    for name in ("spec_first", "tdd_flow", "verify_done"):
        assert "enthusiastic junior engineer" not in PLAYBOOKS[name]["brief"].lower()
