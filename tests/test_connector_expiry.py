"""Connector token expiry normalization: absolute expires_at (Strava) vs
relative expires_in (Google) both become an absolute epoch on the stored grant."""
import time

import pytest

from noesek import connectors


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        return self._p


def _fake_client(payload):
    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, data=None, headers=None):
            return _FakeResp(payload)

    return FakeClient


@pytest.mark.asyncio
async def test_exchange_code_normalizes_relative_expires_in(monkeypatch):
    import httpx
    monkeypatch.setenv("NOESEK_CONNECTOR_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("NOESEK_CONNECTOR_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(httpx, "AsyncClient",
                        _fake_client({"access_token": "tok", "refresh_token": "rt",
                                      "expires_in": 3600}))
    c = connectors.get("google")
    before = int(time.time())
    out = await connectors.exchange_code(c, "code-1", "http://x/cb")
    assert out["access_token"] == "tok" and out["refresh_token"] == "rt"
    assert before + 3600 <= out["expires_at"] <= int(time.time()) + 3600


@pytest.mark.asyncio
async def test_exchange_code_keeps_absolute_expires_at(monkeypatch):
    import httpx
    monkeypatch.setenv("NOESEK_CONNECTOR_STRAVA_CLIENT_ID", "cid")
    monkeypatch.setenv("NOESEK_CONNECTOR_STRAVA_CLIENT_SECRET", "secret")
    monkeypatch.setattr(httpx, "AsyncClient",
                        _fake_client({"access_token": "tok", "refresh_token": "rt",
                                      "expires_at": 1_900_000_000}))
    c = connectors.get("strava")
    out = await connectors.exchange_code(c, "code-1", "http://x/cb")
    assert out["expires_at"] == 1_900_000_000


@pytest.mark.asyncio
async def test_refresh_grant_normalizes_and_keeps_old_refresh_token(monkeypatch, tmp_path):
    import httpx
    monkeypatch.setenv("NOESEK_CONNECTOR_STRAVA_CLIENT_ID", "cid")
    monkeypatch.setenv("NOESEK_CONNECTOR_STRAVA_CLIENT_SECRET", "secret")
    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    await store.put("strava", "ethan-main", "tok-old", ("activity:read_all",),
                    refresh_token="rt-keep", expires_at=1)
    # Provider rotates the access token but sends no new refresh token.
    monkeypatch.setattr(httpx, "AsyncClient",
                        _fake_client({"access_token": "tok-new", "expires_in": 21600}))
    before = int(time.time())
    fresh = await connectors.refresh_grant("strava", "ethan-main")
    assert fresh == "tok-new"
    grant = await store.get("strava", "ethan-main")
    assert grant["access_token"] == "tok-new"
    assert grant["refresh_token"] == "rt-keep"
    assert before + 21600 <= grant["expires_at"] <= int(time.time()) + 21600
