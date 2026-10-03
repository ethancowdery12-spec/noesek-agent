from noesek.tools.style_match import StyleMatchInput as I, delta_e, style_match as f

REF = "<style>body{background:#0a0a0a;color:#f5f5f5;font-family:Inter,sans-serif}.c{border-radius:12px;color:#ff5a1f}</style>"


def test_delta_e_basics():
    assert delta_e("#000000", "#000") == 0
    assert delta_e("#ffffff", "#000000") > 90
    assert delta_e("#0a0a0a", "#0b0b0b") < 2


def test_match_from_reference_html():
    built = "<style>body{background:#0b0b0b;color:#f4f4f4;font-family:'Inter',sans-serif}.k{border-radius:12px;color:#ff5b20}</style>"
    r = f(I(built_html=built, reference_html=REF))
    assert r["matches_reference"] is True and r["palette_coverage"] == 1.0 and not r["off_palette_colors"]


def test_drift_is_reported():
    built = "<style>body{background:#ffffff;color:#222222;font-family:Arial}.k{border-radius:4px;color:#00ff00}</style>"
    r = f(I(built_html=built, reference_html=REF))
    assert r["matches_reference"] is False and r["palette_coverage"] < 1
    assert "#00ff00" in r["off_palette_colors"]
    assert r["fonts"]["missing"] == ["inter"] and r["radii"]["missing"] == [12] and r["radii"]["extra"] == [4]


def test_explicit_palette_and_tolerance():
    built = "<div style=\"color:#102030\">x</div>"
    assert f(I(built_html=built, palette=["#112233"]))["palette_coverage"] == 1.0
    assert f(I(built_html=built, palette=["#112233"], tolerance=0.5))["palette_coverage"] == 0.0


def test_no_reference_and_bad_entries():
    r = f(I(built_html="<p>x</p>", palette=["blue"]))
    assert r["ok"] is False and r["bad_palette_entries"] == ["blue"]
