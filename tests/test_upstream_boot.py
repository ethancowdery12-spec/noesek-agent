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
    import hermes_constants
    # Other tests may leave a context-local home override behind; clear it so
    # we assert the env mapping, not leftover state.
    monkeypatch.setattr(hermes_constants, "_HERMES_HOME_OVERRIDE", __import__("contextvars").ContextVar("_HERMES_HOME_OVERRIDE", default=hermes_constants._UNSET))
    home = boot.boot_env()
    assert hermes_constants.get_hermes_home() == home
    from hermes_cli.skin_engine import _skins_dir
    assert _skins_dir() == home / "skins"


def test_persist_default_skin_written_and_user_choice_respected(boot):
    home = boot.boot_env()
    import yaml
    data = yaml.safe_load((home / "config.yaml").read_text())
    assert data["display"]["skin"] == "noesek"
    # A user-chosen skin is never overwritten.
    (home / "config.yaml").write_text("display:\n  skin: ares\n")
    boot.boot_env()
    assert yaml.safe_load((home / "config.yaml").read_text())["display"]["skin"] == "ares"


def test_banner_label_patch_reads_noesek_version(boot):
    boot.boot_env()
    boot._patch_banner_label()
    from hermes_cli import banner
    from noesek import __version__
    assert banner.format_banner_version_label() == f"Noesek Agent v{__version__}"


def test_branding_stream_rewrites_commands_only(boot):
    import io
    buf = io.StringIO()
    stream = boot._BrandingStream(buf)
    stream.write("Run `hermes model` or 'hermes setup'. Hermes Agent v0.21.3. "
                 "See NousResearch/hermes-agent, hermes_cli.main, HERMES_HOME, ~/.hermes.")
    out = buf.getvalue()
    assert "`noesek model`" in out and "'noesek setup'" in out
    assert "Noesek Agent v0.21.3" in out
    assert "NousResearch/hermes-agent" in out
    assert "hermes_cli.main" in out and "HERMES_HOME" in out
    assert "~/.hermes" not in out and "~/.noesek" in out


def test_acp_auth_methods_rebranded(boot):
    boot.boot_env()
    boot._patch_acp_identity()
    from acp_adapter.auth import build_auth_methods
    methods = build_auth_methods()
    assert methods, "expected at least the terminal setup auth method"
    for m in methods:
        for field in ("id", "name", "description"):
            value = getattr(m, field, "")
            assert "hermes" not in str(value).lower(), (field, value)
