"""Tests for the code graph tool (roadmap item 49)."""
from pathlib import Path

import pytest

from noesek.tools.code_graph import CodeGraphInput, build_graph, query_graph


@pytest.fixture()
def pkg(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text(
        "import b\nfrom c import helper\n\n\ndef alpha():\n    return beta() + helper()\n")
    (tmp_path / "b.py").write_text("def beta():\n    return 1\n")
    (tmp_path / "c.py").write_text("def helper():\n    return 2\n")
    (tmp_path / "bad.py").write_text("def broken(:\n")
    monkeypatch.setattr("noesek.tools.code_graph._CACHE", {"stamp": None, "graph": None})
    return tmp_path


def test_stats_and_skips(pkg):
    out = query_graph(CodeGraphInput(query="stats"), root=pkg)
    assert out["result"]["files"] == 3
    assert out["result"]["definitions"] == 3
    assert out["result"]["skipped_unparsable"] == ["noesek.bad"]


def test_callers_and_callees(pkg):
    callers = query_graph(CodeGraphInput(query="callers", symbol="beta"), root=pkg)
    assert callers["result"] == ["noesek.a.alpha"]
    callees = query_graph(CodeGraphInput(query="callees", symbol="alpha"), root=pkg)
    assert set(callees["result"]) == {"beta", "helper"}
    assert callees["defined_at"] == ["noesek.a.alpha"]


def test_importers_and_deps(pkg):
    importers = query_graph(CodeGraphInput(query="importers", symbol="b"), root=pkg)
    assert importers["result"] == ["noesek.a"]
    deps = query_graph(CodeGraphInput(query="deps", symbol="a"), root=pkg)
    assert set(deps["result"]) == {"b", "c"}


def test_outline(pkg):
    out = query_graph(CodeGraphInput(query="outline", symbol="a"), root=pkg)
    assert out["result"] == ["noesek.a.alpha:5 (function)"]


def test_errors(pkg):
    assert "error" in query_graph(CodeGraphInput(query="callers"), root=pkg)
    assert "error" in query_graph(CodeGraphInput(query="callees", symbol="nope"), root=pkg)
    assert "error" in query_graph(CodeGraphInput(query="bogus", symbol="x"), root=pkg)


def test_cache_reuse(pkg):
    g1 = build_graph(pkg)
    g2 = build_graph(pkg)
    assert g1 is g2


def test_real_package_builds():
    g = build_graph()
    assert g["files"] > 100
    assert not g["skipped"]
