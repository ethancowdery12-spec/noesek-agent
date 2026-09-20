"""Google connector tools: read Gmail with a chat's stored OAuth grant.

The grant comes from the OAuth loop (connectors.TokenStore) - these helpers
are pure HTTP against the Gmail API plus token lookup, so tests stub the
transport. Write actions stay out until Ethan asks for them.
"""
from __future__ import annotations

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GrantMissing(RuntimeError):
    pass


async def list_messages(token: str, max_results: int = 5) -> list[dict]:
    """Recent inbox messages: id, from, subject, date, snippet."""
    import httpx

    max_results = max(1, min(int(max_results), 20))
    async with httpx.AsyncClient(timeout=20) as client:
        headers = {"Authorization": f"Bearer {token}"}
        listing = await client.get(f"{GMAIL_API}/messages",
                                   params={"maxResults": max_results, "labelIds": "INBOX"},
                                   headers=headers)
        if listing.status_code == 401:
            raise GrantMissing("google token was rejected (expired or revoked)")
        listing.raise_for_status()
        ids = [m["id"] for m in listing.json().get("messages", [])]
        out = []
        for mid in ids:
            msg = await client.get(f"{GMAIL_API}/messages/{mid}",
                                   params={"format": "metadata",
                                           "metadataHeaders": ["From", "Subject", "Date"]},
                                   headers=headers)
            if msg.status_code != 200:
                continue
            data = msg.json()
            hdrs = {h["name"].lower(): h["value"]
                    for h in data.get("payload", {}).get("headers", [])}
            out.append({
                "id": mid,
                "from": hdrs.get("from", ""),
                "subject": hdrs.get("subject", ""),
                "date": hdrs.get("date", ""),
                "snippet": data.get("snippet", ""),
            })
        return out
