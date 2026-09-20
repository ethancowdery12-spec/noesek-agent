"""GitHub connector tools: read notifications with a chat's stored grant."""
from __future__ import annotations

GITHUB_API = "https://api.github.com"


class GrantMissing(RuntimeError):
    pass


async def list_notifications(token: str, max_results: int = 10) -> list[dict]:
    """Unread notifications: repo, title, type, reason, updated_at."""
    import httpx

    max_results = max(1, min(int(max_results), 30))
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{GITHUB_API}/notifications",
            params={"per_page": max_results},
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"})
        if resp.status_code == 401:
            raise GrantMissing("github token was rejected (expired or revoked)")
        resp.raise_for_status()
        out = []
        for n in resp.json():
            out.append({
                "id": n.get("id", ""),
                "repo": (n.get("repository") or {}).get("full_name", ""),
                "title": (n.get("subject") or {}).get("title", ""),
                "type": (n.get("subject") or {}).get("type", ""),
                "reason": n.get("reason", ""),
                "updated_at": n.get("updated_at", ""),
            })
        return out
