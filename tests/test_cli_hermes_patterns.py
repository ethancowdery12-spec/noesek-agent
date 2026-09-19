import json, zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from noesek import cli, cli_ops


def test_completion_all_shells():
    for shell in ("bash", "zsh", "fish"):
        text=cli._completion(shell); assert "noesek" in text and "doctor" in text


def test_config_redacts_secrets(monkeypatch):
    monkeypatch.setattr(cli_ops, "config_snapshot", lambda:{"llm_api_key":"***configured***","llm_model":"x"})
    assert cli_ops.config_get("llm_api_key") == "***configured***"
    with pytest.raises(KeyError): cli_ops.config_get("nope")


def test_doctor_shape():
    r=cli_ops.doctor_report(); assert set(r)=={"ok","checks"}; assert "python" in r["checks"]


def test_prompt_size_shape():
    r=cli_ops.prompt_size_report(); assert r["total_bytes"] == r["system_prompt_bytes"] + r["tool_schemas_bytes"]


def test_backup_uses_local_zip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); Path("README.md").write_text("x")
    out=tmp_path/"b.zip"; names=cli_ops.backup(out)
    assert "README.md" in names
    with zipfile.ZipFile(out) as z: assert z.read("README.md") == b"x"


def test_one_shot_requires_query(capsys):
    assert cli.main(["chat","--oneshot"]) == 2
    assert "requires --query" in capsys.readouterr().err


def test_json_emit(capsys):
    cli._emit({"a":1}, True); assert json.loads(capsys.readouterr().out)=={"a":1}


def test_parser_chat_machine_formats():
    a=cli.build_parser().parse_args(["chat","--oneshot","-q","hi","--format","stream-json","--user","ci"])
    assert (a.oneshot,a.query,a.format,a.user)==(True,"hi","stream-json","ci")


def test_sessions_delete_needs_yes(capsys):
    assert cli.main(["sessions","delete","1"]) == 2
    assert "requires --yes" in capsys.readouterr().err


def test_version_is_030(capsys):
    with pytest.raises(SystemExit): cli.main(["--version"])
    from noesek import __version__
    assert __version__ in capsys.readouterr().out
