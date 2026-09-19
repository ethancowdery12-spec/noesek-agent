import json
import pytest
from pydantic import BaseModel
from sqlalchemy import select
from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Conversation, Message, Session
from noesek.testing import ScriptedLLM, text_reply, tool_reply

class Q(BaseModel): q: str = "x"
class W(BaseModel): v: int = 1

async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id

def search_factory(results):
    async def search(inp): return {"results": results}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec("search", "d", Q, Risk.READ, search)); return r
    return factory

async def test_direct_reply_stored(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([text_reply("hi there")]))
    r = await c.handle(cid, "hello")
    assert r.text == "hi there"
    async with Session() as s:
        roles = (await s.execute(select(Message.role).where(Message.conversation_id == cid))).scalars().all()
    assert roles == ["user", "assistant"]

async def test_tool_call_collects_citations(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("search", {"q": "ai"}), text_reply("summary")]),
                   registry_factory=search_factory([{"title": "t", "url": "https://example.com/a"}]))
    r = await c.handle(cid, "research ai")
    assert r.text == "summary" and r.citations == ["https://example.com/a"]

async def test_unknown_tool_reported_as_data(db):
    cid = await _conv()
    llm = ScriptedLLM([tool_reply("nope", {}), text_reply("fallback")])
    c = Controller(llm=llm, registry_factory=search_factory([]))
    r = await c.handle(cid, "x")
    assert r.text == "fallback"
    tool_msgs = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert "unknown tool" in tool_msgs[0]["content"]

async def test_write_tool_pauses_for_approval(db):
    cid = await _conv()
    async def handler(inp): return {"ok": True}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("write_thing", "d", W, Risk.WRITE, handler)); return r
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 1})]), registry_factory=factory)
    r = await c.handle(cid, "do the write")
    assert r.pending_approval_id is not None and "Approval required" in r.text

async def test_external_id_dedupe(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([text_reply("once")]))
    r1 = await c.handle(cid, "hello", external_id="wamid-1")
    r2 = await c.handle(cid, "hello", external_id="wamid-1")
    assert r1.text == "once" and r2.text == ""
    async with Session() as s:
        n = len((await s.execute(select(Message).where(Message.external_id == "wamid-1"))).scalars().all())
    assert n == 1

async def test_max_steps_stop(db):
    cid = await _conv()
    llm = ScriptedLLM([tool_reply("search", {"q": "a"}, call_id=f"c{i}") for i in range(5)])
    c = Controller(llm=llm, registry_factory=search_factory([]), max_steps=2)
    r = await c.handle(cid, "loop")
    assert "maximum tool steps" in r.text
