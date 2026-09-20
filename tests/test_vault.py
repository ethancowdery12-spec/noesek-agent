"""Hermetic vault tests: store semantics + HTTP endpoints, no env leaks."""

import os
import stat

import pytest
from fastapi.testclient import TestClient

from noesek import vault
from noesek.computer import server


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_VAULT_PATH", str(tmp_path / "vault.json"))
    yield vault.default_store()


@pytest.fixture()
def client(store):
    return TestClient(server.app)


def test_put_get_roundtrip(store):
    store.put("github-token", "s3cr3t")
    entry = store.get("github-token")
    assert entry["value"] == "s3cr3t"
    assert entry["stored_at"] > 0


def test_file_is_0600(store):
    store.put("a", "b")
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600


def test_names_never_returns_values(store):
    store.put("k1", "value-one")
    store.put("k2", "value-two")
    listed = store.names()
    assert [n["name"] for n in listed] == ["k1", "k2"]
    assert all("value" not in n for n in listed)
    assert "value-one" not in repr(listed)


def test_delete(store):
    store.put("x", "y")
    assert store.delete("x") is True
    assert store.get("x") is None
    assert store.delete("x") is False


@pytest.mark.parametrize("bad", ["", "../etc", "a/b", "a b", "x" * 65, "-lead"])
def test_bad_names_rejected(store, bad):
    with pytest.raises(vault.VaultError):
        store.put(bad, "v")


def test_empty_value_rejected(store):
    with pytest.raises(vault.VaultError):
        store.put("ok-name", "")


def test_http_roundtrip_and_no_value_in_list(client):
    assert client.post("/vault", json={"name": "api", "value": "topsecret"}).status_code == 200
    listing = client.get("/vault")
    assert listing.status_code == 200
    assert "topsecret" not in listing.text
    assert listing.json()["secrets"][0]["name"] == "api"
    got = client.get("/vault/api")
    assert got.status_code == 200
    assert got.json()["value"] == "topsecret"


def test_http_missing_and_invalid(client):
    assert client.get("/vault/nope").status_code == 404
    assert client.delete("/vault/nope").status_code == 404
    assert client.post("/vault", json={"name": "a/b", "value": "v"}).status_code == 400
    assert client.delete("/vault/gone-ok").status_code == 404


def test_http_delete(client):
    client.post("/vault", json={"name": "temp", "value": "v"})
    assert client.delete("/vault/temp").status_code == 200
    assert client.get("/vault/temp").status_code == 404
