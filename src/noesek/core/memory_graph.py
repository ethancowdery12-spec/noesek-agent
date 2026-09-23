"""Graph memory (Ethan's graph-memory piece, Sep 21): entities and relationships
extracted deterministically from memory content, stored in SQLite, and fused
into recall as a neighborhood boost.

Zero dependencies, no model calls: entities come from surface patterns (quoted
phrases, @mentions/#tags, capitalized phrases, distinctive tokens as fallback);
edges are co-occurrence pairs with a relation type from a small verb-pattern
set. Best-effort writes, same contract as the FTS and vector indexes.
"""
from __future__ import annotations

import re

from sqlalchemy import bindparam, text

from ..config import settings
from ..db import Session

_ENT_DDL = ("CREATE TABLE IF NOT EXISTS graph_entities("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, "
            "name TEXT, kind TEXT DEFAULT 'entity', created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE(conversation_id, name))")
_EDGE_DDL = ("CREATE TABLE IF NOT EXISTS graph_edges("
             "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, "
             "src_id INTEGER, dst_id INTEGER, relation TEXT DEFAULT 'related', "
             "weight INTEGER DEFAULT 1, memory_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
             "UNIQUE(conversation_id, src_id, dst_id, relation, memory_id))")
_tables_ok: bool | None = None

_STOP = {"about", "after", "again", "being", "could", "every", "from", "have",
         "into", "just", "like", "more", "over", "should", "than", "that",
         "their", "them", "then", "there", "these", "they", "this", "those",
         "through", "under", "what", "when", "where", "which", "while", "will",
         "with", "would", "your"}

_QUOTED = re.compile(r'"([^"\n]{2,60})"')
_TAG = re.compile(r'[@#]([A-Za-z0-9_]{2,30})')
_CAP = re.compile(r'\b([A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+){0,2})')
_LOWER = re.compile(r'[a-z][a-z0-9-]{4,}')

_REL_PATTERNS = [
    ("prefers", re.compile(r'\bprefers?\b', re.I)),
    ("likes", re.compile(r'\b(?:likes?|loves?|enjoys?)\b', re.I)),
    ("uses", re.compile(r'\b(?:uses?|using)\b', re.I)),
    ("works_at", re.compile(r'\b(?:works? at|employed (?:at|by))\b', re.I)),
    ("is_a", re.compile(r'\bis an?\b', re.I)),
]


def extract_entities(content: str, cap: int = 8) -> list[str]:
    """Deterministic surface-pattern entity extraction; normalized lowercase."""
    content = content or ""
    ents: list[str] = []
    ents += _QUOTED.findall(content)
    ents += _TAG.findall(content)
    openers = {"The", "This", "That", "These", "Those", "When", "Where", "What",
               "Why", "How", "If", "But", "So", "And", "Or", "Not", "Yes", "Well"}
    for m in _CAP.finditer(content):
        phrase = m.group(1)
        sentence_start = m.start() == 0 or content[max(0, m.start() - 2)] in ".!?\n"
        if len(phrase.split()) >= 2:
            ents.append(phrase)
        elif len(phrase) >= 4 and not (sentence_start and phrase in openers):
            ents.append(phrase)
    # Salient common nouns are bridge entities in multi-hop chains (item 65,
    # IBM VLDB 2026): include them alongside proper nouns, not only as a
    # last-resort fallback - "sister" and "espresso" link memories that
    # capitalized entities alone cannot connect.
    ents += [t for t in _LOWER.findall(content.lower()) if t not in _STOP][:5]
    out: list[str] = []
    for e in ents:
        n = " ".join(e.lower().split())
        if n and n not in _STOP and n not in out:
            out.append(n)
    return out[:cap]


def relation_type(content: str) -> str:
    for name, pat in _REL_PATTERNS:
        if pat.search(content or ""):
            return name
    return "related"


