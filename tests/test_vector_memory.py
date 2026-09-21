"""Vector memory layer (Ethan's vector-memory piece, Sep 21): hashed-ngram local
embedder, SQLite vector store, lazy backfill, cosine fusion into recall."""
import pytest
from sqlalchemy import select, text

from noesek.config import settings
from noesek.core.memory_vector import (HashedNgramEmbedder, OpenAICompatibleEmbedder,
                                       cosine, deindex_vector, get_embedder,
                                       index_vector, vector_scores)
from noesek.db import Conversation, Memory, Session
from noesek.tools.state import ForgetInput, RememberInput, forget_handler, memory_handler


@pytest.fixture
def vec_on(monkeypatch):
    monkeypatch.setattr(settings, "vector_memory_enabled", True)
    monkeypatch.setattr(settings, "embed_provider", "local")
    return settings


def test_hashed_embedder_deterministic_and_normalized():
    e = HashedNgramEmbedder(256)
    a = e.embed("database connection pooling with sqlalchemy")
    assert a == e.embed("database connection pooling with sqlalchemy")
    assert abs(sum(v * v for v in a) ** 0.5 - 1.0) < 1e-6
    assert len(a) == 256


def test_hashed_embedder_similarity_order():
    e = HashedNgramEmbedder(256)
    q = e.embed("postgres connection pool sizing")
    near = e.embed("tuning the postgres connection pool")
    far = e.embed("banana bread recipe with walnuts")
    assert cosine(q, near) > cosine(q, far)


def test_provider_selection(vec_on, monkeypatch):
    assert get_embedder().name == "hashed-ngram"
    monkeypatch.setattr(settings, "embed_provider", "openai-compatible")
    monkeypatch.setattr(settings, "embed_base_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(settings, "embed_model", "deepseek-embed")
    emb = get_embedder()
    assert isinstance(emb, OpenAICompatibleEmbedder) and emb.model == "deepseek-embed"


def test_openai_provider_needs_url_and_model(vec_on, monkeypatch):
    monkeypatch.setattr(settings, "embed_provider", "openai-compatible")
    monkeypatch.setattr(settings, "embed_base_url", "")
    monkeypatch.setattr(settings, "embed_model", "")
    assert get_embedder().name == "hashed-ngram"  # falls back safely


async def _conv_with_memory(content="alpha memory about postgres pooling"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.flush()
        m = Memory(conversation_id=c.id, content=content, kind="note"); s.add(m); await s.commit()
        return c.id, m.id


async def test_index_and_score_roundtrip(db, vec_on):
    cid, mid = await _conv_with_memory()
    await index_vector(mid, cid, "alpha memory about postgres pooling")
    scores = await vector_scores(cid, "postgres pooling")
    assert scores.get(mid, 0.0) > 0.5


async def test_deindex_removes(db, vec_on):
    cid, mid = await _conv_with_memory()
    await index_vector(mid, cid, "alpha memory about postgres pooling")
    await deindex_vector(mid)
    async with Session() as s:
        n = await s.scalar(text("SELECT count(*) FROM memory_vectors WHERE memory_id = :i"), {"i": mid})
    assert n == 0


async def test_lazy_backfill_on_score(db, vec_on):
    cid, mid = await _conv_with_memory("unindexed memory about redis caching")
    scores = await vector_scores(cid, "redis caching")  # no explicit index_vector call
    assert scores.get(mid, 0.0) > 0.5


async def test_scores_disabled_returns_empty(db, vec_on, monkeypatch):
    cid, mid = await _conv_with_memory()
    await index_vector(mid, cid, "alpha memory about postgres pooling")
    monkeypatch.setattr(settings, "vector_memory_enabled", False)
    assert await vector_scores(cid, "postgres pooling") == {}


async def test_remember_tool_indexes_vector(db, vec_on):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); cid = c.id
    r = await memory_handler(cid)(RememberInput(content="remember that deploys freeze on Fridays", kind="fact"))
    async with Session() as s:
        n = await s.scalar(text("SELECT count(*) FROM memory_vectors WHERE memory_id = :i"), {"i": r["memory_id"]})
    assert n == 1


async def test_forget_tool_drops_vector(db, vec_on):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); cid = c.id
    r = await memory_handler(cid)(RememberInput(content="temporary fact about staging", kind="fact"))
    await forget_handler(cid)(ForgetInput(memory_id=r["memory_id"]))
    async with Session() as s:
        n = await s.scalar(text("SELECT count(*) FROM memory_vectors WHERE memory_id = :i"), {"i": r["memory_id"]})
    assert n == 0


async def test_fusion_boosts_vector_match(db, vec_on, monkeypatch):
    """With keyword scores tied, cosine decides the order."""
    from noesek.core.context import rank_memories_async
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.flush()
        m1 = Memory(conversation_id=c.id, content="sharedword alpha one", kind="note")
        m2 = Memory(conversation_id=c.id, content="sharedword beta two", kind="note")
        s.add_all([m1, m2]); await s.commit(); cid = c.id
    # m2's vector points at the query; m1's points away
    await index_vector(m1.id, cid, "unrelated zebra topic entirely")
    await index_vector(m2.id, cid, "sharedword query target")
    async with Session() as s:
        mem_objs = (await s.execute(select(Memory).where(Memory.conversation_id == cid))).scalars().all()
    picked = await rank_memories_async(cid, "sharedword query target", list(mem_objs), 5)
    assert picked[0].id == m2.id
