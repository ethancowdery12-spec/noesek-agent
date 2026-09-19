import pytest
from noesek import cli

def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    from noesek import __version__
    assert __version__ in capsys.readouterr().out

def test_no_command_opens_interactive_ui(monkeypatch):
    called = {}
    async def fake_interactive(user_id):
        called["user_id"] = user_id
    monkeypatch.setattr("noesek.hermes_ui.run_interactive", fake_interactive)
    assert cli.main([]) == 0
    assert called.get("user_id") == "cli-user"
