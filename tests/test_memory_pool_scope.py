"""Memory pool scoping (item 68, multi-user seam): 'deployment' mode keeps the
shared pool (single-user behavior); 'user' mode isolates each user's memories."""
import pytest
from sqlalchemy import select, text

from noesek.config import settings
from noesek.core.context import rank_memories_async
from noesek.core.memory_v2 import index_memory
from noesek.db import Conversation, Memory, Session, pool_conversation_ids
from noesek.tools.state import RecallInput, recall_handler

@pytest.fixture
async def two_users(db):
    async with Session() as s:
        ca = Conversation(title="a1", channel="local", external_user_id="userA-chat1")
        cb = Conversation(title="b1", channel="local", external_user_id="userB-chat1")
        s.add_all([ca, cb]); await s.commit(); await s.refresh(ca); await s.refresh(cb)
        ma = Memory(conversation_id=ca.id, kind="fact", content="User A's dog is called Biscuit")
        mb = Memory(conversation_id=cb.id, kind="fact", content="User B's dog is called Waffles")
        s.add_all([ma, mb]); await s.commit(); await s.refresh(ma); await s.refresh(mb)
        ids = (ca.id, cb.id, ma.id, mb.id)
    await index_memory(ma.id, ma.content); await index_memory(mb.id, mb.content)
    return ids

async def test_deployment_mode_shares_pool_by_default(two_users):
    _, _, ma, mb = two_users
    assert settings.memory_pool_mode == "deployment"
    async with Session() as s:
        assert await pool_conversation_ids(s, two_users[0]) is None
    out = await recall_handler(two_users[0])(RecallInput(query="dog"))
    assert {m["id"] for m in out["memories"]} == {ma, mb}

async def test_user_mode_isolates_pools(two_users, monkeypatch):
    ca, cb, ma, mb = two_users
    monkeypatch.setattr(settings, "memory_pool_mode", "user")
    async with Session() as s:
        pool_a = await pool_conversation_ids(s, ca)
        pool_b = await pool_conversation_ids(s, cb)
    assert pool_a == [ca] and pool_b == [cb]  # distinct users, distinct pools
    out = await recall_handler(ca)(RecallInput(query="dog"))
    assert {m["id"] for m in out["memories"]} == {ma}
    out = await recall_handler(cb)(RecallInput(query="dog"))
    assert {m["id"] for m in out["memories"]} == {mb}

async def test_user_mode_groups_a_users_chats(two_users, monkeypatch):
    ca, cb, ma, mb = two_users
    monkeypatch.setattr(settings, "memory_pool_mode", "user")
    async with Session() as s:
        ca2 = Conversation(title="a2", channel="local", external_user_id="userA-chat1")
        s.add(ca2); await s.commit(); await s.refresh(ca2)
        pool = await pool_conversation_ids(s, ca2.id)
    assert sorted(pool) == sorted([ca, ca2.id])
