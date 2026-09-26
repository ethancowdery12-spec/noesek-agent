"""Obsidian channel router: pairing endpoints + token-authenticated message POST.

v1 transport is synchronous: POST /channels/obsidian/messages holds until the
controller reply is ready (a one-shot long-poll), so the plugin needs no SSE
client. Replies containing edit proposals travel as text blocks; the plugin
previews and applies them locally (docs/OBSIDIAN_PLUGIN.md).
"""
import logging

from fastapi import APIRouter, HTTPException, Request

from ..core.metrics import inc
from ..db import Session, get_or_create_conversation
from .authorization import get_gate
from .core_controller import get_controller
from .obsidian import ContextTooLarge, ObsidianTokenStore, fold_context

log = logging.getLogger("noesek.obsidian")
router = APIRouter()
store = ObsidianTokenStore()


def _source(gate, device_id: str):
    return gate.make_source(platform="obsidian", chat_id=device_id, user_id=device_id)


def _authed_device(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    device_id = store.validate(token)
    if not device_id:
        raise HTTPException(401, "invalid or missing bearer token")
    if not get_gate().is_authorized(_source(get_gate(), device_id)):
        raise HTTPException(403, "device authorization revoked")
    return device_id


@router.post("/channels/obsidian/pair/start")
async def pair_start(request: Request):
    payload = await request.json()
    device_id = str(payload.get("device_id", "")).strip()
    if not device_id:
        raise HTTPException(400, "device_id required")
    gate = get_gate()
    if gate.is_authorized(_source(gate, device_id)):
        # Already paired device re-keying: issue a fresh token, no new code.
        return {"status": "approved", "token": store.issue(device_id)}
    code = gate.start_pairing("obsidian", device_id, str(payload.get("device_name", "")))
    if code is None:
        raise HTTPException(429, "pairing rate limited, try later")
    return {"status": "pending", "code": code}


@router.get("/channels/obsidian/pair/status")
async def pair_status(device_id: str):
    gate = get_gate()
    if not gate.is_authorized(_source(gate, device_id)):
        return {"status": "pending"}
    return {"status": "approved", "token": store.issue(device_id)}


@router.post("/channels/obsidian/messages")
async def post_message(request: Request):
    device_id = _authed_device(request)
    payload = await request.json()
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    try:
        folded, manifest = fold_context(text, payload.get("context") or [])
    except ContextTooLarge:
        raise HTTPException(413, "context over 50KB cap")
    inc("noesek_inbound_total")
    async with Session() as s:
        conv = await get_or_create_conversation(s, "obsidian", device_id)
        await s.commit()
        cid = conv.id
    result = await get_controller().handle(cid, folded, payload.get("client_msg_id") or None)
    return {"reply": result.text, "attachments_sent": manifest}
