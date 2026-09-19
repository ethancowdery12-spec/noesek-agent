import json, zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from noesek import cli, cli_ops


def test_completion_all_shells():
    from noesek import cli_surface
    for shell in ("bash", "zsh", "fish"):
        text=cli_surface._completion(shell); assert "noesek" in text and "doctor" in text


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
    from noesek import cli_surface
    a=cli_surface.build_parser().parse_args(["chat","-q","hi","-m","claude-sonnet-4-20250514"])
    assert (a.query,a.model)==("hi","claude-sonnet-4-20250514")
    a=cli_surface.build_parser().parse_args(["--oneshot","hi","--output-format","stream-json"])
    assert (a.oneshot,a.output_format)==("hi","stream-json")


def test_sessions_delete_needs_yes(capsys):
    assert cli.main(["sessions","delete","1"]) == 2
    assert "requires --yes" in capsys.readouterr().err


def test_version_is_030(capsys):
    assert cli.main(["--version"]) == 0
    from noesek import __version__
    assert __version__ in capsys.readouterr().out
