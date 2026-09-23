"""GEO audit - Generative Engine Optimization for HTML deliverables.

Ethan Sep 23: "Maybe study and poddibly implement open seo and or geo
optimizer skill". Companion to seo_audit (#121): seo_audit asks "will this
page rank", geo_audit asks "will AI answers cite this page".

Source study: Auriti-Labs/geo-optimizer-skill VERIFIED real and MIT on-disk
(Copyright 2026 Juan Camilo Auriti; full text at
docs/licenses/GEO-OPTIMIZER-SKILL-MIT.txt). Its method families derive from
the GEO research line (Aggarwal et al., KDD 2024, arXiv 2311.09735, and the
AutoGEO follow-up): the methods with measured citation lift are citing
sources, quoting experts, adding statistics, and answer-ready structure.
Knowledge studied and REIMPLEMENTED own-words per the reuse posture; no code
copied. Deterministic, stdlib-only, no new dependencies.

What is auditable in one HTML page (+ optional robots.txt / llms.txt):
  - citations to outside sources (the single strongest measured GEO method)
  - statistics and quotations in the content
  - an answer-ready lead (direct answer up front, not throat-clearing)
  - question-form headings matching how people prompt AI engines
  - extractable structure (lists/tables/summary blocks)
  - entity clarity via JSON-LD (@type + sameAs to authority records)
  - freshness signals (datePublished/dateModified)
  - AI-crawler access in robots.txt (GPTBot, ClaudeBot, PerplexityBot, ...)
  - llms.txt presence (the emerging AI-facing site map convention)
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class GeoAuditInput(BaseModel):
    html: str = Field(min_length=20, max_length=400000, description="The page's full HTML source")
    robots_txt: str = Field(default="", max_length=100000,
                            description="Optional: the site's robots.txt content, for AI-crawler access checks")
    llms_txt: str = Field(default="", max_length=100000,
                          description="Optional: the site's llms.txt content, if it exists")


# AI answer-engine crawlers worth explicitly allowing. Blocked = the site
# opts out of being cited by that engine.
AI_CRAWLERS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User",
               "PerplexityBot", "Google-Extended", "Bytespider", "CCBot"]

_ENTITY_TYPES = {"Organization", "Person", "LocalBusiness", "Corporation", "Brand"}


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.text_parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.text_parts.append(data.strip())


def _check(cid, bucket, weight, verdict, evidence, fix):
    return {"id": cid, "bucket": bucket, "weight": weight, "verdict": verdict,
            "evidence": evidence[:200], "fix": fix[:300]}


def _jsonld_items(html: str) -> list[dict]:
    items = []
    for b in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(b)
            items.extend(data if isinstance(data, list) else [data])
        except Exception:
            continue
    return [it for it in items if isinstance(it, dict)]


def audit_geo(html: str, robots_txt: str = "", llms_txt: str = "") -> dict:
    p = _Page(); p.feed(html)
    text = " ".join(p.text_parts)
    checks = []

    # --- citations: outbound links to other domains (strongest measured method)
    page_hosts = set()
    links = []
    for t, a in p.tags:
        if t == "a" and a.get("href", "").startswith(("http://", "https://")):
            links.append(a["href"])
    for t, a in p.tags:
        if t in ("link",) and a.get("rel") and "canonical" in " ".join(a["rel"] if isinstance(a["rel"], list) else [a["rel"]]):
            page_hosts.add(urlparse(a.get("href", "")).netloc)
    ext_hosts = {urlparse(u).netloc for u in links} - page_hosts - {""}
    _social = ("facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com")
    ext_hosts = {h for h in ext_hosts if h and h not in _social and not any(h.endswith("." + s) for s in _social)}
    n_ext = len(ext_hosts)
    checks.append(_check("citations", "authority", 3,
                         "pass" if n_ext >= 2 else ("warn" if n_ext == 1 else "fail"),
                         f"{n_ext} external source domains linked" + (f" ({', '.join(sorted(ext_hosts))[:80]})" if ext_hosts else ""),
                         "" if n_ext >= 2 else "cite authoritative outside sources with links - the strongest measured lift for AI citations"))

    # --- statistics: numbers with units/percent in prose
    stats = len(re.findall(r"\d+(?:\.\d+)?\s?%|\$\s?\d|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand|x|times|percent|users|people|years|days)\b", text, re.I))
    checks.append(_check("statistics", "authority", 2,
                         "pass" if stats >= 3 else ("warn" if stats >= 1 else "fail"),
                         f"{stats} quantitative statements",
                         "" if stats >= 3 else "add concrete numbers (percentages, figures, timeframes) - quantitative content is cited more"))

    # --- quotations
    quotes = sum(1 for t, _ in p.tags if t in ("blockquote", "q"))
    checks.append(_check("quotations", "authority", 1,
                         "pass" if quotes >= 1 else "warn",
                         f"{quotes} blockquote/q elements",
                         "" if quotes else "quote experts or primary sources verbatim where it adds weight"))

    # --- answer-ready lead: first paragraph after the h1 is a direct answer
    m = re.search(r"<h1[^>]*>.*?</h1>(.*?)</p>", html, re.S | re.I)
    lead_words = len(re.findall(r"[a-zA-Z0-9']+", re.sub(r"<[^>]+>", " ", m.group(1)))) if m else 0
    definitional = bool(m and re.search(r"\b(is|are|means|refers to|is a|is an|is the)\b", re.sub(r"<[^>]+>", " ", m.group(1))))
    if not m:
        checks.append(_check("answer_lead", "answer_ready", 2, "warn", "no h1 -> first paragraph sequence found",
                             "open with a 30-90 word paragraph that directly answers the page's core question"))
    elif definitional and 25 <= lead_words <= 110:
        checks.append(_check("answer_lead", "answer_ready", 2, "pass", f"lead answers directly ({lead_words} words)", ""))
    else:
        checks.append(_check("answer_lead", "answer_ready", 2, "warn",
                             f"lead is {lead_words} words, definitional={'yes' if definitional else 'no'}",
                             "make the first paragraph a self-contained direct answer an AI can quote verbatim"))

    # --- question-form headings (match how people prompt engines)
    heads = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", html, re.S | re.I)
    q_heads = [h for h in heads if re.sub(r"<[^>]+>", "", h).strip().endswith("?")]
    checks.append(_check("question_headings", "answer_ready", 2,
                         "pass" if q_heads else "warn",
                         f"{len(q_heads)}/{len(heads)} h2/h3 are questions",
                         "" if q_heads else "phrase some headings as the exact questions users ask AI engines"))

    # --- extractable structure
    struct = sum(1 for t, _ in p.tags if t in ("ul", "ol", "table"))
    checks.append(_check("extractable_structure", "answer_ready", 1,
                         "pass" if struct >= 1 else "warn",
                         f"{struct} list/table blocks",
                         "" if struct else "use lists and tables for key facts - engines extract them cleanly"))

    # --- entity clarity via JSON-LD
    items = _jsonld_items(html)
    def _types(it):
        t = it.get("@type")
        return set(t if isinstance(t, list) else [t]) if t else set()
    entity = [it for it in items if _types(it) & _ENTITY_TYPES]
    sameas = any(it.get("sameAs") for it in entity)
    if not items:
        checks.append(_check("entity_clarity", "entity", 3, "warn", "no JSON-LD at all",
                             "add Organization/Person JSON-LD with sameAs links to authority records (Wikidata, official profiles)"))
    elif not entity:
        checks.append(_check("entity_clarity", "entity", 3, "warn", "JSON-LD present but no entity type",
                             "declare who is behind the page: Organization/Person with sameAs"))
    elif not sameas:
        checks.append(_check("entity_clarity", "entity", 3, "warn", "entity declared without sameAs",
                             "add sameAs links so engines can disambiguate the entity"))
    else:
        checks.append(_check("entity_clarity", "entity", 3, "pass", "entity with sameAs links", ""))

    # --- freshness
    fresh = any(it.get("datePublished") or it.get("dateModified") for it in items) or bool(re.search(r"<time[^>]+datetime", html, re.I))
    checks.append(_check("freshness", "entity", 1,
                         "pass" if fresh else "warn",
                         "machine-readable dates present" if fresh else "no datePublished/dateModified/<time>",
                         "" if fresh else "expose publish/update dates - engines prefer current sources"))

    # --- AI crawler access (robots.txt, optional)
    if not robots_txt.strip():
        checks.append(_check("ai_crawler_access", "access", 2, "info", "robots.txt not provided",
                             "pass robots_txt to check AI-crawler access (GPTBot, ClaudeBot, PerplexityBot, ...)"))
    else:
        blocked = []
        for ua in AI_CRAWLERS:
            m2 = re.search(rf"User-agent:\s*{re.escape(ua)}\s*((?:[^\n]*\n)*?)(?=User-agent:|\Z)", robots_txt, re.I)
            if m2 and re.search(r"Disallow:\s*/\s*$", m2.group(1), re.M):
                blocked.append(ua)
        checks.append(_check("ai_crawler_access", "access", 2,
                             "fail" if blocked else "pass",
                             f"blocked AI crawlers: {', '.join(blocked)}" if blocked else f"no AI crawlers blocked ({len(AI_CRAWLERS)} checked)",
                             f"remove the Disallow for {', '.join(blocked)} if the site wants AI citations" if blocked else ""))

    # --- llms.txt (optional)
    checks.append(_check("llms_txt", "access", 1,
                         "pass" if llms_txt.strip() else "info",
                         "llms.txt present" if llms_txt.strip() else "llms.txt not provided",
                         "" if llms_txt.strip() else "consider an llms.txt at the site root - the emerging AI-facing sitemap convention"))

    score_num = sum(c["weight"] for c in checks)
    got = sum(c["weight"] * {"pass": 1.0, "info": 0.75, "warn": 0.4, "fail": 0.0}[c["verdict"]] for c in checks)
    score = round(100 * got / score_num) if score_num else 0
    return {"score": score, "checks": checks,
            "fails": sum(1 for c in checks if c["verdict"] == "fail"),
            "warns": sum(1 for c in checks if c["verdict"] == "warn"),
            "note": "GEO = being cited inside AI answers. Fix fails first (citations, AI-crawler blocks), then answer-readiness warns; re-run to confirm the score moves"}


def geo_audit(inp: GeoAuditInput) -> dict:
    return audit_geo(inp.html, inp.robots_txt, inp.llms_txt)
