"""Roadmap items 34-36: UI library knowledge adoption (Ethan's call Sep 21)."""
from noesek.core.context import SYSTEM


def test_system_prompt_points_at_ui_reference():
    assert "docs/UI_LIBRARY_REFERENCE.md" in SYSTEM


def test_system_prompt_teaches_the_libraries():
    assert "anime" in SYSTEM and "stagger" in SYSTEM
    assert "Motion" in SYSTEM and "spring" in SYSTEM
    assert "kokonutui" in SYSTEM
    assert "MIT" in SYSTEM


def test_reference_doc_covers_all_three_with_licenses():
    doc = open("docs/UI_LIBRARY_REFERENCE.md").read()
    for marker in ("juliangarnier/anime", "motiondivision/motion", "kokonut-labs/kokonutui"):
        assert marker in doc, marker
    assert doc.count("MIT") >= 3
    for pattern in ("createTimeline", "stagger", "spring", "inView", "motion.div"):
        assert pattern in doc, pattern


def test_roadmap_ui_items_closed():
    doc = open("docs/RESEARCH_ROADMAP.md").read()
    for marker in ("**34. anime.js**", "**35. motion.dev / Framer Motion**", "**36. \"coconut UI\" = kokonutui**"):
        line = next(l for l in doc.splitlines() if marker in l)
        assert line.startswith("- [x]"), marker
