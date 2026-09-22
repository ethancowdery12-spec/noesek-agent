"""Cross-chat memory recall regression (Sep 22 live-verify failure).

Memories are the agent's durable knowledge of the user, not of one chat
session: a fact stored in chat A must be visible when chat B's context is
assembled. The pool query used to filter Memory.conversation_id == current
conversation, so fresh-chat recall always came up empty.
"""
import pytest
from sqlalchemy import delete

from noesek.db import Conversation, Memory, Session, init_db, migrate


@pytest.fixture()
async def clean(db):
    await init_db(); await migrate()
    async with Session() as s:
        await s.execute(delete(Memory))
        await s.execute(delete(Conversation))
        await s.commit()
    yield


async def _conv(s, ext):
    c = Conversation(channel="web", external_user_id=ext)
    s.add(c); await s.commit(); await s.refresh(c)
    return c


@pytest.mark.asyncio
async def test_memory_stored_in_chat_a_visible_in_chat_b(clean):
    async with Session() as s:
        a = await _conv(s, "chat-a"); b = await _conv(s, "chat-b")
        s.add(Memory(conversation_id=a.id, kind="preference",
                     content="Favorite bird is the cardinal."))
        await s.commit()
    from noesek.core.context import assemble
    async with Session() as s:
        ctx = await assemble(s, b.id, query="what is my favorite bird")
    mem_msgs = [m for m in ctx if m.get("role") == "system" and "cardinal" in (m.get("content") or "")]
    assert mem_msgs, "memory stored in chat A missing from chat B context"


@pytest.mark.asyncio
async def test_fts_search_ids_none_searches_all_conversations(clean):
    async with Session() as s:
        a = await _conv(s, "chat-a")
        m = Memory(conversation_id=a.id, kind="preference", content="Favorite bird is the cardinal.")
        s.add(m); await s.commit(); await s.refresh(m)
        mid = m.id
    from noesek.core.memory_v2 import fts_available, index_memory, fts_search_ids
    if not await fts_available():
        pytest.skip("sqlite build without FTS5")
    await index_memory(mid, "Favorite bird is the cardinal.")
    assert mid in await fts_search_ids(None, "favorite bird", 10)
