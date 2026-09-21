import re
import httpx
from pydantic import BaseModel, Field
from ..config import settings
from .web import FetchInput, fetch_url

class SearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    count: int = Field(default=5, ge=1, le=10)

async def search_web(inp: SearchInput):
    if not settings.brave_search_api_key:
        return {"error":"Search is not configured", "setup":"Set NOESEK_BRAVE_SEARCH_API_KEY"}
    headers={"X-Subscription-Token":settings.brave_search_api_key,"Accept":"application/json"}
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.get("https://api.search.brave.com/res/v1/web/search",params={"q":inp.query,"count":inp.count},headers=headers)
        r.raise_for_status(); data=r.json()
    return {"results":[{"title":x.get("title"),"url":x.get("url"),"description":x.get("description")} for x in data.get("web",{}).get("results",[])]}


class DeepResearchInput(BaseModel):
    question: str = Field(min_length=4, max_length=1000)
    num_queries: int = Field(default=4, ge=1, le=6)
    sources_per_query: int = Field(default=3, ge=1, le=5)
    max_sources: int = Field(default=8, ge=1, le=12)

_STOP = {"what","when","where","which","who","whom","why","how","the","a","an","is","are","was","were","does","do","did","can","could","should","would","will","of","in","on","for","to","and","or","vs","with","about","into","from","that","this","it","its","be","by","at","as"}

def expand_queries(question: str, num_queries: int) -> list[str]:
    """Deterministic multi-query fan-out (OpenResearch/ARIS idea, own implementation):
    the raw question plus keyword and facet reformulations, deduped, capped."""
    q = question.strip()
    out = [q]
    keywords = " ".join(w for w in re.findall(r"[a-z0-9]+", q.lower()) if w not in _STOP)
    if keywords and keywords != q.lower():
        out.append(keywords)
    for facet in ("explained", "latest developments", "compared"):
        cand = f"{q} {facet}"
        if cand.lower() not in {x.lower() for x in out}:
            out.append(cand)
    return out[:num_queries]

async def deep_research(inp: DeepResearchInput):
    """Fan-out research: expand the question into queries, search each, fetch and
    dedupe top sources concurrently, return a cited evidence pack for synthesis."""
    if not settings.brave_search_api_key:
        return {"error": "Search is not configured", "setup": "Set NOESEK_BRAVE_SEARCH_API_KEY"}
    queries = expand_queries(inp.question, inp.num_queries)
    per_query: list[dict] = []
    candidates: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        res = await search_web(SearchInput(query=q, count=inp.sources_per_query))
        if "error" in res:
            per_query.append({"query": q, "error": res["error"]})
            continue
        hits = res.get("results", [])
        per_query.append({"query": q, "hits": len(hits)})
        for h in hits:
            u = (h.get("url") or "").strip()
            if u and u not in seen and len(seen) < inp.max_sources:
                seen.add(u)
                candidates.append(h)
    import asyncio
    sem = asyncio.Semaphore(3)
    async def _fetch(h):
        async with sem:
            r = await fetch_url(FetchInput(url=h["url"], max_chars=2000))
            if "error" in r:
                return {"title": h.get("title"), "url": h.get("url"), "error": r["error"]}
            return {"title": r.get("title") or h.get("title"), "url": r.get("url"),
                    "snippet": (r.get("text") or "")[:2000], "truncated": r.get("truncated", False)}
    sources = await asyncio.gather(*(_fetch(h) for h in candidates)) if candidates else []
    return {"question": inp.question, "queries": per_query,
            "sources": list(sources), "source_count": len(sources),
            "instruction": "Synthesize an answer to the question from these sources. Cite the source URLs. Say plainly what the sources do not establish."}
