"""Code graph for the noesek package (roadmap item 49).

Graphify-style, deterministic and zero-dependency: stdlib ast parses every
module in the installed package and builds three maps - definitions
(functions/classes per module, with line numbers), call edges (which
function calls which names), and import edges (module -> modules). The
chat tool answers: what calls X, what does X call, what imports this
module, what does this module import, outline of a module, and stats.

No graph database, no vector store: the maps rebuild in about a second and
are cached against the newest source mtime. Graphify itself (Apache-2.0)
was studied for the query shapes; this is our own implementation.
"""
from __future__ import annotations

import ast
import os
import time
from pathlib import Path

from pydantic import BaseModel, Field


class CodeGraphInput(BaseModel):
    query: str = Field(description="callers | callees | importers | deps | outline | stats")
    symbol: str = Field(default="", max_length=200,
                        description="function, class, or module name (not needed for stats)")
    limit: int = Field(default=20, ge=1, le=100)


_CACHE: dict = {"stamp": None, "graph": None}


def _pkg_root() -> Path:
    import noesek
    return Path(noesek.__file__).resolve().parent


def _stamp(root: Path) -> float:
    newest = 0.0
    for p in root.rglob("*.py"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest


class _Visitor(ast.NodeVisitor):
    def __init__(self, module: str, graph: dict):
        self.module = module
        self.graph = graph
        self.stack: list[str] = []

    def _qual(self) -> str:
        return f"{self.module}." + ".".join(self.stack) if self.stack else self.module

    def visit_FunctionDef(self, node): self._def(node, "function")
    def visit_AsyncFunctionDef(self, node): self._def(node, "async function")

    def _def(self, node, kind):
        qual = self._qual() + "." + node.name if self.stack else f"{self.module}.{node.name}"
        self.graph["defs"].setdefault(node.name, []).append((qual, node.lineno, kind))
        self.graph["calls"].setdefault(qual, set())
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ClassDef(self, node):
        qual = self._qual() + "." + node.name if self.stack else f"{self.module}.{node.name}"
        self.graph["defs"].setdefault(node.name, []).append((qual, node.lineno, "class"))
        self.graph["calls"].setdefault(qual, set())
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Call(self, node):
        name = None
        f = node.func
        if isinstance(f, ast.Name):
            name = f.id
        elif isinstance(f, ast.Attribute):
            name = f.attr
        if name and self.stack:
            self.graph["calls"].setdefault(self._qual(), set()).add(name)
        self.generic_visit(node)

    def visit_Import(self, node):
        for a in node.names:
            self.graph["imports"][self.module].add(a.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.module:
            self.graph["imports"][self.module].add(node.module.split(".")[0])


def build_graph(root: Path | None = None) -> dict:
    root = root or _pkg_root()
    stamp = _stamp(root)
    if _CACHE["graph"] is not None and _CACHE["stamp"] == stamp and root == _CACHE.get("root"):
        return _CACHE["graph"]
    graph: dict = {"defs": {}, "calls": {}, "imports": {}, "files": 0, "skipped": []}
    for p in sorted(root.rglob("*.py")):
        module = "noesek." + ".".join(p.relative_to(root).with_suffix("").parts)
        module = module.replace(".__init__", "")
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            graph["skipped"].append(module)
            continue
        graph["files"] += 1
        graph["imports"].setdefault(module, set())
        _Visitor(module, graph).visit(tree)
    _CACHE.update({"stamp": stamp, "graph": graph, "root": root, "built_at": int(time.time())})
    return graph


def query_graph(inp: CodeGraphInput, root: Path | None = None) -> dict:
    g = build_graph(root)
    sym = inp.symbol.strip()
    q = inp.query.strip().lower()
    out: dict = {"query": q, "symbol": sym}

    if q == "stats":
        out["result"] = {"files": g["files"], "definitions": sum(len(v) for v in g["defs"].values()),
                         "call_edges": sum(len(v) for v in g["calls"].values()),
                         "skipped_unparsable": g["skipped"]}
        return out
    if not sym:
        return {"error": f"query '{q}' needs a symbol"}

    if q == "callers":
        hits = sorted({qual for qual, calls in g["calls"].items() if sym in calls})
        out["result"] = hits[: inp.limit]
        out["total"] = len(hits)
    elif q == "callees":
        quals = [qual for name, locs in g["defs"].items() if name == sym for qual, _, _ in locs]
        edges = sorted({c for qual in quals for c in g["calls"].get(qual, ())})
        out["defined_at"] = quals
        out["result"] = edges[: inp.limit]
        out["total"] = len(edges)
        if not quals:
            return {"error": f"'{sym}' is not defined in the package"}
    elif q == "importers":
        hits = sorted(m for m, deps in g["imports"].items() if any(d == sym or d.endswith("." + sym) for d in deps))
        out["result"] = hits[: inp.limit]
        out["total"] = len(hits)
    elif q == "deps":
        deps = sorted(g["imports"].get(sym) or g["imports"].get("noesek." + sym) or ())
        if not deps and sym not in g["imports"] and "noesek." + sym not in g["imports"]:
            return {"error": f"module '{sym}' not found"}
        out["result"] = deps[: inp.limit]
        out["total"] = len(deps)
    elif q == "outline":
        rows = []
        for name, locs in sorted(g["defs"].items()):
            for qual, lineno, kind in locs:
                if qual.startswith(f"noesek.{sym}.") or qual.startswith(sym + "."):
                    rows.append(f"{qual}:{lineno} ({kind})")
        out["result"] = sorted(rows)[: inp.limit]
        out["total"] = len(rows)
        if not rows:
            return {"error": f"no definitions found under module '{sym}'"}
    else:
        return {"error": "query must be one of: callers, callees, importers, deps, outline, stats"}
    return out


async def code_graph(inp: CodeGraphInput) -> dict:
    return query_graph(inp)
