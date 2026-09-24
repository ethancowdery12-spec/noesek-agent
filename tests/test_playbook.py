"""Tests for the playbook tool (roadmap item 55)."""
from noesek.tools.playbook import PLAYBOOKS, PlaybookInput, playbook


def test_list_and_load():
    out = playbook(PlaybookInput(action="list"))
    assert set(out["playbooks"]) == {"interview_coach", "debate", "writing_tutor", "teacher", "critic", "terse", "spec_first", "tdd_flow", "verify_done", "storyscope", "reason_route", "seo_web",
                                    "budget_tracker", "fitness_log", "nutrition_lookup", "meal_planner", "spaced_repetition_tutor", "trip_planner",
                                    "birthdays"}
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


def test_life_consumer_briefs_carry_guardrails():
    # batch 4 tranche 1 (item 87): life/consumer playbooks distilled from the
    # MIT/public-domain sources in the batch-4 research (actualbudget,
    # free-exercise-db, openfoodfacts, py-fsrs, OSM stack). Guardrails from the
    # batch-4 brief must survive in the briefs themselves.
    b = PLAYBOOKS["budget_tracker"]["brief"].lower()
    assert "explicit approval" in b and "not professional financial advice" in b
    assert "kind='expense'" in b
    b = PLAYBOOKS["fitness_log"]["brief"].lower()
    assert "no medical" in b and "kind='workout'" in b
    b = PLAYBOOKS["nutrition_lookup"]["brief"].lower()
    assert "ask a" in b and "professional" in b and "kind='nutrition'" in b
    b = PLAYBOOKS["trip_planner"]["brief"].lower()
    assert "explicit approval" in b and "total shown" in b
    assert "if a source fails" in b  # scraper graceful-failure guardrail
    b = PLAYBOOKS["spaced_repetition_tutor"]["brief"].lower()
    assert "again" in b and "interval" in b and "kind='flashcard'" in b


def test_birthdays_brief_carries_date_handling():
    # batch 4 tranche 2: birthdays playbook - dates as memories, holidays never guessed.
    b = PLAYBOOKS["birthdays"]["brief"].lower()
    assert "kind='important_date'" in b and "weekday" in b
    assert "never guess" in b  # public-holiday guardrail
