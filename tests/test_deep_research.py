"""P4: deep_research fan-out tool (multi-query search + dedupe + concurrent fetch)."""
from noesek.tools import research as R


def test_expand_queries_variants_and_cap():
    qs = R.expand_queries("What is the fastest way to render markdown in Python?", 6)
    assert qs[0].startswith("What is the fastest")
    assert any("render markdown python" in q for q in qs)
    assert len(qs) <= 6
    assert len({q.lower() for q in qs}) == len(qs)


def test_expand_queries_short_question():
    qs = R.expand_queries("rust", 4)
    assert qs[0] == "rust"
    assert len(qs) >= 2


async def test_deep_research_requires_key(monkeypatch):
    monkeypatch.setattr(R.settings, "brave_search_api_key", "")
    out = await R.deep_research(R.DeepResearchInput(question="anything at all"))
    assert out["error"] == "Search is not configured"


async def test_deep_research_fans_out_dedupes_and_fetches(monkeypatch):
    monkeypatch.setattr(R.settings, "brave_search_api_key", "k")
    calls = {"search": 0, "fetch": 0}

    async def fake_search(inp):
        calls["search"] += 1
        return {"results": [
            {"title": "A", "url": "https://a.example/1"},
            {"title": "B", "url": "https://b.example/2"},
            {"title": "A-dup", "url": "https://a.example/1"},
        ]}

    async def fake_fetch(inp):
        calls["fetch"] += 1
        return {"url": inp.url, "title": "T", "text": "body of " + inp.url, "truncated": False}

    monkeypatch.setattr(R, "search_web", fake_search)
    monkeypatch.setattr(R, "fetch_url", fake_fetch)
    out = await R.deep_research(R.DeepResearchInput(question="test subject", num_queries=3))
    assert calls["search"] == 3  # one search per expanded query
    urls = [s["url"] for s in out["sources"]]
    assert len(urls) == len(set(urls))  # deduped across queries
    assert calls["fetch"] == len(out["sources"]) == 2
    assert out["source_count"] == 2
    assert out["queries"][0]["hits"] == 3
    assert "Cite the source URLs" in out["instruction"]


async def test_deep_research_tolerates_fetch_failure(monkeypatch):
    monkeypatch.setattr(R.settings, "brave_search_api_key", "k")

    async def fake_search(inp):
        return {"results": [{"title": "A", "url": "https://a.example/1"},
                            {"title": "B", "url": "https://b.example/2"}]}

    async def fake_fetch(inp):
        if "b.example" in inp.url:
            return {"error": "Fetch failed: HTTPError"}
        return {"url": inp.url, "title": "T", "text": "ok", "truncated": False}

    monkeypatch.setattr(R, "search_web", fake_search)
    monkeypatch.setattr(R, "fetch_url", fake_fetch)
    out = await R.deep_research(R.DeepResearchInput(question="q here", num_queries=1))
    assert any("error" in s for s in out["sources"])
    assert any(s.get("snippet") == "ok" for s in out["sources"])


async def test_deep_research_empty_results(monkeypatch):
    monkeypatch.setattr(R.settings, "brave_search_api_key", "k")

    async def fake_search(inp):
        return {"results": []}

    monkeypatch.setattr(R, "search_web", fake_search)
    out = await R.deep_research(R.DeepResearchInput(question="obscure thing", num_queries=2))
    assert out["sources"] == []
    assert out["source_count"] == 0


def test_researcher_worker_has_deep_research():
    from noesek.workers.base import WORKERS
    assert "deep_research" in WORKERS["researcher"].tools


def test_deep_research_registered():
    from noesek.workers.runner import _all_tool_specs
    spec = _all_tool_specs()["deep_research"]
    assert spec.timeout_seconds == 90
