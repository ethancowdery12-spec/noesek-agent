"""Memory v2 (stage D): typed memories with provenance, invalidate-not-overwrite,
SQLite FTS5 episodic search, persisted compaction transitions, untrusted wrapping.

Zero added dependencies: FTS5 ships with SQLite; when the local SQLite build
lacks it, every search falls back to the v1 keyword ranker.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from ..db import Compaction, Memory, Session

MEMORY_KINDS = ("note", "fact", "preference", "episode", "handoff", "lesson")

_FTS_TOKEN = re.compile(r"[a-z0-9]{3,}")
_fts_ok: bool | None = None


async def fts_available() -> bool:
    """Feature-detect FTS5 once per process."""
    global _fts_ok
    if _fts_ok is None:
        try:
            async with Session() as s:
                await s.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(memory_id UNINDEXED, content)"))
                await s.commit()
            _fts_ok = True
        except Exception:
            _fts_ok = False
    return _fts_ok


async def index_memory(memory_id: int, content: str) -> None:
    """Best-effort FTS index write; never breaks a user turn."""
    try:
        if not await fts_available(): return
        async with Session() as s:
            await s.execute(text("INSERT INTO memory_fts(memory_id, content) VALUES (:i, :c)"),
                            {"i": memory_id, "c": content})
            await s.commit()
    except Exception:
        pass


async def deindex_memory(memory_id: int) -> None:
    try:
        if not await fts_available(): return
        async with Session() as s:
            await s.execute(text("DELETE FROM memory_fts WHERE memory_id = :i"), {"i": memory_id})
            await s.commit()
    except Exception:
        pass


async def fts_search_ids(conversation_id: int | None, query: str, limit: int) -> list[int]:
    """Active memory ids matching the query, best first. conversation_id=None
    searches the shared user-wide pool (provenance only, Sep 22 recall fix)."""
    tokens = _FTS_TOKEN.findall((query or "").lower())
    if not tokens or not await fts_available():
        return []
    match = " OR ".join(tokens[:8])
    sql = ("SELECT m.id FROM memory_fts f JOIN memories m ON m.id = f.memory_id "
           "WHERE memory_fts MATCH :q AND m.active = 1 ")
    params = {"q": match, "n": limit}
    if conversation_id is not None:
        sql += "AND m.conversation_id = :c "
        params["c"] = conversation_id
    sql += "ORDER BY bm25(memory_fts) LIMIT :n"
    async with Session() as s:
        rows = (await s.execute(text(sql), params)).all()
    return [r[0] for r in rows]


async def auto_distill(conversation_id: int, summarize) -> int | None:
    """Session auto-distill (item 58, claude-mem pattern, own implementation):
    after a compaction, compress the dropped span into ONE durable handoff
    memory so later turns keep the thread (the handoff pin in context.assemble
    surfaces it). Idempotent per compaction; None when there is nothing to do.
    `summarize` is an async callable transcript -> summary text supplied by the
    caller (the controller wires its chat model; tests wire a fake)."""
    from sqlalchemy import select as _select
    from ..db import Message
    async with Session() as s:
        comp = (await s.execute(_select(Compaction).where(Compaction.conversation_id==conversation_id)
                                .order_by(Compaction.created_at.desc()).limit(1))).scalar_one_or_none()
        if comp is None or comp.oldest_dropped_id is None:
            return None
        marker = f"compaction #{comp.id}"
        existing = (await s.execute(_select(Memory.id).where(
            Memory.conversation_id==conversation_id, Memory.kind=="handoff",
            Memory.source=="auto-distill", Memory.content.like(f"%{marker}%")))).first()
        if existing:
            return None
        span = (await s.execute(_select(Message).where(
            Message.conversation_id==conversation_id,
            Message.id >= comp.oldest_dropped_id, Message.id <= comp.newest_dropped_id)
            .order_by(Message.id))).scalars().all()
    if not span:
        return None
    transcript = "\n".join(f"{m.role}: {(m.content or '')[:300]}" for m in span[-40:])[:6000]
    try:
        summary = (await summarize(transcript) or "").strip()
    except Exception:
        return None
    if not summary:
        return None
    content = f"Auto-distilled session summary ({marker}): {summary[:1500]}"
    async with Session() as s:
        m = Memory(conversation_id=conversation_id, kind="handoff",
                   content=content, source="auto-distill")
        s.add(m); await s.commit(); await s.refresh(m)
        mid = m.id
    try:
        await index_memory(mid, content)
    except Exception:
        pass
    return mid


async def record_compaction(conversation_id: int, removed: int, budget: int,
                            oldest_dropped_id: int | None, newest_dropped_id: int | None,
                            turn_id: str | None = None) -> int | None:
    """Persist a visible compaction transition. Best-effort; None on failure."""
    try:
        async with Session() as s:
            row = Compaction(conversation_id=conversation_id, turn_id=turn_id,
                             removed_count=removed, budget_chars=budget,
                             oldest_dropped_id=oldest_dropped_id, newest_dropped_id=newest_dropped_id)
            s.add(row); await s.commit()
            return row.id
    except Exception:
        return None


def wrap_untrusted(text: str, source: str) -> str:
    """Mark tool/web content as untrusted data before it enters model context."""
    safe = "".join(c for c in source if c.isalnum() or c in "_-")
    return f'<untrusted_content source="{safe}">\n{text}\n</untrusted_content>'
