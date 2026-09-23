"""On-page SEO audit for HTML deliverables (roadmap item 63).

Ethan Sep 23: "build in agriciDaniel/claude-seo so our agent makes good,
rankable websites." Repo VERIFIED real (github.com/AgriciDaniel/claude-seo,
17.5k stars); LICENSE VERIFIED MIT on-disk (Copyright 2026 AgriciDaniel) -
knowledge studied and REIMPLEMENTED own-words per the reuse posture; full
license text at docs/licenses/CLAUDE-SEO-MIT.txt.

Own implementation: a deterministic, stdlib-only (html.parser) audit of one
HTML page across on-page, technical, schema, social, content, and image
checks. Weights adapted from the claude-seo audit skill's scoring model.
Deprecated-schema facts current as of the skill's June 2026 status list
(HowTo, SpecialAnnouncement, CourseInfo, EstimatedSalary, LearningVideo,
ClaimReview, VehicleListing retired; FAQPage rich results retired May 2026 -
kept as Info since QAPage is the live Q&A type). No new dependencies.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

from pydantic import BaseModel, Field


class SeoAuditInput(BaseModel):
    html: str = Field(min_length=20, max_length=400000, description="The page's full HTML source")
    page_type: str = Field(default="other",
                           description="homepage | service | blog | product | location | other - used for content-depth floors")


DEPRECATED_TYPES = {"HowTo", "SpecialAnnouncement", "CourseInfo", "EstimatedSalary",
                    "LearningVideo", "ClaimReview", "VehicleListing"}
NO_RICH_TYPES = {"FAQPage"}  # rich results retired May 2026; QAPage is the live Q&A type
WORD_FLOORS = {"homepage": 500, "service": 800, "blog": 1500, "product": 300, "location": 500}


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


def _check(cid: str, bucket: str, weight: float, verdict: str, evidence: str, fix: str) -> dict:
    return {"id": cid, "bucket": bucket, "weight": weight, "verdict": verdict,
            "evidence": evidence[:200], "fix": fix[:300]}


def audit_html(html: str, page_type: str = "other") -> dict:
    p = _Page(); p.feed(html)
    def first(tag, **attrs):
        for t, a in p.tags:
            if t == tag and all(a.get(k, "").lower() == v.lower() for k, v in attrs.items()):
                return a
        return None
    def all_tags(tag):
        return [a for t, a in p.tags if t == tag]

    checks = []
    # on-page
    title = (first("title") or {})
    title_text = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m: title_text = re.sub(r"\s+", " ", m.group(1)).strip()
    if not title_text:
        checks.append(_check("title", "on_page", 3, "fail", "no <title> found",
                             "add a unique title with the primary term, 30-60 characters"))
    elif not 30 <= len(title_text) <= 60:
        checks.append(_check("title", "on_page", 3, "warn", f"title is {len(title_text)} chars: {title_text[:60]}",
                             "keep titles 30-60 characters so they survive SERP truncation"))
    else:
        checks.append(_check("title", "on_page", 3, "pass", f"{len(title_text)} chars", ""))
    desc = first("meta", name="description")
    dtxt = (desc or {}).get("content", "").strip()
    if not dtxt:
        checks.append(_check("meta_description", "on_page", 3, "fail", "no meta description",
                             "add a 70-160 character description that earns the click"))
    elif not 70 <= len(dtxt) <= 160:
        checks.append(_check("meta_description", "on_page", 3, "warn", f"description is {len(dtxt)} chars",
                             "keep descriptions 70-160 characters"))
    else:
        checks.append(_check("meta_description", "on_page", 3, "pass", f"{len(dtxt)} chars", ""))
    h1s = re.findall(r"<h1[\s>]", html, re.I)
    checks.append(_check("single_h1", "on_page", 2, "pass" if len(h1s) == 1 else "fail",
                         f"{len(h1s)} h1 elements",
                         "" if len(h1s) == 1 else "exactly one h1 per page; demote the rest"))
    levels = [int(m) for m in re.findall(r"<h([1-6])[\s>]", html, re.I)]
    skips = any(b - a > 1 for a, b in zip(levels, levels[1:]))
    checks.append(_check("heading_hierarchy", "on_page", 1, "warn" if skips else "pass",
                         "heading levels skip" if skips else "no skipped levels",
                         "keep a logical h1 -> h2 -> h3 outline" if skips else ""))
    # technical
    html_tag = first("html")
    checks.append(_check("lang", "technical", 1, "pass" if (html_tag or {}).get("lang") else "warn",
                         f"lang={((html_tag or {}).get('lang'))!r}", "declare <html lang=...>"))
    checks.append(_check("viewport", "technical", 1,
                         "pass" if first("meta", name="viewport") else "fail",
                         "viewport meta present" if first("meta", name="viewport") else "no viewport meta",
                         "add <meta name=viewport content=\"width=device-width, initial-scale=1\">"))
    has_charset = bool(re.search(r"<meta[^>]+charset", html, re.I))
    checks.append(_check("charset", "technical", 1,
                         "pass" if has_charset else "fail",
                         "charset declared" if has_charset else "no charset declared",
                         "declare <meta charset=\"utf-8\">"))
    canon = first("link", rel="canonical")
    if canon and canon.get("href", "").startswith(("http://", "https://")):
        checks.append(_check("canonical", "technical", 1, "pass", canon["href"][:80], ""))
    elif canon:
        checks.append(_check("canonical", "technical", 1, "warn", "relative canonical",
                             "use an absolute canonical URL"))
    else:
        checks.append(_check("canonical", "technical", 1, "warn", "no canonical link",
                             "add <link rel=canonical> with the absolute URL"))
    robots = first("meta", name="robots")
    if robots and "noindex" in robots.get("content", ""):
        checks.append(_check("noindex", "technical", 2, "warn", "robots meta says noindex",
                             "remove noindex if this page should rank"))
    else:
        checks.append(_check("noindex", "technical", 2, "pass", "indexable", ""))
    mixed = [a.get("src", "") for a in all_tags("img") + all_tags("script") if a.get("src", "").startswith("http://")]
    checks.append(_check("mixed_content", "technical", 1, "warn" if mixed else "pass",
                         f"{len(mixed)} http:// resources" if mixed else "no http:// resources",
                         "load all resources over https" if mixed else ""))
    # social
    og_ok = all(first("meta", property=f"og:{k}") for k in ("title", "description", "image"))
    checks.append(_check("open_graph", "social", 1, "pass" if og_ok else "warn",
                         "og:title/description/image present" if og_ok else "missing og tags",
                         "add og:title, og:description, og:image" if not og_ok else ""))
    checks.append(_check("twitter_card", "social", 1,
                         "pass" if first("meta", name="twitter:card") else "warn",
                         "twitter:card present" if first("meta", name="twitter:card") else "no twitter:card",
                         "add <meta name=twitter:card content=summary_large_image>"))
    # schema
    blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I)
    if not blocks:
        checks.append(_check("jsonld", "schema", 2, "warn", "no JSON-LD structured data",
                             "add JSON-LD in the initial HTML (not JS-injected) with a fitting active type"))
    else:
        bad, deprecated, norich, types = 0, [], [], []
        for b in blocks:
            try:
                data = json.loads(b)
                items = data if isinstance(data, list) else [data]
                for it in items:
                    t = it.get("@type") if isinstance(it, dict) else None
                    if not t or not it.get("@context"):
                        bad += 1; continue
                    t = t[0] if isinstance(t, list) else t
                    types.append(str(t))
                    if t in DEPRECATED_TYPES: deprecated.append(t)
                    if t in NO_RICH_TYPES: norich.append(t)
            except Exception:
                bad += 1
        if bad:
            checks.append(_check("jsonld", "schema", 2, "fail", f"{bad} unparseable/invalid JSON-LD blocks",
                                 "fix JSON-LD: valid JSON, @context + @type required"))
        elif deprecated:
            checks.append(_check("jsonld", "schema", 2, "fail", f"deprecated types: {', '.join(sorted(set(deprecated)))}",
                                 "remove deprecated schema types (no rich-result benefit)"))
        elif norich:
            checks.append(_check("jsonld", "schema", 2, "info", f"no-rich-result types: {', '.join(sorted(set(norich)))}",
                                 "FAQPage lost rich results May 2026; use QAPage for genuine Q&A"))
        else:
            checks.append(_check("jsonld", "schema", 2, "pass", f"types: {', '.join(sorted(set(types)))[:80]}", ""))
    # content
    words = len(re.findall(r"[a-zA-Z0-9']+", " ".join(p.text_parts)))
    floor = WORD_FLOORS.get(page_type)
    if floor and words < floor:
        checks.append(_check("content_depth", "content", 2, "warn", f"{words} words, {page_type} floor ~{floor}",
                             "thin topical coverage; expand to cover the topic (floors are guidelines, not targets)"))
    else:
        checks.append(_check("content_depth", "content", 2, "pass", f"{words} words", ""))
    # images
    imgs = all_tags("img")
    if imgs:
        with_alt = sum(1 for a in imgs if a.get("alt", "").strip())
        cov = with_alt / len(imgs)
        checks.append(_check("img_alt", "images", 1,
                             "pass" if cov >= 0.9 else ("warn" if cov >= 0.5 else "fail"),
                             f"{with_alt}/{len(imgs)} images have alt text",
                             "every informative image needs descriptive alt text" if cov < 0.9 else ""))
    score_num = sum(c["weight"] for c in checks)
    got = sum(c["weight"] * {"pass": 1.0, "info": 0.75, "warn": 0.4, "fail": 0.0}[c["verdict"]] for c in checks)
    score = round(100 * got / score_num) if score_num else 0
    return {"score": score, "checks": checks,
            "fails": sum(1 for c in checks if c["verdict"] == "fail"),
            "warns": sum(1 for c in checks if c["verdict"] == "warn"),
            "note": "fix fails first, then warns; re-run to confirm the score moves"}


def seo_audit(inp: SeoAuditInput) -> dict:
    return audit_html(inp.html, inp.page_type.strip().lower() or "other")
