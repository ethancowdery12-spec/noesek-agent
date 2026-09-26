"""Tests for the design_system tool (roadmap item 54)."""
import pytest

from noesek.tools.design_system import (CHECKLISTS, THEMES, DesignInput,
                                        design_system)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    from noesek import filestore
    monkeypatch.setattr(filestore, "files_dir", lambda: tmp_path)
    return tmp_path


def test_list_and_get():
    out = design_system(DesignInput(action="list"))
    assert set(out["themes"]) == {"ink", "paper", "signal"}
    got = design_system(DesignInput(action="get", theme="paper"))
    assert got["tokens"]["colors"]["accent"] == "#9a4b1f"
    assert set(got["tokens"]) >= {"colors", "font", "scale", "spacing", "radius"}


def test_render_writes_downloadable_html(store):
    out = design_system(DesignInput(
        action="render", theme="ink", title="Q4 Report", subtitle="Revenue",
        sections=["Growth | Revenue grew 25%", "Costs | Flat"], file_name="q4.html"))
    assert out["rendered"] and out["download"] == "/files/q4.html"
    page = (store / "q4.html").read_text()
    assert "#101014" in page and "Q4 Report" in page
    assert "<h2>Growth</h2>" in page and "Revenue grew 25%" in page
    assert 'class="subtitle"' in page


def test_render_escapes_and_validates(store):
    out = design_system(DesignInput(action="render", title="<script>x</script>", sections=["<b> | <i>bad</i>"]))
    page = (store / "page.html").read_text()
    assert "<script>" not in page and "<i>bad</i>" not in page and "&lt;i&gt;bad" in page
    assert "error" in design_system(DesignInput(action="render", file_name="x.txt"))
    assert "error" in design_system(DesignInput(action="render", theme="nope"))
    assert "error" in design_system(DesignInput(action="bogus"))


def test_tokens_are_schema_complete():
    for name, t in THEMES.items():
        assert set(t["colors"]) == {"bg", "surface", "ink", "muted", "accent"}, name
        assert set(t["scale"]) == {"h1", "h2", "body"}, name

def test_checklist_action_lists_and_loads():
    # roadmap item 96 (ibelick/ui-skills, MIT; own-words condensations).
    out = design_system(DesignInput(action="checklist"))
    assert set(out["checklists"]) == {"baseline_ui", "accessibility"}
    cl = design_system(DesignInput(action="checklist", checklist="baseline_ui"))
    assert cl["checklist"] == "baseline_ui" and len(cl["rules"]) > 400
    assert "error" in design_system(DesignInput(action="checklist", checklist="nope"))


def test_checklists_carry_the_load_bearing_rules():
    b = CHECKLISTS["baseline_ui"]["rules"].lower()
    assert "200ms" in b and "prefers-reduced-motion" in b
    assert "aria-label" in b and "skeleton" in b and "gradient" in b
    a = CHECKLISTS["accessibility"]["rules"].lower()
    assert "keyboard" in a and "focus" in a and "aria-hidden" in a
    assert "contrast" in a and "live regions" in a
    # own-words guard: zero phrasing lifted from the upstream skill files
    for name, cl in CHECKLISTS.items():
        assert "how to use" not in cl["rules"].lower(), name
