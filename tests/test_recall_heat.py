"""Recall heat counters (MemOS pattern, item 85).

Explicit recalls bump recall_count on surfaced memories and report the heat
in the preview metadata; ambient assemble surfacing does NOT bump (a write
per chat turn would not survive scale). Auto-pin stays off - the core block
is agent-curated (#146); heat is a curation signal, not a trigger.
"""
import pytest
from sqlalchemy import text

from noesek.db import Memory, Session, bump_recall_heat, _COLUMN_UPGRADES
from noesek.tools.state import recall_handler, RecallInput


@pytest.fixture
async def mems(db):
    async with Session() as s:
        m1 = Memory(conversation_id=1, kind="fact", content="Ethan takes oat milk")
        m2 = Memory(conversation_id=1, kind="fact", content="Postgres is the production database")
        s.add(m1); s.add(m2); await s.commit(); await s.refresh(m1); await s.refresh(m2)
        return m1.id, m2.id


@pytest.mark.asyncio
async def test_bump_increments_heat(mems):
    m1, m2 = mems
    await bump_recall_heat([m1])
    await bump_recall_heat([m1])
    async with Session() as s:
        rows = dict((await s.execute(text("SELECT id, recall_count FROM memories"))).all())
    assert rows[m1] == 2
    assert rows[m2] == 0


@pytest.mark.asyncio
async def test_recall_reports_heat_in_preview(mems):
    m1, _ = mems
    handler = recall_handler(1)
    out = await handler(RecallInput(query="oat milk", limit=5))
    hit = [m for m in out["memories"] if m["id"] == m1]
    assert hit, "expected the oat-milk memory in recall results"
    assert hit[0]["recall_count"] == 1  # this recall included
    out2 = await handler(RecallInput(query="oat milk", limit=5))
    hit2 = [m for m in out2["memories"] if m["id"] == m1]
    assert hit2[0]["recall_count"] == 2


@pytest.mark.asyncio
async def test_bump_is_best_effort_on_empty():
    await bump_recall_heat([])  # must not raise


def test_migration_entry_present():
    assert _COLUMN_UPGRADES["memories"]["recall_count"] == "INTEGER NOT NULL DEFAULT 0"
