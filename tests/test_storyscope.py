"""Item 60: storyscope playbook + story_critique tool (StoryScope, COLM 2026)."""
import pytest

from noesek.tools.playbook import PLAYBOOKS, PlaybookInput, playbook
from noesek.tools.story_critique import CHECKS, StoryCritiqueInput, story_critique_handler


def test_storyscope_playbook_counters_documented_ai_defaults():
    pb = PLAYBOOKS["storyscope"]
    brief = pb["brief"].lower()
    # the counters to the paper's core AI-typical findings must all be present
    for marker in ("theme", "lesson", "moral", "non-linear", "flashback", "ambiguous",
                   "loose end", "escalation", "epilogue", "afraid", "name real", "allusions"):
        assert marker in brief, f"storyscope brief missing counter for: {marker}"
    out = playbook(PlaybookInput(action="load", name="storyscope"))
    assert out["loaded"] == "storyscope" and "brief" in out


class _Reply:
    def __init__(self, content): self.content = content
    tool_calls = []


class _FakeLLM:
    def __init__(self, content): self._c = content; self.seen = None
    async def complete(self, messages, schemas):
        self.seen = messages[0]["content"]
        return _Reply(self._c)


@pytest.mark.asyncio
async def test_story_critique_rubric_and_parsing():
    payload = ('[{"check": "stated_theme", "verdict": "ai", "evidence": "narrator states the lesson", '
               '"suggestion": "cut the final paragraph"}, '
               '{"check": "linear_time", "verdict": "human", "evidence": "opens at the funeral", '
               '"suggestion": "keep it"}]')
    fake = _FakeLLM(payload)
    async def resolver(): return fake
    story = "Word " * 60 + "and in the end she learned that grief makes us whole."
    out = await story_critique_handler(resolver)(StoryCritiqueInput(story=story))
    assert out["ai_typical"] == 1 and out["human_typical"] == 1
    assert out["checks"][0]["check"] == "stated_theme"
    # every rubric check reached the model
    for name, _ in CHECKS:
        assert f'"{name}"' in fake.seen


@pytest.mark.asyncio
async def test_story_critique_unparseable_degrades():
    fake = _FakeLLM("I think your story is lovely.")
    async def resolver(): return fake
    out = await story_critique_handler(resolver)(StoryCritiqueInput(story="Word " * 60))
    assert "error" in out and "raw_head" in out


def test_rubric_covers_paper_findings():
    names = {n for n, _ in CHECKS}
    assert {"stated_theme", "tidy_ending", "linear_time", "single_track", "clean_hero",
            "bodily_emotion", "vague_references", "flat_escalation"} <= names
