from noesek.tools.taste_check import TasteInput, contrast_ratio, taste_check

GOOD = """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<style>body{color:#111111;background:#ffffff;font-family:Inter,sans-serif;font-size:16px;padding:16px}
.c{margin:8px;gap:12px}</style></head><body><img src="a.png" alt="logo"><button aria-label="Menu"><svg></svg></button></body></html>"""


def rules(out):
    return {f["rule"] for f in out["findings"]}


def test_contrast_math():
    assert contrast_ratio("#000000", "#ffffff") == 21.0
    assert contrast_ratio("#777777", "#888888") < 2


def test_clean_page_passes():
    out = taste_check(TasteInput(html=GOOD, profile="restrained"))
    assert out["passed"] and out["findings"] == []


def test_objective_failures():
    bad = ("<html><head><style>body{color:#888888;background:#999999;font-size:9px}"
           ".a{transition:width 1s;height:100vh}</style></head>"
           "<body><img src=x.png><button><svg></svg></button></body></html>")
    r = rules(taste_check(TasteInput(html=bad)))
    assert {"viewport-meta", "html-lang", "img-alt", "icon-button-name", "fixed-100vh",
            "animate-layout", "reduced-motion", "contrast", "tiny-text"} <= r


def test_profile_is_an_explicit_choice():
    g = GOOD.replace("</style>", ".h{background:linear-gradient(red,blue)}</style>")
    assert "profile-gradient" in rules(taste_check(TasteInput(html=g, profile="restrained")))
    assert "profile-gradient" not in rules(taste_check(TasteInput(html=g, profile="expressive")))


def test_unknown_profile():
    assert "error" in taste_check(TasteInput(html="<p>x</p>", profile="nope"))
