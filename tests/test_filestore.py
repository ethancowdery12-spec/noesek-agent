"""Hermetic file-store tests: write/read/list semantics + endpoints."""

import os

import pytest
from fastapi.testclient import TestClient

from noesek import filestore
from noesek.computer import server


@pytest.fixture()
def fdir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path / "files"))
    yield tmp_path / "files"


@pytest.fixture()
def client(fdir):
    return TestClient(server.app)


def test_write_read_roundtrip(fdir):
    meta = filestore.write_file("notes.md", "# hello\n")
    assert meta["bytes"] == 8 and len(meta["sha256"]) == 64
    assert filestore.read_file("notes.md") == b"# hello\n"


def test_list_metadata_only(fdir):
    filestore.write_file("a.txt", "alpha")
    filestore.write_file("b.csv", "x,y\n1,2\n")
    listed = filestore.list_files()
    assert [f["name"] for f in listed] == ["a.txt", "b.csv"]
    assert all("content" not in f for f in listed)


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "a/b", ".hidden", "x" * 129])
def test_bad_names_rejected(fdir, bad):
    with pytest.raises(filestore.FileStoreError):
        filestore.write_file(bad, "x")


def test_empty_and_oversize_rejected(fdir, monkeypatch):
    with pytest.raises(filestore.FileStoreError):
        filestore.write_file("ok.txt", "")
    monkeypatch.setattr(filestore, "MAX_FILE_BYTES", 10)
    with pytest.raises(filestore.FileStoreError):
        filestore.write_file("big.txt", "x" * 11)


def test_read_missing(fdir):
    with pytest.raises(filestore.FileStoreError):
        filestore.read_file("nope.txt")


def test_endpoints(client):
    filestore.write_file("report.md", "# Report\n")
    listing = client.get("/files")
    assert listing.status_code == 200
    assert listing.json()["files"][0]["name"] == "report.md"
    dl = client.get("/files/report.md")
    assert dl.status_code == 200 and dl.content == b"# Report\n"
    assert 'filename="report.md"' in dl.headers["content-disposition"]
    assert client.get("/files/missing.txt").status_code == 404
    assert client.get("/files/..%2Fetc%2Fpasswd").status_code in (404, 422)


def test_create_file_tool_in_registry(fdir):
    import asyncio
    from noesek.core.controller import Controller
    from noesek.core.types import Risk
    from noesek.tools.file_tools import CreateFileInput

    registry = Controller(llm=object()).registry(1)
    spec = registry.get("create_file")
    assert spec is not None and spec.risk is Risk.WRITE
    out = asyncio.run(spec.handler(CreateFileInput(name="todo.txt", content="- milk\n")))
    assert out["created"] is True and out["download"] == "/files/todo.txt"
    assert filestore.read_file("todo.txt") == b"- milk\n"
