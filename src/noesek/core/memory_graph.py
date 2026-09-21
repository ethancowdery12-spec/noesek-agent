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

from sqlalchemy import text

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
    if not ents:
        ents = [t for t in _LOWER.findall(content.lower()) if t not in _STOP][:5]
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


async def graph_boost(conversation_id: int, query: str) -> dict[int, float]:
    """memory_id -> boost from query entities and their 1-hop graph neighbors."""
    if not settings.graph_memory_enabled or not await graph_available():
        return {}
    qe = extract_entities(query)
    if not qe: return {}
    try:
        async with Session() as s:
            rows = (await s.execute(text(
                "SELECT id, name FROM graph_entities WHERE conversation_id = :c"),
                {"c": conversation_id})).all()
            by_name = {n: i for i, n in rows}
            seed = {by_name[n] for n in qe if n in by_name}
            if not seed: return {}
            edges = (await s.execute(text(
                "SELECT src_id, dst_id, weight, memory_id FROM graph_edges WHERE conversation_id = :c"),
                {"c": conversation_id})).all()
        neighborhood = set(seed)
        for s_, d_, w_, m_ in edges:
            if s_ in seed or d_ in seed:
                neighborhood.add(s_); neighborhood.add(d_)
        boosts: dict[int, float] = {}
        for s_, d_, w_, m_ in edges:
            if m_ is None: continue
            if s_ in neighborhood or d_ in neighborhood:
                boosts[m_] = min(1.0, boosts.get(m_, 0.0) + 0.25 * w_)
        return boosts
    except Exception:
        return {}
