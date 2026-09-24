"""Tests for the AST code-intelligence indexer (roadmap item 89)."""
from pathlib import Path

import pytest

from noesek.core.code_intel import index_root, parse_source, scan_root

pytest.importorskip("tree_sitter", reason="codeintel extra not installed")


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "a.py").write_text(
        'import b\nfrom c import helper\n\n\ndef alpha():\n    """Alpha does the thing."""\n'
        '    return beta() + helper()\n\n\nclass Calc:\n    def mul(self, x):\n        return alpha() * x\n')
    (tmp_path / "b.py").write_text("def beta():\n    return 1\n")
    (tmp_path / "c.py").write_text("def helper():\n    return 2\n")
    (tmp_path / "web.js").write_text(
        "function render(n) { return format(n); }\nconst format = (n) => n.toString();\n")
    (tmp_path / "app.ts").write_text(
        "export function boot(cfg: object): void { render(cfg); }\n")
    (tmp_path / "main.go").write_text(
        "package main\n\nfunc Add(a int, b int) int { return a + b }\n")
    (tmp_path / "bad.py").write_text("def broken(:\n")
    (tmp_path / "data.json").write_text('{"not": "indexed"}')
    return tmp_path


def test_symbols_across_languages(repo):
    scan = scan_root(repo)
    names = {(s["qualname"], s["kind"]) for s in scan["symbols"]}
    assert ("a.alpha", "function") in names
    assert ("a.Calc", "class") in names
    assert ("a.Calc.mul", "method") in names
    assert ("b.beta", "function") in names
    assert ("web.render", "function") in names
    assert ("web.format", "function") in names  # arrow fn assigned to const
    assert ("app.boot", "function") in names
    assert ("main.Add", "function") in names
    assert "data.json" not in scan["file_shas"]  # json is not symbol-indexed


def test_signatures_and_docstrings(repo):
    scan = scan_root(repo)
    by_qual = {s["qualname"]: s for s in scan["symbols"]}
    assert by_qual["a.alpha"]["docstring"] == "Alpha does the thing."
    assert by_qual["a.alpha"]["signature"].startswith("def alpha()")
    assert by_qual["main.Add"]["signature"].startswith("func Add(a int, b int) int")
    assert by_qual["a.alpha"]["start_line"] == 5
    assert by_qual["a.alpha"]["end_line"] == 7


def test_edges_confidence_labels(repo):
    scan = scan_root(repo)
    calls = {(e["src"], e["dst"], e["confidence"]) for e in scan["edges"]
             if e["relation"] == "calls"}
    # unique-name resolutions are EXTRACTED
    assert ("a.alpha", "b.beta", "EXTRACTED") in calls
    assert ("a.alpha", "c.helper", "EXTRACTED") in calls
    assert ("a.Calc.mul", "a.alpha", "EXTRACTED") in calls
    imports = {(e["src"], e["dst"]) for e in scan["edges"] if e["relation"] == "imports"}
    assert any(src == "a" and dst.startswith("mod:") for src, dst in imports)


def test_unparsable_file_recovered_not_fatal(repo):
    scan = scan_root(repo)
    # tree-sitter error recovery: the broken file is flagged, other files unaffected
    assert "bad.py" in scan["errors"]
    assert "bad.py" in scan["file_shas"]
    assert any(s["qualname"] == "a.alpha" for s in scan["symbols"])


def test_missing_grammar_skips_language(repo, monkeypatch):
    import noesek.core.code_intel as ci
    orig = ci._get_parser
    monkeypatch.setattr(ci, "_get_parser", lambda ext: None if ext == ".go" else orig(ext))
    scan = scan_root(repo)
    assert "main.go" in scan["skipped"]
    assert any(s["qualname"] == "web.render" for s in scan["symbols"])


def test_index_root_incremental(repo, tmp_path):
    db = str(tmp_path / "idx.db")
    stats1 = index_root(repo, db)
    assert stats1["files"] == 7  # 6 good sources + error-recovered bad.py (json excluded)
    stats2 = index_root(repo, db)
    assert stats2["changed"] == 0  # sha256-incremental: nothing re-scanned
    (repo / "b.py").write_text("def beta():\n    return 42\n")
    stats3 = index_root(repo, db)
    assert stats3["changed"] == 1  # only the modified file re-scanned
    import sqlite3
    con = sqlite3.connect(db)
    try:
        n = con.execute("SELECT COUNT(*) FROM code_symbols").fetchone()[0]
        assert n == stats1["symbols"]
        sig = con.execute("SELECT signature FROM code_symbols WHERE qualname='b.beta'").fetchone()[0]
        assert sig.startswith("def beta()")
    finally:
        con.close()


def test_index_root_file_removal(repo, tmp_path):
    db = str(tmp_path / "idx.db")
    index_root(repo, db)
    (repo / "c.py").unlink()
    stats = index_root(repo, db)
    assert stats["removed"] == 1
    import sqlite3
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM code_symbols WHERE path='c.py'").fetchone()[0] == 0
    finally:
        con.close()


def test_parse_source_is_pure_and_tolerant():
    out = parse_source("x.py", b"def f():\n    return g(\n")
    assert out["parsed"] is True  # tree-sitter recovers; partial symbols still usable
    out2 = parse_source("x.unknownext", b"whatever")
    assert out2 == {"symbols": [], "calls": [], "imports": [], "parsed": False,
                   "has_error": False}
