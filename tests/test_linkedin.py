"""Tests for the LinkedIn capability layer (roadmap item 52)."""
import httpx
import pytest

_REAL_CLIENT = httpx.AsyncClient

from noesek.tools.linkedin import LinkedInInput, linkedin


@pytest.fixture()
def token(monkeypatch):
    from noesek.config import settings
    monkeypatch.setattr(settings, "linkedin_access_token", "test-token-123")
    return "test-token-123"


def mock_transport(routes):
    def handler(request):
        return routes[(request.method, request.url.path)](request)
    return httpx.MockTransport(handler)


async def test_not_configured(monkeypatch):
    from noesek.config import settings
    monkeypatch.setattr(settings, "linkedin_access_token", "")
    out = await linkedin(LinkedInInput(action="profile"))
    assert out["error"] == "LinkedIn is not configured"
    assert "NOESEK_LINKEDIN_ACCESS_TOKEN" in out["setup"]


async def test_profile(token, monkeypatch):
    seen = {}
    def userinfo(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"sub": "abc123", "name": "Ethan Cowdery",
                                         "given_name": "Ethan", "family_name": "Cowdery"})
    transport = mock_transport({("GET", "/v2/userinfo"): userinfo})
    monkeypatch.setattr("noesek.tools.linkedin.httpx.AsyncClient",
                        lambda **kw: _REAL_CLIENT(transport=transport, **kw))
    out = await linkedin(LinkedInInput(action="profile"))
    assert out["ok"] and out["person_urn"] == "urn:li:person:abc123"
    assert seen["auth"] == "Bearer test-token-123"
    assert "test-token-123" not in str(out)


async def test_share_payload(token, monkeypatch):
    posted = {}
    def userinfo(request):
        return httpx.Response(200, json={"sub": "abc123", "name": "E"})
    def ugc(request):
        import json
        posted["body"] = json.loads(request.content)
        return httpx.Response(201, json={}, headers={"x-restli-id": "urn:li:share:700"})
    transport = mock_transport({("GET", "/v2/userinfo"): userinfo, ("POST", "/v2/ugcPosts"): ugc})
    monkeypatch.setattr("noesek.tools.linkedin.httpx.AsyncClient",
                        lambda **kw: _REAL_CLIENT(transport=transport, **kw))
    out = await linkedin(LinkedInInput(action="share", text="Shipped 5 PRs today", visibility="PUBLIC"))
    assert out["ok"] and out["post_urn"] == "urn:li:share:700" and out["visibility"] == "PUBLIC"
    body = posted["body"]
    assert body["author"] == "urn:li:person:abc123"
    assert body["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"] == "Shipped 5 PRs today"
    assert body["visibility"]["com.linkedin.ugc.MemberNetworkVisibility"] == "PUBLIC"


async def test_share_validation(token):
    assert "error" in await linkedin(LinkedInInput(action="share", text=""))
    assert "error" in await linkedin(LinkedInInput(action="share", text="hi", visibility="FRIENDS"))
    assert "error" in await linkedin(LinkedInInput(action="bogus"))


async def test_401_clean_and_secret_free(token, monkeypatch):
    def userinfo(request):
        return httpx.Response(401, json={"message": "unauthorized"})
    transport = mock_transport({("GET", "/v2/userinfo"): userinfo})
    monkeypatch.setattr("noesek.tools.linkedin.httpx.AsyncClient",
                        lambda **kw: _REAL_CLIENT(transport=transport, **kw))
    out = await linkedin(LinkedInInput(action="profile"))
    assert "401" in out["error"] and "test-token-123" not in str(out)
