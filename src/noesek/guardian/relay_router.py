"""Relay-facing endpoints for the Kaggle guardian kernel
(docs/GUARDIAN_SERVING.md). All three require the X-Guardian-Relay-Key
header; with NOESEK_GUARDIAN_RELAY_KEY unset the relay is unconfigured and
every endpoint 503s rather than running open. The controller itself never
calls these - the gate talks to the JobStore in-process.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings
from .relay_store import get_store

router = APIRouter(prefix="/internal/guardian", tags=["guardian-relay"])


def _auth(x_guardian_relay_key: str | None):
    if not settings.guardian_relay_key:
        raise HTTPException(503, "guardian relay not configured (NOESEK_GUARDIAN_RELAY_KEY unset)")
    if not x_guardian_relay_key or x_guardian_relay_key != settings.guardian_relay_key:
        raise HTTPException(403, "bad relay key")


class RelayResult(BaseModel):
    deny_score: float
    esc_prob: float
    top_risk: str | None = None


@router.get("/jobs/next")
async def next_job(wait: float = 25.0, x_guardian_relay_key: str | None = Header(None)):
    """Long-poll for the oldest pending job. 204 when the wait elapses empty."""
    _auth(x_guardian_relay_key)
    wait = max(0.0, min(wait, 30.0))
    deadline = asyncio.get_event_loop().time() + wait
    while True:
        job = await asyncio.to_thread(get_store().claim_next)
        if job is not None:
            return {"id": job["id"], "state": job["state"]}
        if asyncio.get_event_loop().time() >= deadline:
            from fastapi import Response
            return Response(status_code=204)
        await asyncio.sleep(0.5)


@router.post("/jobs/{job_id}/result")
async def post_result(job_id: str, body: RelayResult, x_guardian_relay_key: str | None = Header(None)):
    _auth(x_guardian_relay_key)
    ok = await asyncio.to_thread(
        get_store().complete, job_id,
        {"deny_score": body.deny_score, "esc_prob": body.esc_prob, "top_risk": body.top_risk})
    if not ok:
        raise HTTPException(404, "unknown or already-completed job")
    return {"ok": True}


@router.get("/health")
async def relay_health(x_guardian_relay_key: str | None = Header(None)):
    _auth(x_guardian_relay_key)
    counts = await asyncio.to_thread(get_store().counts)
    return {"ok": True, "jobs": counts}
