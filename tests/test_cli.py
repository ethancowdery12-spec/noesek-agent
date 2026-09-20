import pytest
from noesek import cli

def test_version_flag(capsys):
    assert cli.main(["--version"]) == 0
    from noesek import __version__
    assert __version__ in capsys.readouterr().out

def test_no_command_boots_vendored_cli_with_noesek_branding(monkeypatch):
    # v3 full fork: bare `noesek` boots the complete vendored upstream CLI via
    # the branding shim. The Noesek interactive UI remains at `noesek chat`.
    called = {}
    def fake_boot():
        called["booted"] = True
        return 0
    monkeypatch.setattr("noesek.upstream_boot.main", fake_boot)
    assert cli.main([]) == 0
    assert called.get("booted") is True
