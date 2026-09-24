"""literature_search: parsing, dedupe, caps, source filter, degradation."""
import json

from noesek.tools.literature import LiteratureInput, literature_search
import noesek.tools.literature as lit

_ARXIV = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry><id>http://arxiv.org/abs/1234.5678v1</id><title>  Graph Memory for
 Agents </title><summary>We study graph memory.</summary><published>2026-01-02T00:00:00Z</published>
 <author><name>Alice</name></author><author><name>Bob</name></author></entry>
</feed>"""

_CROSSREF = json.dumps({"message": {"items": [{
    "DOI": "10.1/x", "title": ["Graph Memory for Agents"],
    "author": [{"given": "Alice", "family": "Smith"}],
    "published": {"date-parts": [[2026]]}, "URL": "https://doi.org/10.1/x"}]}}).encode()

_OPENALEX = json.dumps({"results": [{
    "id": "W1", "title": "Vector Stores for Agents", "publication_year": 2025,
    "authorships": [{"author": {"display_name": "Carol"}}],
    "abstract_inverted_index": {"hello": [0], "world": [1]}, "doi": "https://doi.org/10.2/y"}]}).encode()


def _fake_get(payloads):
    def get(url):
        for key, payload in payloads.items():
            if key in url:
                return payload
        raise RuntimeError("no fake for " + url)
    return get


def test_fanout_dedupes_and_sorts(monkeypatch):
    monkeypatch.setattr(lit, "_get", _fake_get({
        "arxiv.org": _ARXIV, "crossref.org": _CROSSREF, "openalex.org": _OPENALEX,
        }))  # semanticscholar absent from the fake -> its call raises
    out = literature_search(LiteratureInput(query="graph memory", max_results=5))
    # arXiv + Crossref share a normalized title -> deduped to one; openalex second
    assert out["count"] == 2
    assert out["results"][0]["year"] == "2026"
    assert out["results"][1]["title"] == "Vector Stores for Agents"
    assert "semanticscholar" in out["source_errors"]
    assert out["results"][1]["abstract"] == "hello world"


def test_single_source_and_cap(monkeypatch):
    monkeypatch.setattr(lit, "_get", _fake_get({"arxiv.org": _ARXIV}))
    out = literature_search(LiteratureInput(query="xy", source="arxiv", max_results=1))
    assert out["count"] == 1
    assert out["results"][0]["source"] == "arxiv"
    assert "source_errors" not in out


def test_unknown_source():
    out = literature_search(LiteratureInput(query="xy", source="nope"))
    assert "error" in out and "arxiv" in out["sources"]


def test_all_sources_down_returns_zero_not_crash(monkeypatch):
    monkeypatch.setattr(lit, "_get", _fake_get({}))
    out = literature_search(LiteratureInput(query="xy"))
    assert out["count"] == 0 and len(out["source_errors"]) == 4
