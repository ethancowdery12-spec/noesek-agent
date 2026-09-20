"""Noesek boot shim for the vendored upstream CLI: env mapping, skin install,
prog rebrand - with the vendored tree left byte-identical."""
import importlib
import os
import sys

import pytest


@pytest.fixture
def boot(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    from noesek import upstream_boot
    return upstream_boot


def test_boot_env_maps_noesek_home_and_installs_skin(boot):
    home = boot.boot_env()
    assert os.environ["HERMES_HOME"] == str(home)
    skin = home / "skins" / "noesek.yaml"
    assert skin.exists()
    text = skin.read_text()
    assert "Noesek Agent" in text and "banner_logo" in text


def test_boot_env_refreshes_only_its_own_skin(boot, tmp_path):
    home = boot.boot_env()
    custom = home / "skins" / "mine.yaml"
    custom.write_text("name: mine\n")
    boot.boot_env()
    assert custom.read_text() == "name: mine\n"


def test_patch_prog_rebrands_top_level_parser(boot):
    boot.boot_env()
    boot._patch_prog()
    import hermes_cli._parser as hp
    parser, _, chat_parser = hp.build_top_level_parser()
    assert parser.prog == "noesek"
    assert "Noesek Agent" in parser.description
    assert chat_parser.prog == "noesek chat"


def test_vendored_tree_has_no_noesek_edits():
    # The rebrand lives entirely in our layer: no vendored file may mention noesek.
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "vendor/hermes-agent"
    offenders = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            if "noesek" in p.read_text(errors="ignore").lower():
                offenders.append(str(p))
        except OSError:
            pass
    assert not offenders, offenders[:5]


def test_vendored_state_lives_under_noesek_home(boot, tmp_path, monkeypatch):
    # S5: the vendored runtime's home resolution follows NOESEK_HOME end to end.
    home = boot.boot_env()
    import hermes_constants
    assert hermes_constants.get_hermes_home() == home
    from hermes_cli.skin_engine import _skins_dir
    assert _skins_dir() == home / "skins"
