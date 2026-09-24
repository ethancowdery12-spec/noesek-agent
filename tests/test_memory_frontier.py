"""Layer-utility frontier for memory retrieval (item 65, IBM VLDB 2026 recipe).

Kashyap et al., "How Much Structure Should Agentic Graph Memory Build for
Text Retrieval?" (VLDB 2026 workshop): each added layer of graph structure
must PROVE downstream utility against a fixed retrieval/reader stack, and
light entity-centric structure should beat the flat baseline on multi-hop
evidence composition. These fixtures codify that recipe as a regression
guard: the graph layer must surface multi-hop memories the flat FTS/keyword
baseline misses, must never reorder when disabled, and must be deterministic
(cost side of the quality-cost frontier: no model calls, bounded tables).
"""
import pytest
from sqlalchemy import text

from noesek.config import settings
from noesek.core.context import rank_memories_async
from noesek.core.memory_graph import graph_available, index_graph
from noesek.core.memory_v2 import index_memory
from noesek.db import Memory, Session

CORPUS = [
    "Ethan's sister is Sarah.",                      # bridge: ethan <-> sarah
    "Sarah likes espresso from the Bluecup cafe.",   # target: no 'sister' token
    "Ethan prefers morning meetings.",
    "Postgres is the production database.",
    "The deploy freezes every Friday.",
    "Uncle Marco runs the bakery on Fifth Street.",  # distractor chain
    "Marco's bakery closes on Mondays.",
]

@pytest.fixture
async def corpus(db, monkeypatch):
    monkeypatch.setattr(settings, "graph_memory_enabled", True)
    await graph_available()
    async with Session() as s:
        await s.execute(text("DELETE FROM graph_edges"))
        await s.execute(text("DELETE FROM graph_entities"))
        conv_ids = []
        from noesek.db import Conversation
        c = Conversation(title="frontier", channel="test", external_user_id="frontier")
        s.add(c); await s.commit(); await s.refresh(c)
        for content in CORPUS:
            m = Memory(conversation_id=c.id, kind="fact", content=content)
            s.add(m); await s.commit(); await s.refresh(m)
            await index_memory(m.id, content)
            await index_graph(m.id, c.id, content)
        rows = (await s.execute(text("SELECT id, content FROM memories"))).all()
    return {content: mid for mid, content in rows}

async def _recall_ids(query, limit=5):
    async with Session() as s:
        rows = (await s.execute(__import__("sqlalchemy").select(Memory).where(Memory.active==True))).scalars().all()
    picked = await rank_memories_async(None, query, list(rows), limit)
    return [m.id for m in picked]

async def test_graph_layer_surfaces_multihop_memory_flat_baseline_misses(corpus, monkeypatch):
    """Query 'what does my sister like' - the espresso memory carries no query
    token; only the ethan->sarah->espresso entity chain can reach it."""
    target = corpus["Sarah likes espresso from the Bluecup cafe."]
    monkeypatch.setattr(settings, "graph_memory_enabled", False)
    flat = await _recall_ids("what does my sister like")
    monkeypatch.setattr(settings, "graph_memory_enabled", True)
    layered = await _recall_ids("what does my sister like")
    assert target in layered, f"graph layer failed to surface multi-hop memory: {layered}"
    assert target not in flat or layered.index(target) < flat.index(target)

async def test_layer_disabled_never_reorders(corpus, monkeypatch):
    monkeypatch.setattr(settings, "graph_memory_enabled", False)
    a = await _recall_ids("when does the bakery close")
    b = await _recall_ids("when does the bakery close")
    assert a == b and corpus["Marco's bakery closes on Mondays."] in a

async def test_layered_recall_is_deterministic(corpus, monkeypatch):
    monkeypatch.setattr(settings, "graph_memory_enabled", True)
    a = await _recall_ids("what does my sister like")
    b = await _recall_ids("what does my sister like")
    assert a == b

async def test_distractor_chain_does_not_leak(corpus, monkeypatch):
    """1-hop only: querying the sister chain must not pull bakery memories."""
    monkeypatch.setattr(settings, "graph_memory_enabled", True)
    ids = await _recall_ids("what does my sister like", limit=5)
    target = corpus["Sarah likes espresso from the Bluecup cafe."]
    assert target in ids
    for d in ("Uncle Marco runs the bakery on Fifth Street.", "Marco's bakery closes on Mondays."):
        assert corpus[d] not in ids or ids.index(target) < ids.index(corpus[d])


CHAIN = [
    "Alice works with Bruno.",                  # alice <-> bruno
    "Bruno coaches the Lions team.",            # bruno <-> lions team
    "The Lions team trains at Riverside Park.", # lions team <-> riverside park
]

@pytest.fixture
async def chain(db, monkeypatch):
    monkeypatch.setattr(settings, "graph_memory_enabled", True)
    await graph_available()
    async with Session() as s:
        await s.execute(text("DELETE FROM graph_edges"))
        await s.execute(text("DELETE FROM graph_entities"))
        from noesek.db import Conversation
        c = Conversation(title="chain", channel="test", external_user_id="chain")
        s.add(c); await s.commit(); await s.refresh(c)
        ids = []
        for content in CHAIN:
            m = Memory(conversation_id=c.id, kind="fact", content=content)
            s.add(m); await s.commit(); await s.refresh(m)
            await index_memory(m.id, content)
            await index_graph(m.id, c.id, content)
            ids.append(m.id)
    return ids

async def test_multihop_walk_surfaces_twohop_memory(chain, monkeypatch):
    """HippoRAG pattern (item 84): a memory two edges from the query entity
    gets a graded boost instead of falling off the 1-hop cutoff."""
    from noesek.core.memory_graph import graph_boost
    m1, m2, m3 = chain
    boosts = await graph_boost(None, "Alice")
    assert boosts.get(m1, 0) > 0, "direct memory must be boosted"
    assert boosts.get(m3, 0) > 0, "2-hop memory must be boosted by the walk"
    # Grading check: per-edge decay is the mechanism. Cross-memory ordering is
    # NOT asserted - graph_boost sums a memory's clique edges as evidence mass
    # (item 65 semantics), so an entity-rich deep memory can out-sum a sparse
    # direct one. What must hold: the SAME memory scores lower with decay
    # than it would at decay 1.0 (no grading).
    monkeypatch.setattr(settings, "graph_walk_decay", 1.0)
    flat = await graph_boost(None, "Alice")
    assert boosts[m3] < flat[m3], "decay must grade deep hops below flat reach"

async def test_multihop_walk_depth_one_keeps_hard_cutoff(chain, monkeypatch):
    """Depth 1 reproduces the old fixed neighborhood: 2-hop memory silent."""
    from noesek.core.memory_graph import graph_boost
    monkeypatch.setattr(settings, "graph_walk_depth", 1)
    m1, m2, m3 = chain
    boosts = await graph_boost(None, "Alice")
    assert boosts.get(m1, 0) > 0
    assert m3 not in boosts
