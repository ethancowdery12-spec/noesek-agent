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


async def send_message(token: str, to: str, subject: str, body: str) -> dict:
    """Send one plain-text email through the Gmail API.

    The grant needs the gmail.send scope; older readonly grants get a 403
    from Google and must re-auth. Builds the RFC822 message client-side and
    posts base64url, so no message content ever touches a log line here.
    """
    import base64
    import httpx

    if not to or "@" not in to:
        raise ValueError("recipient must be an email address")
    raw = (f"To: {to}\r\nSubject: {subject}\r\n"
           f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}")
    encoded = base64.urlsafe_b64encode(raw.encode()).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{GMAIL_API}/messages/send",
                                 json={"raw": encoded},
                                 headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            raise GrantMissing("google token was rejected (expired or revoked)")
        if resp.status_code == 403:
            raise GrantMissing("grant lacks gmail.send - reconnect Google to add it")
        resp.raise_for_status()
        data = resp.json()
        return {"id": data.get("id", ""), "thread_id": data.get("threadId", "")}


CALENDAR_API = "https://www.googleapis.com/calendar/v3"


async def list_events(token: str, max_results: int = 5) -> list[dict]:
    """Upcoming primary-calendar events: id, summary, start, end, location."""
    import httpx
    from datetime import datetime, timezone

    max_results = max(1, min(int(max_results), 20))
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{CALENDAR_API}/calendars/primary/events",
            params={
                "maxResults": max_results,
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": datetime.now(timezone.utc).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            raise GrantMissing("google token was rejected (expired or revoked)")
        resp.raise_for_status()
        out = []
        for ev in resp.json().get("items", []):
            out.append({
                "id": ev.get("id", ""),
                "summary": ev.get("summary", ""),
                "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date", ""),
                "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date", ""),
                "location": ev.get("location", ""),
            })
        return out
