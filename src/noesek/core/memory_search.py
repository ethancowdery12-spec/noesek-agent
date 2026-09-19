"""Local keyword search over stored memories - offline, no external calls."""
from __future__ import annotations

from sqlalchemy import select

from ..db import Memory, Session


async def search_memories(query: str, limit: int = 20) -> list[dict]:
    if not query.strip():
        raise ValueError("query is required")
    pattern = f"%{query.replace('%', '\\%').replace('_', '\\_')}%"
    async with Session() as s:
        rows = (await s.execute(
            select(Memory).where(Memory.active.is_(True),
                                 Memory.content.ilike(pattern, escape="\\"))
            .order_by(Memory.created_at.desc()).limit(limit))).scalars().all()
        return [{"id": m.id, "conversation_id": m.conversation_id, "kind": m.kind,
                 "content": m.content, "created_at": m.created_at.isoformat()} for m in rows]
