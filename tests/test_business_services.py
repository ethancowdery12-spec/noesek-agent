import asyncio

import httpx
import pytest

import noesek.tools.business_services as bs
from noesek.tools.business_services import BusinessServiceInput as I, business_services


def call(**kw):
    return asyncio.run(business_services(I(action="call", **kw)))


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    import os
    for k in list(os.environ):
        if k.startswith("NOESEK_") and any(s in k for s in ("FIRECRAWL", "TWENTY", "CHATWOOT", "ACTIVEPIECES", "SIGNING")):
            monkeypatch.delenv(k)


def test_list_covers_five_services_unconfigured():
    out = asyncio.run(business_services(I(action="list")))["services"]
    assert set(out) == {"firecrawl", "twenty", "chatwoot", "activepieces", "signing"}
    assert not any(v["configured"] for v in out.values())
    assert "not a confirmed match" in out["signing"]["note"] or "candidate" in out["signing"]["note"]


def test_not_configured_and_unknowns():
    assert "not configured" in call(service="twenty", op="people_list")["error"]
    assert "unknown op" in call(service="twenty", op="delete_all")["error"]
    assert "unknown service" in call(service="x", op="y")["error"]


def test_hosted_firecrawl_refused_without_cost_approval(monkeypatch):
    monkeypatch.setenv("NOESEK_FIRECRAWL_BASE_URL", "https://api.firecrawl.dev")
    monkeypatch.setenv("NOESEK_FIRECRAWL_TOKEN", "fc-secret")
    out = call(service="firecrawl", op="scrape", url="https://example.com")
    assert "spends credits" in out["error"] and "fc-secret" not in str(out)


def test_http_remote_base_refused(monkeypatch):
    monkeypatch.setenv("NOESEK_TWENTY_BASE_URL", "http://crm.example.com")
    monkeypatch.setenv("NOESEK_TWENTY_TOKEN", "t")
    assert "https" in call(service="twenty", op="people_list")["error"]


def test_requests_use_documented_paths_and_auth(monkeypatch):
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path, dict(req.headers)))
        return httpx.Response(200, json={"ok": True})
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(bs.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    for svc, env in (("twenty", "TWENTY"), ("chatwoot", "CHATWOOT"), ("signing", "SIGNING"),
                     ("activepieces", "ACTIVEPIECES"), ("firecrawl", "FIRECRAWL")):
        monkeypatch.setenv(f"NOESEK_{env}_BASE_URL", "http://localhost:3000")
        monkeypatch.setenv(f"NOESEK_{env}_TOKEN", "tok")
    monkeypatch.setenv("NOESEK_CHATWOOT_ACCOUNT_ID", "7")
    call(service="twenty", op="people_list")
    call(service="chatwoot", op="conversations_list")
    call(service="signing", op="templates_list")
    call(service="activepieces", op="flows_list")
    call(service="firecrawl", op="scrape", url="https://example.com")
    assert [(m, p) for m, p, _ in seen] == [("GET", "/rest/people"), ("GET", "/api/v1/accounts/7/conversations"),
                                            ("GET", "/api/v2/template"), ("GET", "/api/v1/flows"), ("POST", "/v2/scrape")]
    assert seen[0][2]["authorization"] == "Bearer tok"
    assert seen[1][2]["api_access_token"] == "tok"
    assert seen[2][2]["authorization"] == "tok"
