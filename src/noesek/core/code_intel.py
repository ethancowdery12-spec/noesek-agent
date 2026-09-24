"""AST code intelligence (roadmap item 89, Ethan Sep 24): tree-sitter parses a
repo into a symbol/call graph so code questions retrieve the relevant
FUNCTIONS/CLASSES instead of whole files ("no ingesting whole files and aimless
search"). Design studied from graphify (safishamsi/graphify, Apache-2.0/MIT -
pipeline shape, symbol+neighborhood retrieval unit, EXTRACTED/INFERRED/
AMBIGUOUS confidence labels, sha256-incremental cache); this is our own
implementation, nothing copied.

Layering: parse_source()/scan_root() are pure (no DB, no settings) so tests and
the fallback path stay simple; index_root() persists to a stdlib-sqlite3
sidecar DB (settings.code_intel_db) with sha256-incremental rescans. Every
grammar import is lazy and optional: a missing grammar skips that language, and
if tree-sitter itself is absent the module still imports (tools/code_graph.py
stdlib-ast remains the fallback). Flag: settings.code_intel_enabled (default
off) gates callers, not this module.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from pathlib import Path

# ext -> (tree-sitter module, factory attribute or "" for .language())
_LANGS = {
    ".py": ("tree_sitter_python", ""),
    ".js": ("tree_sitter_javascript", ""), ".mjs": ("tree_sitter_javascript", ""),
    ".cjs": ("tree_sitter_javascript", ""), ".jsx": ("tree_sitter_javascript", ""),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".go": ("tree_sitter_go", ""),
    ".rs": ("tree_sitter_rust", ""),
    ".java": ("tree_sitter_java", ""),
    ".c": ("tree_sitter_c", ""), ".h": ("tree_sitter_c", ""),
    ".cpp": ("tree_sitter_cpp", ""), ".cc": ("tree_sitter_cpp", ""),
    ".hpp": ("tree_sitter_cpp", ""), ".cxx": ("tree_sitter_cpp", ""),
    ".rb": ("tree_sitter_ruby", ""),
    ".cs": ("tree_sitter_c_sharp", ""),
    ".php": ("tree_sitter_php", ""),
    ".sh": ("tree_sitter_bash", ""), ".bash": ("tree_sitter_bash", ""),
    ".json": ("tree_sitter_json", ""),
}

# node types that introduce a named definition, per grammar family.
_DEF_TYPES = {
    ".py": {"function_definition": "function", "class_definition": "class"},
    ".js": {"function_declaration": "function", "class_declaration": "class",
            "method_definition": "method", "arrow_function": "function",
            "function_expression": "function"},
    ".go": {"function_declaration": "function", "method_declaration": "method",
            "type_declaration": "type"},
    ".rs": {"function_item": "function", "struct_item": "struct",
            "enum_item": "enum", "trait_item": "trait", "impl_item": "impl"},
    ".java": {"class_declaration": "class", "method_declaration": "method",
              "interface_declaration": "interface", "enum_declaration": "enum",
              "constructor_declaration": "constructor"},
    ".c": {"function_definition": "function"},
    ".rb": {"method": "method", "class": "class", "module": "module",
            "singleton_method": "method"},
    ".cs": {"class_declaration": "class", "method_declaration": "method",
            "interface_declaration": "interface", "struct_declaration": "struct",
            "constructor_declaration": "constructor"},
    ".php": {"function_definition": "function", "class_declaration": "class",
             "method_declaration": "method"},
    ".sh": {"function_definition": "function"},
    ".json": {},
}
for _a, _b in [(".mjs", ".js"), (".cjs", ".js"), (".jsx", ".js"), (".ts", ".js"),
               (".tsx", ".js"), (".cpp", ".c"), (".cc", ".c"), (".cxx", ".c"),
               (".h", ".c"), (".hpp", ".c"), (".bash", ".sh")]:
    _DEF_TYPES[_a] = dict(_DEF_TYPES[_b])

_CALL_TYPES = {"call", "call_expression", "method_invocation", "invocation_expression",
               "function_call_expression", "command"}
_IMPORT_TYPES = {"import_statement", "import_from_statement", "import_declaration",
                 "use_declaration", "preproc_include", "using_directive"}
_IDENT_TYPES = {"identifier", "property_identifier", "field_identifier", "type_identifier",
                "attribute", "shorthand_property_identifier", "command_name", "word"}
_NAME_FIELDS = ("name", "function", "method", "command")

_DDL = """
CREATE TABLE IF NOT EXISTS code_files(path TEXT PRIMARY KEY, sha256 TEXT, scanned_at REAL);
CREATE TABLE IF NOT EXISTS code_symbols(
  id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, qualname TEXT, name TEXT,
  kind TEXT, signature TEXT, docstring TEXT, start_line INTEGER, end_line INTEGER,
  UNIQUE(path, qualname));
