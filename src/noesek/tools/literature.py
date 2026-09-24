"""literature_search: academic paper search across open scholarly APIs.

Roadmap item 70 (skills batch 1). Own implementation over public APIs -
the convenience libraries (arxiv, scholarly, habanero) ship without clear
licenses, so we call the APIs directly per the research verdict. Zero deps.

Sources (all free, no key):
- arXiv: export.arxiv.org/api/query (Atom XML)
- Crossref: api.crossref.org/works (JSON; polite pool via User-Agent)
- Semantic Scholar: api.semanticscholar.org/graph/v1/paper/search (JSON)
- OpenAlex: api.openalex.org/works (JSON)
"""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

_UA = {"User-Agent": "noesek-literature-search/1.0 (contact: github.com/ethancowdery12-spec/noesek-agent)"}
_TIMEOUT = 12
_ATOM = "{http://www.w3.org/2005/Atom}"


class LiteratureInput(BaseModel):
    query: str = Field(min_length=2, max_length=500, description="Search terms - title words, authors, topic")
    source: str = Field(default="auto", description="auto | arxiv | crossref | semanticscholar | openalex")
    max_results: int = Field(default=5, ge=1, le=20)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read(2_000_000)


def _arxiv(query: str, n: int) -> list:
    url = ("https://export.arxiv.org/api/query?search_query=all:"
           + urllib.parse.quote(query) + f"&max_results={n}&sortBy=relevance")
    root = ET.fromstring(_get(url))
    out = []
    for e in root.findall(f"{_ATOM}entry"):
        title = re.sub(r"\s+", " ", (e.findtext(f"{_ATOM}title") or "").strip())
        authors = [a.findtext(f"{_ATOM}name") or "" for a in e.findall(f"{_ATOM}author")]
        out.append({
            "source": "arxiv",
            "title": title,
            "authors": ", ".join(a for a in authors[:4] if a),
            "year": (e.findtext(f"{_ATOM}published") or "")[:4],
            "abstract": re.sub(r"\s+", " ", (e.findtext(f"{_ATOM}summary") or "").strip())[:400],
            "url": (e.findtext(f"{_ATOM}id") or "").strip(),
        })
    return out


def _crossref(query: str, n: int) -> list:
    url = ("https://api.crossref.org/works?query=" + urllib.parse.quote(query)
           + f"&rows={n}&select=DOI,title,author,published,abstract,URL")
    items = (json.loads(_get(url)).get("message") or {}).get("items") or []
    out = []
    for it in items:
        authors = ", ".join(
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in (it.get("author") or [])[:4])
        year = ""
        for key in ("published", "published-print", "published-online"):
            parts = ((it.get(key) or {}).get("date-parts") or [[None]])[0]
            if parts and parts[0]:
                year = str(parts[0])
                break
        abstract = re.sub(r"<[^>]+>|\s+", " ", it.get("abstract") or "").strip()[:400]
        out.append({
            "source": "crossref",
            "title": (it.get("title") or [""])[0],
            "authors": authors,
            "year": year,
            "abstract": abstract,
            "url": it.get("URL") or (f"https://doi.org/{it['DOI']}" if it.get("DOI") else ""),
        })
    return out


def _semanticscholar(query: str, n: int) -> list:
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?query="
           + urllib.parse.quote(query)
           + f"&limit={n}&fields=title,authors,year,abstract,url,externalIds")
    out = []
    for p in json.loads(_get(url)).get("data") or []:
        out.append({
            "source": "semanticscholar",
            "title": p.get("title") or "",
            "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:4]),
            "year": str(p.get("year") or ""),
            "abstract": (p.get("abstract") or "")[:400],
            "url": p.get("url") or "",
        })
    return out


def _openalex(query: str, n: int) -> list:
    url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(query)
           + f"&per-page={n}&select=id,title,authorships,publication_year,abstract_inverted_index,doi")
    out = []
    for w in json.loads(_get(url)).get("results") or []:
        authors = ", ".join(
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])[:4])
        abstract = ""
        inv = w.get("abstract_inverted_index")
        if inv:  # reconstruct plain text from the inverted index
            pos = {}
            for word, idxs in inv.items():
                for i in idxs:
                    pos[i] = word
            abstract = " ".join(pos[i] for i in sorted(pos))[:400]
        out.append({
            "source": "openalex",
            "title": w.get("title") or "",
            "authors": authors,
            "year": str(w.get("publication_year") or ""),
            "abstract": abstract,
            "url": w.get("doi") or w.get("id") or "",
        })
    return out


_SOURCES = {
    "arxiv": _arxiv,
    "crossref": _crossref,
    "semanticscholar": _semanticscholar,
    "openalex": _openalex,
}


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def literature_search(inp: LiteratureInput) -> dict:
    source = inp.source.strip().lower() or "auto"
    if source == "auto":
        names = list(_SOURCES)
        per = max(1, min(inp.max_results, 6))
    elif source in _SOURCES:
        names, per = [source], inp.max_results
    else:
        return {"error": f"unknown source {inp.source!r}", "sources": sorted(_SOURCES)}

    results, errors = [], {}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        fut = {pool.submit(_SOURCES[n], inp.query, per): n for n in names}
        for f, n in fut.items():
            try:
                results.extend(f.result())
            except Exception as exc:
                errors[n] = str(exc)[:200]

    seen, deduped = set(), []
    for r in sorted(results, key=lambda r: (r.get("year") or ""), reverse=True):
        key = _norm_title(r.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(r)
        if len(deduped) >= inp.max_results:
            break
    out = {"query": inp.query, "count": len(deduped), "results": deduped}
    if errors:
        out["source_errors"] = errors
    return out
