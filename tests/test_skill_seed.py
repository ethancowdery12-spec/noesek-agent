"""KWP business backbone seed (batch 2, item 86)."""
import pytest
from sqlalchemy import select, text

from noesek.config import settings
from noesek.core.skill_seed import seed_kwp_skills
from noesek.data.kwp_skills import KWP_SKILLS
from noesek.db import Memory, Session


def test_seed_catalog_shape():
    assert len(KWP_SKILLS) >= 20
    for sk in KWP_SKILLS:
        assert sk["name"] and sk["description"] and sk["body"]
        assert sk["source_path"].startswith(sk["category"] + "/skills/")
        assert len(sk["body"]) <= 4000
    categories = {sk["category"] for sk in KWP_SKILLS}
    assert categories == {"customer-support", "operations", "marketing", "small-business",
                           "finance", "human-resources", "legal", "sales"}


@pytest.mark.asyncio
async def test_seed_inserts_then_is_idempotent(db, monkeypatch):
    monkeypatch.setattr(settings, "kwp_seed_enabled", True)
    monkeypatch.setattr(settings, "graph_memory_enabled", False)  # seed path stays sqlite-local
    first = await seed_kwp_skills()
    assert first == len(KWP_SKILLS)
    second = await seed_kwp_skills()
    assert second == 0, "re-seed must not duplicate"
    async with Session() as s:
        rows = (await s.execute(select(Memory).where(Memory.source == "kwp"))).scalars().all()
    assert len(rows) == len(KWP_SKILLS)
    assert all(r.kind == "skill" and r.active for r in rows)
    sample = next(r for r in rows if "ticket-triage" in r.content)
    assert "Apache-2.0" in sample.content and "anthropics/knowledge-work-plugins" in sample.content


@pytest.mark.asyncio
async def test_seed_never_resurrects_retired(db, monkeypatch):
    monkeypatch.setattr(settings, "kwp_seed_enabled", True)
    monkeypatch.setattr(settings, "graph_memory_enabled", False)
    await seed_kwp_skills()
    async with Session() as s:
        victim = (await s.execute(select(Memory).where(Memory.source == "kwp"))).scalars().first()
        victim.active = False
        await s.commit()
        vid = victim.id
    assert await seed_kwp_skills() == 0
    async with Session() as s:
        rows = (await s.execute(select(Memory).where(Memory.source == "kwp"))).scalars().all()
        assert not any(r.id != vid and r.content.startswith(f"Skill: {victim.content.splitlines()[0].removeprefix('Skill: ')}")
                       for r in rows if r.id != vid), "retired seed must stay retired"


@pytest.mark.asyncio
async def test_seed_flag_off_is_noop(db, monkeypatch):
    monkeypatch.setattr(settings, "kwp_seed_enabled", False)
    assert await seed_kwp_skills() == 0
