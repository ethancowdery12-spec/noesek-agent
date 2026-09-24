"""code_intel chat tool (roadmap item 89 M2): symbol-level code search over the
tree-sitter AST index - answers "where is X", "show me the code for Y", "what
calls Z" with the relevant functions/classes instead of whole files. Thin
wrapper over core.code_intel (indexing + retrieval live there). Requires the
optional [codeintel] extra; degrades with a clear message when unindexed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import settings
from ..core.code_intel import default_root, index_root, retrieve


class CodeIntelInput(BaseModel):
    action: str = Field(description="search | callers | callees | reindex | stats")
    query: str = Field(default="", max_length=400,
                       description="for search: what the code should do, or a symbol name")
    symbol: str = Field(default="", max_length=200,
                        description="for callers/callees: function or class name")
    limit: int = Field(default=5, ge=1, le=20)


def _db():
    return settings.code_intel_db


def _root():
    return settings.code_intel_root or default_root()


def _con():
    import os
    import sqlite3
    if not os.path.exists(_db()):
        return None
    return sqlite3.connect(_db())


async def code_intel(inp: CodeIntelInput) -> dict:
    a = inp.action.strip().lower()
    if a == "reindex":
        stats = index_root(_root(), _db())
        return {"result": stats}
    if a == "stats":
        con = _con()
        if con is None:
            return {"result": {"indexed": False,
                               "hint": "no index yet - run reindex (needs the [codeintel] extra)"}}
        try:
            files = con.execute("SELECT COUNT(*) FROM code_files").fetchone()[0]
            syms = con.execute("SELECT COUNT(*) FROM code_symbols").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM code_edges").fetchone()[0]
            return {"result": {"indexed": True, "files": files, "symbols": syms,
                               "edges": edges, "root": _root()}}
        finally:
            con.close()
    if a == "search":
        ret = retrieve(_db(), inp.query, root=_root(), limit=inp.limit)
        if not ret["seeds"]:
            return {"result": {"matches": [],
                               "hint": "no symbol matches (or no index yet - try reindex)"}}
        matches = [{"qualname": s["qualname"], "kind": s["kind"],
                    "path": s["path"], "lines": f"L{s['start_line']}-L{s['end_line']}",
                    "signature": s["signature"],
                    "docstring": s["docstring"][:120]} for s in ret["seeds"]]
        out = {"matches": matches,
               "neighbors": [s["qualname"] for s in ret["neighbors"]]}
        if ret["slices"]:
            out["source"] = [{"qualname": sl["qualname"], "path": sl["path"],
                              "start_line": sl["start_line"], "text": sl["text"]}
                             for sl in ret["slices"][:3]]
        return {"result": out}
    if a in ("callers", "callees"):
        name = inp.symbol.strip()
        if not name:
            return {"error": "symbol is required for callers/callees"}
        con = _con()
        if con is None:
            return {"error": "no index yet - run reindex first"}
        try:
            quals = [r[0] for r in con.execute(
                "SELECT qualname FROM code_symbols WHERE name=? OR qualname=?",
                (name, name))]
            if not quals:
                return {"result": []}
            hits: set[str] = set()
            for q in quals:
                col, other = ("dst", "src") if a == "callers" else ("src", "dst")
                for (v,) in con.execute(
                        f"SELECT {other} FROM code_edges WHERE relation='calls' AND {col}=?",
                        (q,)):
                    hits.add(v)
            return {"result": sorted(hits)}
        finally:
            con.close()
    return {"error": f"unknown action {inp.action!r}: search | callers | callees | reindex | stats"}
