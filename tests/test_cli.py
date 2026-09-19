import pytest
from noesek import cli

def test_version_flag(capsys):
    assert cli.main(["--version"]) == 0
    from noesek import __version__
    assert __version__ in capsys.readouterr().out

def test_no_command_opens_interactive_ui(monkeypatch):
    called = {}
    async def fake_interactive(user_id, **kwargs):
        called["user_id"] = user_id
    monkeypatch.setattr("noesek.ui.run_interactive", fake_interactive)
    assert cli.main([]) == 0
    assert called.get("user_id") == "cli-user"
