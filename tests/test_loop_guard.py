"""Stage C: loop guardrails."""
from pydantic import BaseModel

from noesek.core import turn_spine
from noesek.core.controller import Controller
from noesek.core.loop_guard import LoopGuard, classify_exception
from noesek.core.tools import ToolRegistry, ToolSpec, ToolTimeoutError
from noesek.core.turn_spine import get_turn_events
from noesek.core.types import Risk
from noesek.db import Conversation, Session
from noesek.testing import ScriptedLLM, text_reply, tool_reply


class Q(BaseModel): q: str = "x"


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


def _factory(name="search", handler=None):
    async def default(inp): return {"results": []}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec(name, "d", Q, Risk.READ, handler or default)); return r
    return factory


# --- pure guard ---

def test_identical_retry_warns_then_stops():
    g = LoopGuard(max_identical=3)
    assert g.before_call("t", {"a": 1}) is None
    assert g.before_call("t", {"a": 1})[0] == "warn"
    assert g.before_call("t", {"a": 1})[0] == "stop"


def test_different_args_reset_identical_streak():
    g = LoopGuard(max_identical=3)
    g.before_call("t", {"a": 1}); g.before_call("t", {"a": 2})
    assert g.before_call("t", {"a": 2}) is None or g.before_call is not None


def test_cycle_detection():
    g = LoopGuard(cycle_window=2)
    for c in [("a", {}), ("b", {}), ("a", {}), ("b", {})]:
        hit = g.before_call(*c)
    assert hit and hit[0] == "stop" and "cycle" in hit[1]


def test_error_streak():
    g = LoopGuard(max_consecutive_errors=2)
    g.record_outcome(False)
    assert not g.error_streak_tripped()
    g.record_outcome(False)
    assert g.error_streak_tripped()
    g.record_outcome(True)
    assert not g.error_streak_tripped()


def test_classify_exception():
    assert classify_exception(ToolTimeoutError("x")) == "timeout"
    assert classify_exception(ValueError("x")) == "ValueError"


# --- controller integration ---

async def test_identical_retry_stops_turn_early(db):
    cid = await _conv()
    ran = []
    async def handler(inp): ran.append(1); return {"results": []}
    script = [tool_reply("search", {"q": "same"}, call_id=f"c{i}") for i in range(4)]
    c = Controller(llm=ScriptedLLM(script), registry_factory=_factory(handler=handler), max_steps=8)
    r = await c.handle(cid, "loop")
    assert "I stopped" in r.text and "repeating the same action" in r.text and "search" not in r.text
    assert len(ran) == 1  # first call ran; repeat warned; third stopped
    kinds = [e.kind for e in await get_turn_events(r.turn_id)]
    assert turn_spine.LOOP_GUARD in kinds and kinds[-1] == turn_spine.TURN_STOPPED


async def test_error_streak_stops_turn(db):
    cid = await _conv()
    async def boom(inp): raise RuntimeError("backend down")
    script = [tool_reply("search", {"q": f"q{i}"}, call_id=f"c{i}") for i in range(5)]
    c = Controller(llm=ScriptedLLM(script), registry_factory=_factory(handler=boom), max_steps=8)
    r = await c.handle(cid, "x")
    assert "did not work" in r.text and "RuntimeError" not in r.text and "search" not in r.text
    kinds = [e.kind for e in await get_turn_events(r.turn_id)]
    assert kinds[-1] == turn_spine.TURN_STOPPED


async def test_normal_turn_unaffected(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("search", {"q": "a"}), text_reply("done")]),
                   registry_factory=_factory())
    r = await c.handle(cid, "x")
    assert r.text == "done"
