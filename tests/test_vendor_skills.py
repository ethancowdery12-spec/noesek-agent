"""The vendored Hermes skill system backs Noesek's skill registry."""
from noesek.compat.skills_real import SkillStore


def _skill(home, name, body=None):
    d = home / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body or f"---\nname: {name}\ndescription: {name} skill\n---\n# {name}\nBody.\n")


def test_list_and_view(tmp_path):
    store = SkillStore(tmp_path)
    _skill(tmp_path, "demo")
    _skill(tmp_path, "research-helper")
    names = [s["name"] for s in store.list()]
    assert names == ["demo", "research-helper"]
    viewed = store.view("demo")
    assert "demo" in str(viewed)

def test_check_requirements(tmp_path):
    assert SkillStore(tmp_path).check() is True

def test_missing_skill_errors(tmp_path):
    import pytest
    store = SkillStore(tmp_path)
    with pytest.raises(RuntimeError):
        store.view("nonexistent-skill")
