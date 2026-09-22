"""Tests for the OfficeCLI wrapper tool (roadmap item 51)."""
import os
import stat

import pytest

from noesek.tools.office_doc import OfficeDocInput, office_doc


@pytest.fixture()
def fake_cli(tmp_path, monkeypatch):
    log = tmp_path / "argv.log"
    binpath = tmp_path / "officecli"
    binpath.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\necho "ok-out"\n')
    binpath.chmod(binpath.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NOESEK_OFFICE_CLI", str(binpath))
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    return log


def run(action, **kw):
    return office_doc(OfficeDocInput(action=action, **kw))


def test_create_argv_and_download(fake_cli):
    out = run("create", file="deck.pptx")
    assert out["ok"] and out["output"].strip() == "ok-out"
    assert out["download"] == "/files/deck.pptx"
    line = fake_cli.read_text().strip()
    assert line.startswith("create ") and line.endswith("/deck.pptx")


def test_add_props(fake_cli):
    out = run("add", file="deck.pptx", path="/", props=["type=slide", "title=Q4 Report"])
    assert out["ok"]
    line = fake_cli.read_text().strip()
    assert "add " in line and " / " in line
    assert '--prop type=slide --prop title=Q4 Report' in line


def test_view_defaults_outline_and_get_json(fake_cli):
    run("view", file="notes.docx")
    run("get", file="deck.pptx", path="/slide[1]", as_json=True)
    lines = fake_cli.read_text().splitlines()
    assert lines[0].endswith("/notes.docx outline")
    assert lines[1].endswith("/deck.pptx /slide[1] --json")


def test_read_actions_have_no_download(fake_cli):
    out = run("view", file="deck.pptx")
    assert "download" not in out


def test_validation():
    assert "error" in run("bogus", file="a.pptx")
    assert "error" in run("view", file="a.pdf")
    assert "error" in run("view", file="../a.pptx")
    assert "error" in run("get", file="a.pptx")
    assert "error" in run("add", file="a.pptx", path="/", props=["noequals"])


def test_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_OFFICE_CLI", "nonexistent-officecli-xyz")
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    out = run("view", file="a.pptx")
    assert out["error"] == "officecli binary not found"
    assert "install" in out


def test_failing_binary(tmp_path, monkeypatch):
    binpath = tmp_path / "officecli"
    binpath.write_text('#!/bin/sh\necho bad-news >&2\nexit 3\n')
    binpath.chmod(binpath.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NOESEK_OFFICE_CLI", str(binpath))
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    out = run("remove", file="a.xlsx", path="/row[2]")
    assert out["error"] == "officecli exited 3"
    assert "bad-news" in out["stderr"]