CREATE TABLE IF NOT EXISTS code_edges(
  id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, src TEXT, dst TEXT,
  relation TEXT, confidence TEXT, UNIQUE(path, src, dst, relation));
CREATE INDEX IF NOT EXISTS idx_code_symbols_name ON code_symbols(name);
CREATE INDEX IF NOT EXISTS idx_code_edges_dst ON code_edges(dst);
"""

_MAX_FILE_BYTES = 1_000_000
_MAX_DOCSTRING = 200


def _get_parser(ext: str):
    """Lazy per-language parser; None when the grammar (or tree-sitter) is absent."""
    spec = _LANGS.get(ext)
    if not spec:
        return None
    try:
        from tree_sitter import Language, Parser
        mod = __import__(spec[0])
        factory = getattr(mod, spec[1] or "language")
        return Parser(Language(factory()))
    except Exception:
        return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _def_name(node, source: bytes) -> str:
    n = node.child_by_field_name("name")
    if n is not None:
        return _text(n, source)
    # js/ts: const f = () => ... - the declarator's parent holds the name.
    p = node.parent
    if p is not None and p.type == "variable_declarator":
        n = p.child_by_field_name("name")
        if n is not None:
            return _text(n, source)
    return ""


def _signature(node, source: bytes) -> str:
    """First line of the definition up to its body (stable, language-agnostic)."""
    body = node.child_by_field_name("body")
    end = body.start_byte if body is not None else node.end_byte
    sig = source[node.start_byte:end].decode("utf-8", "replace").splitlines()
    line = sig[0].strip() if sig else ""
    return line[:160]


def _py_docstring(node, source: bytes) -> str:
    body = node.child_by_field_name("body")
    if body is None or not body.named_children:
        return ""
    first = body.named_children[0]
    if first.type == "expression_statement" and first.named_children and \
            first.named_children[0].type in ("string", "concatenated_string"):
        return _text(first.named_children[0], source).strip("\"' \n")[:_MAX_DOCSTRING]
    return ""


def _callee_name(node, source: bytes) -> str:
    """Best-effort callee identifier from a call node across grammars."""
    fn = None
    for f in _NAME_FIELDS:
        fn = node.child_by_field_name(f)
        if fn is not None:
            break
    target = fn if fn is not None else node
    last = ""
    stack = [target]
    while stack:
        n = stack.pop()
        if n.type in _IDENT_TYPES:
            last = _text(n, source)  # keep walking: attribute/member chains - last ident wins
        stack.extend(n.named_children)
    return last[:80]


def _import_target(node, source: bytes) -> str:
    txt = _text(node, source).replace("\n", " ")
    return " ".join(txt.split())[:120]


def parse_source(relpath: str, source: bytes, ext: str | None = None) -> dict:
    """Parse one file into symbols + raw (unresolved) edges. Pure, no DB."""
    ext = ext or os.path.splitext(relpath)[1].lower()
    out = {"symbols": [], "calls": [], "imports": [], "parsed": False,
           "has_error": False}
    parser = _get_parser(ext)
    defs = _DEF_TYPES.get(ext)
    if parser is None or defs is None:
        return out
    try:
        tree = parser.parse(source)
    except Exception:
        return out
    out["parsed"] = True
    out["has_error"] = bool(tree.root_node.has_error)
    module = relpath.replace(os.sep, "/").rsplit(".", 1)[0].replace("/", ".")

    def walk(node, stack):
        t = node.type
        inner = node
        if t == "decorated_definition" and node.named_children:
            inner = node.named_children[-1]
            t = inner.type
        kind = defs.get(t)
        if kind:
            name = _def_name(inner, source)
            if name:
                if kind == "function" and any(k in ("class", "impl", "interface")
                                              for _, k in stack):
                    kind = "method"
                qual = ".".join([module, *[n for n, _ in stack], name])
                doc = _py_docstring(inner, source) if ext == ".py" else ""
                out["symbols"].append({
                    "qualname": qual, "name": name, "kind": kind,
                    "signature": _signature(inner, source), "docstring": doc,
                    "start_line": inner.start_point[0] + 1,
                    "end_line": inner.end_point[0] + 1})
                stack = stack + [(name, kind)]
        elif t in _CALL_TYPES:
            callee = _callee_name(node, source)
            if callee:
                src = ".".join([module, *[n for n, _ in stack]]) if stack else module
                out["calls"].append({"src": src, "callee": callee})
        elif t in _IMPORT_TYPES:
            out["imports"].append({"target": _import_target(node, source)})
        for ch in node.named_children:
            walk(ch, stack)

    walk(tree.root_node, [])
    return out


def iter_sources(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in {".git", "__pycache__", "node_modules", ".venv", "vendor"} for part in p.parts):
            continue
        ext = p.suffix.lower()
        if ext not in _LANGS or ext == ".json":
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
            yield p, ext
        except OSError:
            continue


def scan_root(root) -> dict:
    """Full pure scan of a tree: symbols (each tagged with its path), resolved
    call edges, import edges, per-file shas. Single parse pass."""
    root = Path(root)
    by_name: dict[str, list[dict]] = {}
    per_file: dict[str, dict] = {}
    skipped: list[str] = []
    errors: list[str] = []
    flat: list[dict] = []
    for p, ext in iter_sources(root):
        rel = str(p.relative_to(root))
        try:
            data = p.read_bytes()
        except OSError:
            continue
        parsed = parse_source(rel, data, ext)
        if not parsed["parsed"]:
            skipped.append(rel)
            continue
        if parsed["has_error"]:
            errors.append(rel)
        per_file[rel] = {"sha256": _sha256(data), "parsed": parsed}
        for s in parsed["symbols"]:
            s["path"] = rel
            flat.append(s)
            by_name.setdefault(s["name"], []).append(s)
    edges: list[dict] = []
    for rel, info in per_file.items():
        parsed = info["parsed"]
        module = rel.replace(os.sep, "/").rsplit(".", 1)[0].replace("/", ".")
        for c in parsed["calls"]:
            cands = by_name.get(c["callee"], [])
            if len(cands) == 1:
                edges.append({"path": rel, "src": c["src"], "dst": cands[0]["qualname"],
                              "relation": "calls", "confidence": "EXTRACTED"})
            elif len(cands) > 1:
                for cand in cands[:3]:
                    edges.append({"path": rel, "src": c["src"], "dst": cand["qualname"],
                                  "relation": "calls", "confidence": "AMBIGUOUS"})
        for i in parsed["imports"]:
            edges.append({"path": rel, "src": module, "dst": "mod:" + i["target"],
                          "relation": "imports", "confidence": "EXTRACTED"})
    return {"files": len(per_file), "skipped": skipped, "errors": errors,
            "symbols": flat, "edges": edges,
            "file_shas": {k: v["sha256"] for k, v in per_file.items()}}


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.executescript(_DDL)
    return con


def index_root(root, db_path: str) -> dict:
    """sha256-incremental scan persisted to the sidecar DB. Returns stats."""
    scan = scan_root(root)
    con = _connect(db_path)
    try:
        old = {r[0]: r[1] for r in con.execute("SELECT path, sha256 FROM code_files")}
        changed = [rel for rel, sha in scan["file_shas"].items() if old.get(rel) != sha]
        removed = [rel for rel in old if rel not in scan["file_shas"]]
        now = time.time()
        with con:
            for rel in changed + removed:
                con.execute("DELETE FROM code_files WHERE path=?", (rel,))
                con.execute("DELETE FROM code_symbols WHERE path=?", (rel,))
                con.execute("DELETE FROM code_edges WHERE path=?", (rel,))
            for rel in changed:
                con.execute("INSERT INTO code_files VALUES (?,?,?)",
                            (rel, scan["file_shas"][rel], now))
            for s in scan["symbols"]:
                if s["path"] in changed:
                    con.execute(
                        "INSERT OR REPLACE INTO code_symbols(path,qualname,name,kind,signature,docstring,start_line,end_line)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (s["path"], s["qualname"], s["name"], s["kind"], s["signature"],
                         s["docstring"], s["start_line"], s["end_line"]))
            for e in scan["edges"]:
                if e["path"] in changed:
                    con.execute("INSERT OR IGNORE INTO code_edges(path,src,dst,relation,confidence)"
                                " VALUES (?,?,?,?,?)",
                                (e["path"], e["src"], e["dst"], e["relation"], e["confidence"]))
        return {"files": scan["files"], "changed": len(changed), "removed": len(removed),
                "symbols": len(scan["symbols"]), "edges": len(scan["edges"]),
                "skipped": scan["skipped"], "errors": scan["errors"]}
    finally:
        con.close()
