"""Item 63: seo_audit tool + seo_web playbook (claude-seo knowledge, MIT, own-words)."""
from noesek.tools.playbook import PLAYBOOKS
from noesek.tools.seo_audit import SeoAuditInput, audit_html, seo_audit

GOOD = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Handmade Oak Desks Built to Order in Austin</title>
<meta name="description" content="Custom oak desks designed, built, and delivered by a two-person Austin workshop. See the build process, wood sources, and pricing.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="https://oak.example.com/">
<meta property="og:title" content="Handmade Oak Desks"><meta property="og:description" content="Custom oak desks."><meta property="og:image" content="https://oak.example.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"Oak Shop","url":"https://oak.example.com/"}</script>
</head><body><h1>Handmade Oak Desks</h1><h2>The workshop</h2>
<img src="https://oak.example.com/desk.jpg" alt="Solid oak desk with drawer, workshop photo">
<p>""" + "word " * 520 + """</p></body></html>"""

BAD = """<html><head><title>Desks</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"HowTo","name":"old"}</script>
</head><body><h1>A</h1><h1>B</h1><h4>skip</h4>
<img src="http://x.example.com/pic.png">
<meta name="robots" content="noindex">
<p>thin</p></body></html>"""


def test_good_page_scores_high():
    out = audit_html(GOOD, "homepage")
    assert out["fails"] == 0 and out["score"] >= 90, out
    by_id = {c["id"]: c for c in out["checks"]}
    assert by_id["title"]["verdict"] == "pass" and by_id["jsonld"]["verdict"] == "pass"
    assert by_id["single_h1"]["verdict"] == "pass" and by_id["img_alt"]["verdict"] == "pass"


def test_bad_page_flags_everything():
    out = audit_html(BAD, "blog")
    by_id = {c["id"]: c for c in out["checks"]}
    assert by_id["title"]["verdict"] == "warn"                      # 5 chars
    assert by_id["meta_description"]["verdict"] == "fail"           # missing
    assert by_id["single_h1"]["verdict"] == "fail"                  # two h1
    assert by_id["heading_hierarchy"]["verdict"] == "warn"          # h1 -> h4 skip
    assert by_id["viewport"]["verdict"] == "fail"
    assert by_id["lang"]["verdict"] == "warn"
    assert by_id["jsonld"]["verdict"] == "fail"                     # HowTo deprecated
    assert "HowTo" in by_id["jsonld"]["evidence"]
    assert by_id["noindex"]["verdict"] == "warn"
    assert by_id["mixed_content"]["verdict"] == "warn"
    assert by_id["img_alt"]["verdict"] == "fail"                    # no alt
    assert by_id["content_depth"]["verdict"] == "warn"              # blog floor
    assert out["score"] < 50


def test_faqpage_is_info_not_fail():
    html = GOOD.replace('"@type":"LocalBusiness"', '"@type":"FAQPage"')
    by_id = {c["id"]: c for c in audit_html(html)["checks"]}
    assert by_id["jsonld"]["verdict"] == "info" and "QAPage" in by_id["jsonld"]["fix"]


def test_unparseable_jsonld_fails():
    html = GOOD.replace('{"@context":"https://schema.org","@type":"LocalBusiness","name":"Oak Shop","url":"https://oak.example.com/"}', '{not json')
    by_id = {c["id"]: c for c in audit_html(html)["checks"]}
    assert by_id["jsonld"]["verdict"] == "fail"


def test_tool_entrypoint():
    out = seo_audit(SeoAuditInput(html=GOOD, page_type="homepage"))
    assert out["score"] >= 90 and "checks" in out


def test_seo_web_playbook_markers():
    brief = PLAYBOOKS["seo_web"]["brief"].lower()
    for marker in ("one h1", "30-60", "70-160", "json-ld", "canonical", "og:title",
                   "twitter:card", "alt text", "faqpage", "qapage", "seo_audit",
                   "absolute urls", "e-e-a-t"):
        assert marker in brief, f"seo_web brief missing: {marker}"
