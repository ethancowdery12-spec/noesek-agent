"""LinkedIn capability layer (roadmap item 52) - official API only.

Connector-shaped: the tool activates only when a real LinkedIn member access
token is present (NOESEK_LINKEDIN_ACCESS_TOKEN); otherwise it answers with a
clean not-configured message and setup pointer. Uses LinkedIn's official REST
API (https://api.linkedin.com/v2) - NOT the paid third-party "Linked API" that
item 28 rejected. The token never appears in output, logs, or errors.

Actions: profile (who am I - OpenID userinfo), share (post text as the member,
visibility PUBLIC or CONNECTIONS). Write actions flow through the approval
contract like every other Risk.WRITE tool.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..config import settings

_API = "https://api.linkedin.com/v2"
_NOT_CONFIGURED = {
    "error": "LinkedIn is not configured",
    "setup": ("Set NOESEK_LINKEDIN_ACCESS_TOKEN to a member access token from your own LinkedIn app "
              "(developer.linkedin.com > create app > products: Sign In with LinkedIn using OpenID Connect "
              "+ Share on LinkedIn; scopes: openid profile w_member_social). The token stays server-side."),
}


class LinkedInInput(BaseModel):
    action: str = Field(description="profile | share")
    text: str = Field(default="", max_length=3000, description="share: the post text")
    visibility: str = Field(default="CONNECTIONS", description="share: PUBLIC or CONNECTIONS")


async def _request(method: str, path: str, token: str, json_body: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as c:
        r = await c.request(method, f"{_API}{path}",
                            headers={"Authorization": f"Bearer {token}",
                                     "X-Restli-Protocol-Version": "2.0.0"},
                            json=json_body)
        r.raise_for_status()
        return r


def _err(e: Exception) -> dict:
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403):
        return {"error": f"LinkedIn rejected the token (HTTP {status}) - expired or missing scope. See setup.", "setup": _NOT_CONFIGURED["setup"]}
    return {"error": f"LinkedIn request failed: {type(e).__name__} (HTTP {status or 'n/a'})"}


async def linkedin(inp: LinkedInInput) -> dict:
    token = (settings.linkedin_access_token or "").strip()
    if not token:
        return dict(_NOT_CONFIGURED)
    action = inp.action.strip().lower()
    try:
        if action == "profile":
            r = await _request("GET", "/userinfo", token)
            d = r.json()
            return {"ok": True, "name": d.get("name", ""), "given_name": d.get("given_name", ""),
                    "family_name": d.get("family_name", ""), "person_urn": f"urn:li:person:{d.get('sub', '')}"}
        if action == "share":
            text = inp.text.strip()
            if not text:
                return {"error": "share requires text"}
            visibility = inp.visibility.strip().upper()
            if visibility not in ("PUBLIC", "CONNECTIONS"):
                return {"error": "visibility must be PUBLIC or CONNECTIONS"}
            me = (await _request("GET", "/userinfo", token)).json()
            body = {
                "author": f"urn:li:person:{me.get('sub', '')}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {"com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"}},
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
            }
            r = await _request("POST", "/ugcPosts", token, body)
            return {"ok": True, "post_urn": r.headers.get("x-restli-id", ""), "visibility": visibility}
        return {"error": f"unknown action '{inp.action}'", "actions": ["profile", "share"]}
    except Exception as e:  # token is never part of the exception text
        return _err(e)
