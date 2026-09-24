"""geo_audit (SEO/GEO lane): AI-answer citability checks."""
from noesek.tools.geo_audit import GeoAuditInput, geo_audit

_BASE_HEAD = '<html><head><title>t</title></head><body>'
_BASE_TAIL = '</body></html>'

def _run(html, robots="", llms=""):
    return geo_audit(GeoAuditInput(html=html, robots_txt=robots, llms_txt=llms))

def _by_id(r, cid):
    return next(c for c in r["checks"] if c["id"] == cid)

GOOD = (_BASE_HEAD +
    '<h1>What is noesek?</h1><p>Noesek is a self-hostable agent runtime that a team runs on its own hardware to keep chat data in-house.</p>'
    '<h2>How does noesek handle memory?</h2><ul><li>vector</li><li>graph</li></ul>'
    '<a href="https://example.org/a">a</a> <a href="https://research.example/b">b</a>'
    '<blockquote>It just works.</blockquote>'
    '<p>Adoption grew 240% in 2026 across 3 million chats and 12 countries.</p>'
    '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Noesek","sameAs":["https://www.wikidata.org/wiki/Q1"],"datePublished":"2026-01-01"}</script>'
    + _BASE_TAIL)

def test_good_page_scores_well():
    r = _run(GOOD, robots="User-agent: *\nAllow: /\n", llms="# noesek\n")
    assert r["fails"] == 0
    assert r["score"] >= 85
    assert _by_id(r, "citations")["verdict"] == "pass"
    assert _by_id(r, "entity_clarity")["verdict"] == "pass"
    assert _by_id(r, "wikidata_entity")["verdict"] == "pass"

def test_bare_page_flags_citations_and_answer_lead():
    r = _run(_BASE_HEAD + "<h1>Hi</h1><p>Welcome.</p>" + _BASE_TAIL)
    assert _by_id(r, "citations")["verdict"] == "fail"
    assert _by_id(r, "statistics")["verdict"] == "fail"
    assert _by_id(r, "answer_lead")["verdict"] == "warn"
    assert r["fails"] >= 2

def test_blocked_ai_crawler_fails():
    r = _run(GOOD, robots="User-agent: GPTBot\nDisallow: /\n")
    c = _by_id(r, "ai_crawler_access")
    assert c["verdict"] == "fail" and "GPTBot" in c["evidence"]

def test_allowed_ai_crawlers_pass():
    r = _run(GOOD, robots="User-agent: GPTBot\nAllow: /\nUser-agent: ClaudeBot\nAllow: /\n")
    assert _by_id(r, "ai_crawler_access")["verdict"] == "pass"

def test_missing_robots_is_info_not_fail():
    r = _run(GOOD)
    assert _by_id(r, "ai_crawler_access")["verdict"] == "info"

def test_entity_without_sameas_warns():
    html = _BASE_HEAD + '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"X"}</script>' + _BASE_TAIL
    r = _run(html)
    assert _by_id(r, "entity_clarity")["verdict"] == "warn"
    w = _by_id(r, "wikidata_entity")
    assert w["verdict"] == "warn" and "wikidata.org" in w["fix"]

def test_no_entity_wikidata_is_info():
    r = _run(_BASE_HEAD + "<h1>Hi</h1><p>Welcome.</p>" + _BASE_TAIL)
    assert _by_id(r, "wikidata_entity")["verdict"] == "info"

def test_social_links_do_not_count_as_citations():
    html = _BASE_HEAD + '<a href="https://www.facebook.com/x">fb</a><a href="https://x.com/y">x</a>' + _BASE_TAIL
    assert _by_id(_run(html), "citations")["verdict"] == "fail"
