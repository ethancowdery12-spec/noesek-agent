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


async def fts_search_ids(conversation_id: int, query: str, limit: int) -> list[int]:
    """Active memory ids for this conversation matching the query, best first."""
    tokens = _FTS_TOKEN.findall((query or "").lower())
    if not tokens or not await fts_available():
        return []
    match = " OR ".join(tokens[:8])
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT m.id FROM memory_fts f JOIN memories m ON m.id = f.memory_id "
            "WHERE memory_fts MATCH :q AND m.conversation_id = :c AND m.active = 1 "
            "ORDER BY bm25(memory_fts) LIMIT :n"),
            {"q": match, "c": conversation_id, "n": limit})).all()
    return [r[0] for r in rows]


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
