"""Graph memory layer (Ethan's graph-memory piece, Sep 21): deterministic entity
extraction, co-occurrence edges with relation types, recall neighborhood boost."""
import pytest
from sqlalchemy import select, text

from noesek.config import settings
from noesek.core.memory_graph import (deindex_graph, extract_entities, graph_boost,
                                      index_graph, relation_type)
from noesek.db import Conversation, Memory, Session
from noesek.tools.state import ForgetInput, RememberInput, forget_handler, memory_handler


@pytest.fixture
async def graph_on(db, monkeypatch):
    """Graph tables are raw-SQL (outside Base.metadata), so the db fixture's
    recreate does not wipe them; clean explicitly to isolate tests."""
    monkeypatch.setattr(settings, "graph_memory_enabled", True)
    from noesek.core.memory_graph import graph_available
    await graph_available()
    async with Session() as s:
        await s.execute(text("DELETE FROM graph_edges"))
        await s.execute(text("DELETE FROM graph_entities"))
        await s.commit()
    return settings


def test_extract_proper_nouns_mixed_case_and_sentence_start():
    ents = extract_entities('Ethan prefers Postgres over MySQL for the "Noesek Agent" project #backend')
    assert "noesek agent" in ents and "backend" in ents
    assert "ethan" in ents and "postgres" in ents and "mysql" in ents


def test_extract_skips_sentence_openers():
    ents = extract_entities("The deploy freezes every Friday.")
    assert "the" not in ents and "friday" in ents


def test_extract_lowercase_fallback():
    ents = extract_entities("all lowercase note about sqlite backups")
    assert "lowercase" in ents and "sqlite" in ents


def test_extract_deterministic_and_capped():
    a = extract_entities("Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Kappa Lambda")
    assert a == extract_entities("Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Kappa Lambda")
    assert len(a) <= 8


def test_relation_typing():
    assert relation_type("Ethan prefers Postgres") == "prefers"
    assert relation_type("she loves hiking") == "likes"
    assert relation_type("we use sqlite") == "uses"
    assert relation_type("he works at Acme") == "works_at"
    assert relation_type("plain co-occurrence") == "related"


async def _conv():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); return c.id


async def test_index_graph_creates_entities_and_edges(db, graph_on):
    cid = await _conv()
    await index_graph(1, cid, "Ethan prefers Postgres over MySQL")
    async with Session() as s:
        ents = (await s.execute(text("SELECT name FROM graph_entities WHERE conversation_id = :c"), {"c": cid})).all()
        edges = (await s.execute(text("SELECT relation, weight, memory_id FROM graph_edges WHERE conversation_id = :c"), {"c": cid})).all()
    names = {r[0] for r in ents}
    assert {"ethan", "postgres", "mysql"} <= names
    assert edges and all(r[0] == "prefers" and r[2] == 1 for r in edges)


async def test_weight_increments_on_repeat(db, graph_on):
    cid = await _conv()
    await index_graph(1, cid, "Ethan prefers Postgres")
    await index_graph(1, cid, "Ethan prefers Postgres")
    async with Session() as s:
        w = await s.scalar(text("SELECT max(weight) FROM graph_edges WHERE conversation_id = :c"), {"c": cid})
    assert w == 2


async def test_deindex_removes_memory_edges(db, graph_on):
    cid = await _conv()
    await index_graph(1, cid, "Ethan prefers Postgres")
    await index_graph(2, cid, "Zebra topic with MySQL")
    await deindex_graph(1)
    async with Session() as s:
        ids = (await s.execute(text("SELECT DISTINCT memory_id FROM graph_edges WHERE conversation_id = :c"), {"c": cid})).all()
    assert [r[0] for r in ids] == [2]


async def test_remember_tool_indexes_graph(db, graph_on):
    cid = await _conv()
    r = await memory_handler(cid)(RememberInput(content="Ethan prefers Postgres for Noesek", kind="fact"))
    async with Session() as s:
        n = await s.scalar(text("SELECT count(*) FROM graph_edges WHERE conversation_id = :c AND memory_id = :m"),
                           {"c": cid, "m": r["memory_id"]})
    assert n > 0


async def test_forget_tool_drops_graph_edges(db, graph_on):
    cid = await _conv()
    r = await memory_handler(cid)(RememberInput(content="Ethan prefers Postgres for Noesek", kind="fact"))
    await forget_handler(cid)(ForgetInput(memory_id=r["memory_id"]))
    async with Session() as s:
        n = await s.scalar(text("SELECT count(*) FROM graph_edges WHERE memory_id = :m"), {"m": r["memory_id"]})
    assert n == 0


async def test_graph_boost_hits_query_entity_and_neighbor(db, graph_on):
    cid = await _conv()
    # memory 9 links Postgres <-> NoSQL; memory 10 links Postgres <-> Indexing
    await index_graph(9, cid, "Postgres beats NoSQL here")
    await index_graph(10, cid, "Postgres needs Indexing tuning")
    boosts = await graph_boost(cid, "how is Postgres doing")
    assert boosts.get(9, 0) > 0 and boosts.get(10, 0) > 0
    # 1-hop: querying a neighbor of Postgres also boosts its edges
    boosts2 = await graph_boost(cid, "tell me about NoSQL")
    assert boosts2.get(9, 0) > 0 and boosts2.get(10, 0) > 0  # NoSQL -> Postgres -> Indexing


async def test_graph_boost_disabled(db, graph_on, monkeypatch):
    cid = await _conv()
    await index_graph(9, cid, "Postgres beats NoSQL here")
    monkeypatch.setattr(settings, "graph_memory_enabled", False)
    assert await graph_boost(cid, "Postgres") == {}


async def test_fusion_uses_graph_boost(db, graph_on, monkeypatch):
    """Graph boost flips the order when the baseline is tied and vectors are off."""
    from noesek.core.context import rank_memories_async
    monkeypatch.setattr(settings, "vector_memory_enabled", False)
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); cid = c.id
    m1 = await memory_handler(cid)(RememberInput(content="Postgres tuning notes live here", kind="note"))
    m2 = await memory_handler(cid)(RememberInput(content="totally different zebra note", kind="note"))
    async with Session() as s:
        mems = (await s.execute(select(Memory).where(Memory.conversation_id == cid))).scalars().all()
    picked = await rank_memories_async(cid, "what about Postgres", list(mems), 5)
    assert picked[0].id == m1["memory_id"]
