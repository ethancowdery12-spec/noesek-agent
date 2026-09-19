"""Stage A: durable turn spine (typed, ordered, write-ahead event log)."""
import pytest
from pydantic import BaseModel
from sqlalchemy import select

from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core import turn_spine
from noesek.core.turn_spine import TurnSpine, get_turn_events, render_turn
from noesek.core.types import LLMReply, Risk
from noesek.db import Conversation, Session, TurnEvent
from noesek.testing import ScriptedLLM, text_reply, tool_reply


class Q(BaseModel): q: str = "x"
class W(BaseModel): v: int = 1


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def _events(turn_id):
    return await get_turn_events(turn_id)


def read_factory(results=None, calls=None):
    async def search(inp):
        if calls is not None: calls.append(dict(inp.model_dump()))
        return {"results": results or []}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec("search", "d", Q, Risk.READ, search)); return r
    return factory


def write_factory(calls):
    async def write(inp):
        calls.append(dict(inp.model_dump())); return {"ok": True}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec("write_thing", "d", W, Risk.WRITE, write)); return r
    return factory


async def test_event_sequence_for_tool_turn(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("search", {"q": "ai"}), text_reply("done")]),
                   registry_factory=read_factory())
    r = await c.handle(cid, "research ai")
    kinds = [e.kind for e in await _events(r.turn_id)]
    assert kinds == [turn_spine.TURN_STARTED, turn_spine.MODEL_REQUEST, turn_spine.MODEL_RESPONSE,
                     turn_spine.TOOL_CALL_REQUESTED, turn_spine.TOOL_CALL_RESULT,
                     turn_spine.MODEL_REQUEST, turn_spine.MODEL_RESPONSE, turn_spine.TURN_COMPLETED]


async def test_seq_is_monotonic_and_unique(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("search", {}), text_reply("done")]),
                   registry_factory=read_factory())
    r = await c.handle(cid, "x")
    seqs = [e.seq for e in await _events(r.turn_id)]
    assert seqs == list(range(1, len(seqs) + 1))
    assert all(e.turn_id == r.turn_id for e in await _events(r.turn_id))


async def test_write_ahead_requested_precedes_execution(db):
    cid = await _conv()
    calls = []
    c = Controller(llm=ScriptedLLM([tool_reply("search", {"q": "x"}), text_reply("done")]),
                   registry_factory=read_factory(calls=calls))
    r = await c.handle(cid, "x")
    assert calls == [{"q": "x"}]
    events = await _events(r.turn_id)
    requested = next(e for e in events if e.kind == turn_spine.TOOL_CALL_REQUESTED)
    result = next(e for e in events if e.kind == turn_spine.TOOL_CALL_RESULT)
    assert requested.seq < result.seq
    assert requested.data["tool"] == "search" and requested.data["risk"] == "read"
    assert '"q": "x"' in requested.data["arguments_json"]
    assert result.data["ok"] is True


async def test_strict_write_failure_blocks_side_effect(db, monkeypatch):
    cid = await _conv()
    calls = []
    c = Controller(llm=ScriptedLLM([tool_reply("search", {"q": "x"}), text_reply("done")]),
                   registry_factory=read_factory(calls=calls))

    class FailingSession:
        async def __aenter__(self): raise RuntimeError("db down")
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(turn_spine, "Session", FailingSession)
    with pytest.raises(turn_spine.SpineWriteError):
        await c.handle(cid, "x")
    assert calls == []  # the side effect never ran


async def test_genai_attributes_on_model_events(db):
    cid = await _conv()
    reply = text_reply("hi")
    reply.usage = {"input_tokens": 11, "output_tokens": 7}
    reply.finish_reason = "stop"
    c = Controller(llm=ScriptedLLM([reply]))
    r = await c.handle(cid, "hello")
    events = await _events(r.turn_id)
    req = next(e for e in events if e.kind == turn_spine.MODEL_REQUEST)
    resp = next(e for e in events if e.kind == turn_spine.MODEL_RESPONSE)
    assert "gen_ai.system" in req.data and "gen_ai.request.model" in req.data
    assert resp.data["gen_ai.usage.input_tokens"] == 11
    assert resp.data["gen_ai.usage.output_tokens"] == 7
    assert resp.data["gen_ai.response.finish_reasons"] == ["stop"]


async def test_approval_flow_events(db):
    cid = await _conv()
    calls = []
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 3})]),
                   registry_factory=write_factory(calls))
    r = await c.handle(cid, "do the write")
    assert r.pending_approval_id is not None
    kinds = [e.kind for e in await _events(r.turn_id)]
    assert turn_spine.APPROVAL_REQUIRED in kinds and turn_spine.TOOL_CALL_RESULT not in kinds
    assert calls == []  # gated: nothing ran yet

    r2 = await c.decide_approval(cid, r.pending_approval_id, True)
    assert calls == [{"v": 3}]
    kinds2 = [e.kind for e in await _events(r2.turn_id)]
    assert turn_spine.APPROVAL_DECIDED in kinds2
    assert turn_spine.TOOL_CALL_REQUESTED in kinds2 and turn_spine.TOOL_CALL_RESULT in kinds2
    assert kinds2.index(turn_spine.TOOL_CALL_REQUESTED) < kinds2.index(turn_spine.TOOL_CALL_RESULT)


async def test_max_steps_stop_event(db):
    cid = await _conv()
    script = [tool_reply("search", {"q": "x"}, call_id=f"c{i}") for i in range(8)]
    c = Controller(llm=ScriptedLLM(script), registry_factory=read_factory(), max_steps=2)
    r = await c.handle(cid, "loop")
    kinds = [e.kind for e in await _events(r.turn_id)]
    assert kinds[-1] == turn_spine.TURN_STOPPED
    assert "maximum tool steps" in r.text


async def test_render_turn_deterministic(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([text_reply("hi")]))
    r = await c.handle(cid, "hello")
    text1 = render_turn(await _events(r.turn_id))
    text2 = render_turn(await _events(r.turn_id))
    assert text1 == text2
    assert "turn_started" in text1 and "turn_completed" in text1


async def test_spine_data_redacts_secret_keys(db):
    spine = TurnSpine(1, turn_id="t-redact")
    await spine.emit(turn_spine.TURN_STARTED, {"api_key": "secret", "chars": 3})
    events = await _events("t-redact")
    assert events[0].data["api_key"] == "[REDACTED]"
    assert events[0].data["chars"] == 3


def test_normalize_usage_openai_shape():
    from noesek.core.llm import normalize_usage
    assert normalize_usage({"usage": {"prompt_tokens": 5, "completion_tokens": 2}}) == {"input_tokens": 5, "output_tokens": 2}
    assert normalize_usage({}) == {"input_tokens": None, "output_tokens": None}
