"""Stage D: memory v2 - typed memories, FTS search, compaction transitions, untrusted wrapping."""
from pydantic import BaseModel
from sqlalchemy import select

from noesek.core import turn_spine
from noesek.core.context import assemble
from noesek.core.controller import Controller
from noesek.core.memory_v2 import fts_available, fts_search_ids, wrap_untrusted
from noesek.core.turn_spine import get_turn_events
from noesek.core.types import Risk
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.db import Compaction, Conversation, Memory, Message, Session
from noesek.testing import ScriptedLLM, tool_reply, text_reply
from noesek.tools.state import (
    ForgetInput, RecallInput, RememberInput, SupersedeInput,
    forget_handler, memory_handler, recall_handler, supersede_handler,
)


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def test_typed_remember_and_recall(db):
    cid = await _conv()
    r = await memory_handler(cid)(RememberInput(content="favorite tea is oolong", kind="preference"))
    assert r["kind"] == "preference"
    async with Session() as s:
        m = (await s.execute(select(Memory).where(Memory.id == r["memory_id"]))).scalar_one()
        assert m.kind == "preference" and m.source == "conversation" and m.superseded_by is None
    out = await recall_handler(cid)(RecallInput(query="tea"))
    assert out["memories"][0]["kind"] == "preference"


async def test_invalid_kind_rejected(db):
    cid = await _conv()
    r = await memory_handler(cid)(RememberInput(content="x", kind="bogus"))
    assert "error" in r


async def test_supersede_invalidates_not_overwrites(db):
    cid = await _conv()
    r1 = await memory_handler(cid)(RememberInput(content="deploy host is a vps", kind="fact"))
    r2 = await supersede_handler(cid)(SupersedeInput(memory_id=r1["memory_id"], content="deploy host is fly.io"))
    assert r2["superseded"] and r2["old_memory_id"] == r1["memory_id"]
    async with Session() as s:
        old = (await s.execute(select(Memory).where(Memory.id == r1["memory_id"]))).scalar_one()
        assert old.active is False and old.superseded_by == r2["memory_id"]
        assert old.content == "deploy host is a vps"  # kept, not overwritten
    out = await recall_handler(cid)(RecallInput(query="deploy host"))
    assert [m["id"] for m in out["memories"]] == [r2["memory_id"]]


async def test_fts_search_when_available(db):
    cid = await _conv()
    if not await fts_available():
        import pytest; pytest.skip("SQLite build without FTS5")
    r = await memory_handler(cid)(RememberInput(content="favorite color is blue", kind="fact"))
    ids = await fts_search_ids(cid, "favorite color", 5)
    assert r["memory_id"] in ids
    # forget deindexes
    await forget_handler(cid)(ForgetInput(memory_id=r["memory_id"]))
    assert r["memory_id"] not in await fts_search_ids(cid, "favorite color", 5)


async def test_compaction_is_persisted_and_visible(db):
    cid = await _conv()
    async with Session() as s:
        for i in range(10):
            s.add(Message(conversation_id=cid, role="user", content="z" * 100))
        await s.commit()
        msgs = await assemble(s, cid, query="hi", char_budget=400)
    assert "older messages omitted" in msgs[0]["content"] and "compaction #" in msgs[0]["content"]
    async with Session() as s:
        rows = (await s.execute(select(Compaction).where(Compaction.conversation_id == cid))).scalars().all()
    assert len(rows) == 1 and rows[0].removed_count >= 5
    assert rows[0].oldest_dropped_id is not None


async def test_compaction_on_spine_when_passed(db):
    cid = await _conv()
    spine = turn_spine.TurnSpine(cid, turn_id="t-compact")
    async with Session() as s:
        for i in range(10):
            s.add(Message(conversation_id=cid, role="user", content="z" * 100))
        await s.commit()
        await assemble(s, cid, query="hi", char_budget=400, spine=spine)
    kinds = [e.kind for e in await get_turn_events("t-compact")]
    assert "compaction" in kinds


class Q(BaseModel): q: str = "x"


async def test_tool_results_wrapped_untrusted(db):
    cid = await _conv()
    async def search(inp): return {"results": [{"title": "t", "url": "https://example.com"}]}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("search", "d", Q, Risk.READ, search)); return r
    llm = ScriptedLLM([tool_reply("search", {"q": "x"}), text_reply("done")])
    c = Controller(llm=llm, registry_factory=factory)
    await c.handle(cid, "x")
    tool_msg = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["content"].startswith('<untrusted_content source="search">')
    assert "https://example.com" in tool_msg["content"]  # content passed as data


def test_wrap_untrusted_sanitizes_source():
    out = wrap_untrusted("body", 'web"><script>')
    assert out == '<untrusted_content source="webscript">\nbody\n</untrusted_content>'


async def test_supersede_tool_registered_and_gated(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("supersede_memory", {"memory_id": 1, "content": "new"})]))
    r = await c.handle(cid, "correct my memory")
    assert r.pending_approval_id is not None  # WRITE risk -> approval lease
