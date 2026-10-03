from noesek.tools.design_resources import RESOURCES, DesignResourcesInput as I, design_resources as f


def test_six_verified_sites_and_exclusions():
    assert set(RESOURCES) == {"shadcn", "motion", "bklit_ui", "kokonut_ui", "haikei", "spline"}
    out = f(I(action="list"))
    assert set(out["excluded"]) == {"manus", "manifold"}
    assert "excluded" in f(I(action="get", resource="manus"))


def test_every_entry_has_source_and_honest_license():
    for r in RESOURCES.values():
        assert r["source"].startswith("https://") and r["license"]
    assert "proprietary" in RESOURCES["bklit_ui"]["license"]
    assert RESOURCES["haikei"]["install"] is None and RESOURCES["spline"]["install"] is None


def test_recommend():
    ids = [x["id"] for x in f(I(action="recommend", need="a dashboard with a chart and animation"))["recommended"]]
    assert ids[:1] == ["bklit_ui"] and "motion" in ids
    assert f(I(action="recommend", need="zzz"))["recommended"] == []
