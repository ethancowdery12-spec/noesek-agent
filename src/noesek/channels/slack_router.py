"""Slack Events API router: signature-verified ingress behind the authz gate."""
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from ..core.metrics import inc
from ..db import Session, get_or_create_conversation
from .authorization import get_gate
from .core_controller import get_controller  # shared controller instance
from .slack import SlackEventsAdapter
from .slack_sdk import SlackTransport

log = logging.getLogger("noesek.slack")
router = APIRouter()
transport = SlackTransport()
adapter = SlackEventsAdapter()


async def send_slack(channel: str, text: str):
    return await transport.send_text(channel, text)


@router.post("/webhooks/slack")
async def slack_events(request: Request,
                       x_slack_request_timestamp: str | None = Header(default=None),
                       x_slack_signature: str | None = Header(default=None)):
    body = await request.body()
    if not transport.verify_request(body, x_slack_request_timestamp or "", x_slack_signature or ""):
        raise HTTPException(401, "bad signature")
    payload = await request.json()
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    gate = get_gate()
    for env in await adapter.normalize(payload):
        inc("noesek_inbound_total")
        source = gate.make_source(platform="slack", chat_id=env.conversation,
                                  user_id=env.sender)
        if not gate.is_authorized(source):
            inc("noesek_unauthorized_total")
            continue
        async with Session() as s:
            conv = await get_or_create_conversation(s, "slack", env.sender)
            await s.commit(); cid = conv.id
        result = await get_controller().handle(cid, env.text, env.external_id or None)
        if result.text:
            await send_slack(env.conversation, result.text)
    return {"ok": True}
