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


# --- Sep 21 live-acceptance regressions ---

async def test_approval_lifecycle_marked_persisted_and_visible(db):
    """Approval prompts AND outcomes are [system]-marked and stay in the transcript;
    assemble() injects the authoritative live approval state (approval-confabulation fix)."""
    from noesek.core.context import assemble
    cid = await _conv()
    async def handler(inp): return {"ok": True}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("write_thing", "d", W, Risk.WRITE, handler)); return r
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 1})]), registry_factory=factory)
    r = await c.handle(cid, "do the write")
    assert r.pending_approval_id is not None and r.text.startswith("[system] Approval required")
    out = await c.decide_approval(cid, r.pending_approval_id, True)
    assert out.text.startswith("[system]") and "executed" in out.text
    async with Session() as s:
        texts = [m.content for m in (await s.execute(select(Message).where(Message.conversation_id == cid).order_by(Message.id))).scalars().all()]
    assert any(t.startswith("[system] Approval required") for t in texts), texts
    assert any(t.startswith("[system] Approval #") and "executed" in t for t in texts), texts
    async with Session() as s:
        assembled = await assemble(s, cid, query="x")
    sysmsg = assembled[0]["content"]
    assert "Live approval state" in sysmsg and "write_thing" in sysmsg and "executed" in sysmsg

async def test_rejected_approval_also_persisted(db):
    cid = await _conv()
    async def handler(inp): return {"ok": True}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("write_thing", "d", W, Risk.WRITE, handler)); return r
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 1})]), registry_factory=factory)
    r = await c.handle(cid, "do the write")
    out = await c.decide_approval(cid, r.pending_approval_id, False)
    assert out.text.startswith("[system] Rejected")
    async with Session() as s:
        texts = [m.content for m in (await s.execute(select(Message).where(Message.conversation_id == cid))).scalars().all()]
    assert any(t.startswith("[system] Rejected approval #") for t in texts)

async def test_error_streak_stop_text_hides_tool_details(db):
    """Loop-guard stop text must not leak tool names or raw exceptions (narration rule)."""
    cid = await _conv()
    async def bad(inp): raise RuntimeError("raw-internal-detail")
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("fragile_tool", "d", Q, Risk.READ, bad)); return r
    llm = ScriptedLLM([tool_reply("fragile_tool", {"q": f"v{i}"}, call_id=f"e{i}") for i in range(4)] + [text_reply("done")])
    c = Controller(llm=llm, registry_factory=factory)
    r = await c.handle(cid, "go")
    assert "did not work" in r.text
    assert "fragile_tool" not in r.text and "raw-internal-detail" not in r.text and "Exception" not in r.text

async def test_identical_loop_stop_text_hides_tool_details(db):
    cid = await _conv()
    async def ok(inp): return {"results": []}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("search", "d", Q, Risk.READ, ok)); return r
    llm = ScriptedLLM([tool_reply("search", {"q": "same"}, call_id=f"s{i}") for i in range(4)] + [text_reply("done")])
    c = Controller(llm=llm, registry_factory=factory)
    r = await c.handle(cid, "go")
    assert "repeating the same action" in r.text and "search" not in r.text.split("repeating")[0]

def test_switch_model_description_reflects_live_catalog(db):
    from noesek.core.llm import allowed_models, model_catalog
    c = Controller(llm=ScriptedLLM([]))
    spec = c.registry(1).get("switch_model")
    assert model_catalog()["chat"] in spec.description
    assert "configured:" in spec.description
    for m in allowed_models():
        assert m in spec.description
