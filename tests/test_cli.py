import pytest
from noesek import cli

def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    from noesek import __version__
    assert __version__ in capsys.readouterr().out

def test_no_command_prints_help(capsys):
    cli.main([])
    assert "usage: noesek" in capsys.readouterr().out
