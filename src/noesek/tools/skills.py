"""skill_library: the agent writes, verifies, stores, and reuses its own
skills (skills batch 3: Voyager MIT + agent-workflow-memory Apache
patterns, own-words implementation - nothing copied).

Voyager's core loop, adapted to noesek's memory pipeline: after a
procedure verifiably works, the agent saves it as a structured skill -
name, when-to-use, steps, and the verification that proved it. Skills are
Memory rows (kind="skill"), so retrieval comes free: FTS + keyword +
vector + graph ranking in assemble() surfaces relevant skills next to
other durable memory on later turns, and explicit search/list/get/retire
manage the library. agent-workflow-memory's contribution - workflow
templates from successful runs, injected for similar future tasks - lands
through the same pool: the verification field records what "successful"
meant so later turns can trust the template.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..core.context import rank_memories
from ..core.memory_v2 import deindex_memory, index_memory
from ..db import Memory, Session

SKILL_KIND = "skill"


class SkillInput(BaseModel):
    action: str = Field(description="save | search | get | list | retire")
    name: str = Field(default="", max_length=200, description="Short skill name (save)")
    when_to_use: str = Field(default="", max_length=500, description="Trigger conditions: the task shapes this skill applies to (save)")
    steps: str = Field(default="", max_length=4000, description="The procedure, numbered steps, concrete (save)")
    verification: str = Field(default="", max_length=1000, description="What proved this works - the check that passed and when (required for save)")
    query: str = Field(default="", max_length=300, description="Search terms (search)")
    skill_id: int = Field(default=0, description="Skill memory id (get | retire)")
    limit: int = Field(default=5, ge=1, le=20)


def _format(inp: SkillInput) -> str:
    return (f"Skill: {inp.name.strip()}\nWhen to use: {inp.when_to_use.strip()}\n"
            f"Steps:\n{inp.steps.strip()}\nVerified by: {inp.verification.strip()}")


def _preview(content: str) -> dict:
    lines = (content or "").splitlines()
    name = lines[0].removeprefix("Skill: ").strip() if lines else ""
    when = ""
    for ln in lines:
        if ln.startswith("When to use:"):
            when = ln.removeprefix("When to use:").strip()
            break
    return {"name": name, "when_to_use": when}


async def _active_skills(session) -> list[Memory]:
    return (await session.execute(select(Memory).where(
        Memory.kind == SKILL_KIND, Memory.active == True)
        .order_by(Memory.created_at.desc()).limit(200))).scalars().all()


async def skill_library(inp: SkillInput, conversation_id: int) -> dict:
    action = inp.action.strip().lower()
    if action == "save":
        missing = [f for f, v in (("name", inp.name), ("when_to_use", inp.when_to_use),
                                  ("steps", inp.steps), ("verification", inp.verification)) if not v.strip()]
        if missing:
            return {"ok": False, "error": f"missing required for save: {', '.join(missing)} - "
                    "a skill is only saved after a verification proves it works"}
        content = _format(inp)
        async with Session() as s:
            m = Memory(conversation_id=conversation_id, kind=SKILL_KIND,
                       content=content, source="self-authored")
            s.add(m); await s.commit(); await s.refresh(m)
            mid = m.id
        try:
            from ..core.memory_v2 import index_graph, index_vector
            await index_memory(mid, content)
            await index_vector(mid, conversation_id, content)
            await index_graph(mid, conversation_id, content)
        except Exception:
            pass
        return {"ok": True, "saved": True, "skill_id": mid, "name": inp.name.strip()}
    if action == "search":
        if not inp.query.strip():
            return {"ok": False, "error": "query is required for search"}
        async with Session() as s:
            skills = await _active_skills(s)
        ranked = rank_memories(inp.query, skills, inp.limit)
        return {"ok": True, "count": len(ranked),
                "results": [{"skill_id": m.id, **_preview(m.content)} for m in ranked]}
    if action == "list":
        async with Session() as s:
            skills = await _active_skills(s)
        return {"ok": True, "count": len(skills),
                "results": [{"skill_id": m.id, **_preview(m.content)} for m in skills[:inp.limit]]}
    if action == "get":
        async with Session() as s:
            m = await s.get(Memory, inp.skill_id)
        if not m or m.kind != SKILL_KIND or not m.active:
            return {"ok": False, "error": f"skill #{inp.skill_id} not found"}
        return {"ok": True, "skill_id": m.id, "content": m.content}
    if action == "retire":
        async with Session() as s:
            m = (await s.execute(select(Memory).where(
                Memory.id == inp.skill_id, Memory.kind == SKILL_KIND,
                Memory.active == True))).scalar_one_or_none()
            if not m:
                return {"ok": False, "error": f"skill #{inp.skill_id} not found"}
            m.active = False
            await s.commit()
        try:
            await deindex_memory(inp.skill_id)
        except Exception:
            pass
        return {"ok": True, "retired": inp.skill_id}
    return {"ok": False, "error": f"unknown action {inp.action!r}: save | search | get | list | retire"}
