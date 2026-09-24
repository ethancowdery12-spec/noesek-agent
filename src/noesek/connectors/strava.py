"""Strava connector reads: recent athlete activities via a chat's stored grant.

Pure HTTP against the Strava V3 API plus token lookup, matching the Google and
GitHub connector helpers (no SDK dependency). Access tokens expire after a few
hours; connectors.refresh_grant renews them with the stored refresh token.
"""
from __future__ import annotations

ACTIVITIES_API = "https://www.strava.com/api/v3/athlete/activities"


class GrantMissing(RuntimeError):
    pass


async def list_activities(token: str, limit: int = 10, after_ts: int = 0) -> list[dict]:
    """Recent activities, newest first: id, name, sport, date, distance, time,
    elevation, average heart rate when the device recorded it."""
    import httpx

    limit = max(1, min(int(limit), 30))
    params: dict = {"per_page": limit}
    if after_ts:
        params["after"] = after_ts
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(ACTIVITIES_API, params=params,
                                headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 401:
        raise GrantMissing("strava token was rejected (expired or revoked)")
    resp.raise_for_status()
    out = []
    for a in resp.json():
        out.append({
            "id": a.get("id"),
            "name": a.get("name", ""),
            "sport": a.get("sport_type") or a.get("type", ""),
            "start_date": a.get("start_date", ""),
            "distance_km": round((a.get("distance") or 0) / 1000, 2),
            "moving_time_min": round((a.get("moving_time") or 0) / 60, 1),
            "elevation_m": a.get("total_elevation_gain"),
            "avg_hr": a.get("average_heartrate"),
            "max_hr": a.get("max_heartrate"),
        })
    return out