async def graph_available() -> bool:
    global _tables_ok
    if _tables_ok is None:
        try:
            async with Session() as s:
                await s.execute(text(_ENT_DDL)); await s.execute(text(_EDGE_DDL)); await s.commit()
            _tables_ok = True
        except Exception:
            _tables_ok = False
    return _tables_ok


async def _entity_ids(s, conversation_id: int, names: list[str]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for n in names:
        row = (await s.execute(text("SELECT id FROM graph_entities WHERE conversation_id = :c AND name = :n"),
                               {"c": conversation_id, "n": n})).first()
        if row:
            ids[n] = row[0]
        else:
            r = await s.execute(text("INSERT INTO graph_entities(conversation_id, name) VALUES (:c, :n)"),
                                {"c": conversation_id, "n": n})
            ids[n] = r.lastrowid
    return ids


async def index_graph(memory_id: int, conversation_id: int, content: str) -> None:
    """Extract entities/edges from one memory. Best-effort; never breaks a turn."""
    try:
        if not settings.graph_memory_enabled or not await graph_available(): return
        ents = extract_entities(content)
        if not ents: return
        rel = relation_type(content)
        async with Session() as s:
            ids = await _entity_ids(s, conversation_id, ents)
            names = sorted(ids)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    await s.execute(text(
                        "INSERT INTO graph_edges(conversation_id, src_id, dst_id, relation, weight, memory_id)"
                        " VALUES (:c, :s, :d, :r, 1, :m)"
                        " ON CONFLICT(conversation_id, src_id, dst_id, relation, memory_id)"
                        " DO UPDATE SET weight = weight + 1"),
                        {"c": conversation_id, "s": ids[a], "d": ids[b], "r": rel, "m": memory_id})
            await s.commit()
    except Exception:
        pass


async def deindex_graph(memory_id: int) -> None:
    try:
        if not await graph_available(): return
        async with Session() as s:
            await s.execute(text("DELETE FROM graph_edges WHERE memory_id = :m"), {"m": memory_id})
            await s.commit()
    except Exception:
        pass


async def graph_boost(conversation_id: int | None, query: str,
                      pool_conversation_ids: list[int] | None = None) -> dict[int, float]:
    """memory_id -> boost from query entities and their 1-hop graph neighbors.
    conversation_id=None boosts across the shared user-wide pool.
    pool_conversation_ids scopes the pool explicitly (multi-user seam, item 68);
    when set it wins over conversation_id. The 1-hop expansion runs in SQL -
    at thousands of users the old load-everything-into-Python pass falls over."""
    if not settings.graph_memory_enabled or not await graph_available():
        return {}
    qe = extract_entities(query)
    if not qe: return {}
    scope, params = "", {"names": qe}
    if pool_conversation_ids is not None:
        if not pool_conversation_ids: return {}
        scope = "AND conversation_id IN :cids"; params["cids"] = pool_conversation_ids
    elif conversation_id is not None:
        scope = "AND conversation_id = :c"; params["c"] = conversation_id
    sql = text(
        "WITH seed AS (SELECT id FROM graph_entities WHERE name IN :names " + scope + "), "
        "neighborhood AS ("
        "  SELECT id FROM seed UNION"
        "  SELECT src_id FROM graph_edges WHERE dst_id IN (SELECT id FROM seed) " + scope + " UNION"
        "  SELECT dst_id FROM graph_edges WHERE src_id IN (SELECT id FROM seed) " + scope + ") "
        "SELECT memory_id, SUM(weight) FROM graph_edges "
        "WHERE memory_id IS NOT NULL "
        "AND (src_id IN (SELECT id FROM neighborhood) OR dst_id IN (SELECT id FROM neighborhood)) " + scope + " "
        "GROUP BY memory_id")
    if "cids" in params:
        sql = sql.bindparams(bindparam("names", expanding=True), bindparam("cids", expanding=True))
    else:
        sql = sql.bindparams(bindparam("names", expanding=True))
    try:
        async with Session() as s:
            rows = (await s.execute(sql, params)).all()
        return {m: min(1.0, 0.25 * w) for m, w in rows}
    except Exception:
        return {}
