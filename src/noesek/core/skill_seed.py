"""Seed the curated business skill backbone (batch 2, item 86).

anthropics/knowledge-work-plugins (Apache-2.0) ships ~250 workplace SKILL.md
workflows; scripts/build_kwp_seed.py converts whole categories into
src/noesek/data/kwp_skills.py with per-skill provenance headers. This module
loads them into the shared skill library (Memory rows, kind="skill") so FTS/
vector/graph recall surfaces them like any agent-written skill (#144).

Idempotent: a skill whose name already exists (active OR retired) is left
alone - retired means the user curated it out, and seeding must never
resurrect or overwrite. Seeded rows carry source="kwp" and live under a
system conversation; in deployment pool mode every chat recalls them.
"""
from sqlalchemy import select

from ..data.kwp_skills import KWP_SKILLS
from ..db import Conversation, Memory, Session
from ..config import settings
from .memory_v2 import index_memory
from .memory_vector import index_vector
from .memory_graph import index_graph

SEED_CHANNEL = "system"
SEED_USER = "kwp-skill-seed"

_FORMAT = ("Skill: {name}\nWhen to use: {when}\nSteps:\n{body}\n"
           "Verified by: Imported from anthropics/knowledge-work-plugins "
           "({path}, Apache-2.0) - curated business backbone, item 86.")


async def seed_kwp_skills() -> int:
    """Insert missing seed skills. Returns the count newly added."""
    if not settings.kwp_seed_enabled or not KWP_SKILLS:
        return 0
    try:
        async with Session() as s:
            conv = (await s.execute(select(Conversation).where(
                Conversation.channel == SEED_CHANNEL,
                Conversation.external_user_id == SEED_USER))).scalars().first()
            if conv is None:
                conv = Conversation(title="KWP skill seed", channel=SEED_CHANNEL,
                                    external_user_id=SEED_USER)
                s.add(conv); await s.commit(); await s.refresh(conv)
            existing = set((await s.execute(select(Memory.content).where(
                Memory.kind == "skill", Memory.source == "kwp"))).scalars().all())
            existing_names = {c.splitlines()[0].removeprefix("Skill: ").strip()
                              for c in existing if c.startswith("Skill: ")}
            added = []
            for sk in KWP_SKILLS:
                if sk["name"] in existing_names:
                    continue
                m = Memory(conversation_id=conv.id, kind="skill", source="kwp",
                           content=_FORMAT.format(name=sk["name"], when=sk["description"],
                                                  body=sk["body"], path=sk["source_path"]))
                s.add(m); await s.commit(); await s.refresh(m)
                added.append(m)
        for m in added:  # index outside the insert session; best-effort per skill
            try:
                await index_memory(m.id, m.content)
                await index_vector(m.id, m.conversation_id, m.content)
                await index_graph(m.id, m.conversation_id, m.content)
            except Exception:
                pass
        return len(added)
    except Exception:
        return 0
