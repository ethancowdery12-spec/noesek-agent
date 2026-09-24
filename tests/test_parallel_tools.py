"""Tests for LLMCompiler M1: concurrent read-only tool batches (batch 3)."""
import asyncio

from pydantic import BaseModel

from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import LLMReply, Risk, ToolCall
from noesek.db import Conversation, Session
from noesek.testing import ScriptedLLM, text_reply, tool_reply


class Q(BaseModel):
    q: str = "x"


async def _conv():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); return c.id


def _multi(*calls):
    return LLMReply(content="", tool_calls=[ToolCall(id=f"c{i}", name=n, arguments=a)
                                            for i, (n, a) in enumerate(calls)])


def _factory(delay=0.05, tracker=None):
    async def search(inp):
        if tracker is not None:
            tracker["cur"] += 1
            tracker["peak"] = max(tracker["peak"], tracker["cur"])
            await asyncio.sleep(delay)
            tracker["cur"] -= 1
        return {"results": [{"title": "t", "url": f"https://example.com/{inp.q}"}]}

    async def write_thing(inp):
        return {"ok": True}

    def factory(cid):
        r = ToolRegistry()
        r.register(ToolSpec("search", "d", Q, Risk.READ, search))
        r.register(ToolSpec("lookup", "d", Q, Risk.READ, search))
        r.register(ToolSpec("write_thing", "d", Q, Risk.WRITE, write_thing))
        return r
    return factory


async def test_read_batch_runs_concurrently(db):
    cid = await _conv()
    tracker = {"cur": 0, "peak": 0}
    llm = ScriptedLLM([_multi(("search", {"q": "a"}), ("lookup", {"q": "b"}), ("search", {"q": "c"})),
                       text_reply("done")])
    c = Controller(llm=llm, registry_factory=_factory(tracker=tracker))
    r = await c.handle(cid, "research three things")
    assert r.text == "done"
    assert tracker["peak"] == 3  # all three in flight at once
    assert set(r.citations) == {"https://example.com/a", "https://example.com/b", "https://example.com/c"}
    # results appended in request order
    tool_msgs = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c0", "c1", "c2"]


async def test_mixed_round_keeps_sequential_approval_semantics(db):
    cid = await _conv()
    llm = ScriptedLLM([_multi(("search", {"q": "a"}), ("write_thing", {"q": "b"}))])
    c = Controller(llm=llm, registry_factory=_factory())
    r = await c.handle(cid, "search then write")
    assert r.pending_approval_id is not None  # write paused for approval like before


async def test_unknown_tool_falls_back_to_sequential(db):
    cid = await _conv()
    llm = ScriptedLLM([_multi(("search", {"q": "a"}), ("nope", {})), text_reply("ok")])
    c = Controller(llm=llm, registry_factory=_factory())
    r = await c.handle(cid, "x")
    assert r.text == "ok"
    tool_msgs = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert any("unknown tool" in m["content"] for m in tool_msgs)


async def test_loop_guard_intervention_uses_sequential_path(db):
    cid = await _conv()
    # three identical calls in one round trips the identical-call guard
    llm = ScriptedLLM([_multi(("search", {"q": "same"}), ("search", {"q": "same"}), ("search", {"q": "same"})),
                       text_reply("recovered")])
    c = Controller(llm=llm, registry_factory=_factory())
    r = await c.handle(cid, "x")
    assert r.text in ("recovered",) or "stopped" in r.text.lower()
    if r.text == "recovered":
        tool_msgs = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"]
        assert any("loop_guard" in m["content"] for m in tool_msgs)


async def test_parallel_error_streak_stops_turn(db):
    cid = await _conv()

    async def fail(inp):
        raise RuntimeError("backend down")

    def factory(c2):
        r = ToolRegistry()
        for n in ("search", "lookup", "search2"):
            r.register(ToolSpec(n, "d", Q, Risk.READ, fail))
        return r
    llm = ScriptedLLM([_multi(("search", {"q": "a"}), ("lookup", {"q": "b"}), ("search2", {"q": "c"}))])
    c = Controller(llm=llm, registry_factory=factory)
    r = await c.handle(cid, "x")
    assert "did not work" in r.text
