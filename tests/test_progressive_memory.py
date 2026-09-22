"""Item 58: memory progressive disclosure + session auto-distill (claude-mem
core, own implementation). recall returns a compact index; memory_get fetches
full text by id; compaction auto-distills a durable session-summary memory."""
import pytest
from sqlalchemy import delete, select

from noesek.db import Compaction, Conversation, Memory, Message, Session, init_db, migrate
from noesek.tools.state import MemoryGetInput, RecallInput, memory_get_handler, recall_handler


@pytest.fixture()
async def clean(db):
    await init_db(); await migrate()
    async with Session() as s:
        for t in (Message, Memory, Compaction, Conversation):
            await s.execute(delete(t))
        await s.commit()
    yield


async def _conv(ext="u1"):
    async with Session() as s:
        c = Conversation(channel="web", external_user_id=ext)
        s.add(c); await s.commit(); await s.refresh(c)
        return c.id


@pytest.mark.asyncio
async def test_recall_returns_compact_index_memory_get_returns_full(clean):
    cid = await _conv()
    long_content = "Favorite tea is green tea. " * 20  # > 140 chars
    async with Session() as s:
        m = Memory(conversation_id=cid, kind="preference", content=long_content)
        s.add(m); await s.commit(); await s.refresh(m)
        mid = m.id
    out = await recall_handler(cid)(RecallInput(query="green tea"))
    assert out["memories"], "recall found nothing"
    hit = out["memories"][0]
    assert hit["id"] == mid and set(hit) == {"id", "kind", "preview", "created_at"}
    assert len(hit["preview"]) <= 143 and hit["preview"].endswith("...")
    assert "content" not in hit
    got = await memory_get_handler(cid)(MemoryGetInput(ids=[mid]))
    assert got["memories"][0]["content"] == long_content


@pytest.mark.asyncio
async def test_auto_distill_writes_one_handoff_and_is_idempotent(clean):
    cid = await _conv()
    async with Session() as s:
        ids = []
        for i in range(5):
            m = Message(conversation_id=cid, role="user" if i % 2 == 0 else "assistant",
                        content=f"planning step {i}: build the deck")
            s.add(m); await s.commit(); await s.refresh(m)
            ids.append(m.id)
        c = Compaction(conversation_id=cid, removed_count=5, budget_chars=1000,
                       oldest_dropped_id=ids[0], newest_dropped_id=ids[-1])
        s.add(c); await s.commit()

    async def fake_summarize(tx: str) -> str:
        assert "planning step" in tx
        return "User is building a deck; steps 0-4 discussed; nothing decided yet."

    from noesek.core.memory_v2 import auto_distill
    mid = await auto_distill(cid, fake_summarize)
    assert mid is not None
    again = await auto_distill(cid, fake_summarize)
    assert again is None, "second distill for the same compaction must be a no-op"
    async with Session() as s:
        m = await s.get(Memory, mid)
        assert m.kind == "handoff" and m.source == "auto-distill"
        assert "deck" in m.content and "compaction #" in m.content
    # and the next turn's context pins it (handoff pinning)
    from noesek.core.context import assemble
    async with Session() as s:
        ctx = await assemble(s, cid, query="where were we")
    sys = ctx[0]["content"]
    assert "Auto-distilled session summary" in sys
