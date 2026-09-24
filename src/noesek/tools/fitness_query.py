"""fitness_query: recent workouts from the chat's connected Strava account.

Wearable-OAuth tranche PR2 (roadmap item 87 follow-up). Read-only by default:
answers "how was my run?" from the Strava API. log=True also saves the fetched
activities as deduped kind='workout' memories (same entry shape as fit_import).
Refresh handling: a 401 triggers one refresh_grant retry before the tool asks
the user to reconnect.

Guardrails (batch-4 brief): informational-only health tooling - not medical
advice. No background polling; activities are fetched only when asked.
"""
from __future__ import annotations

import json
import re
import time

from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import connectors
from ..connectors import strava as st
from ..db import Conversation, Memory, Session

_ID_RE = re.compile(r'"strava_id":\s*(\d+)')


class FitnessQueryInput(BaseModel):
    days: int = Field(default=7, ge=1, le=30,
                      description="How far back to look (1-30 days, default 7)")
    limit: int = Field(default=10, ge=1, le=30,
                       description="Max activities to return (default 10)")
    log: bool = Field(default=False,
                      description="Also save the fetched activities as workout memories (deduped)")


def _entry(a: dict) -> dict:
    return {"date": (a.get("start_date") or "")[:10] or None,
            "activity": a.get("sport") or "unknown",
            "name": a.get("name") or None,
            "duration_min": a.get("moving_time_min"),
            "distance_km": a.get("distance_km"),
            "elevation_m": a.get("elevation_m"),
            "avg_hr": a.get("avg_hr"), "max_hr": a.get("max_hr"),
            "strava_id": a.get("id")}


def fitness_query_handler(conversation_id: int):
    async def f(inp: FitnessQueryInput) -> dict:
        async with Session() as s:
            conv = await s.get(Conversation, conversation_id)
        chat_id = conv.external_user_id if conv else ""
        grant = await connectors.default_store().get("strava", chat_id)
        if grant is None:
            return {"ok": False,
                    "error": "Strava is not connected for this chat",
                    "connect": f"POST /connectors/strava/auth-start with chat_id={chat_id!r}, "
                               "open the returned URL, approve once"}
        after_ts = int(time.time()) - inp.days * 86400
        try:
            acts = await st.list_activities(grant["access_token"], inp.limit, after_ts)
        except st.GrantMissing:
            fresh = await connectors.refresh_grant("strava", chat_id)
            if not fresh:
                return {"ok": False,
                        "error": "the Strava grant expired and could not be refreshed - "
                                 "please reconnect Strava (auth-start link again)"}
            acts = await st.list_activities(fresh, inp.limit, after_ts)

        entries = [_entry(a) for a in acts]
        out: dict = {"ok": True, "days": inp.days, "count": len(entries),
                     "activities": [{k: v for k, v in e.items() if v is not None} for e in entries],
                     "note": "Informational only - not medical advice."}
        if not inp.log or not entries:
            return out

        async with Session() as s:
            existing = (await s.execute(
                select(Memory.content).where(Memory.conversation_id == conversation_id,
                                             Memory.kind == "workout", Memory.active))).scalars().all()
        seen = {int(m.group(1)) for c in existing for m in [_ID_RE.search(c or "")] if m}
        added = 0
        async with Session() as s:
            for e in entries:
                if e["strava_id"] in seen:
                    continue
                s.add(Memory(conversation_id=conversation_id, kind="workout",
                             content=json.dumps(e, ensure_ascii=False), source="fitness_query"))
                seen.add(e["strava_id"])
                added += 1
            await s.commit()
        out["logged"] = added
        out["skipped_duplicates"] = len(entries) - added
        return out
    return f
