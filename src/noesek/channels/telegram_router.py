"""Telegram webhook router: secret-token-verified ingress behind the authz gate."""
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from ..core.metrics import inc
from ..db import Session, get_or_create_conversation
from .authorization import get_gate
from .core_controller import get_controller
from .telegram import TelegramWebhookAdapter
from .telegram_sdk import TelegramTransport

log = logging.getLogger("noesek.telegram")
router = APIRouter()
transport = TelegramTransport()
adapter = TelegramWebhookAdapter()


async def send_telegram(chat_id: str, text: str):
    return await transport.send_text(chat_id, text)


@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request,
                           x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if not transport.verify_webhook(x_telegram_bot_api_secret_token):
        raise HTTPException(401, "bad secret token")
    payload = await request.json()
    gate = get_gate()
    for env in await adapter.normalize(payload):
        inc("noesek_inbound_total")
        source = gate.make_source(platform="telegram", chat_id=env.conversation,
                                  user_id=env.sender)
        if not gate.is_authorized(source):
            inc("noesek_unauthorized_total")
            continue
        async with Session() as s:
            conv = await get_or_create_conversation(s, "telegram", env.sender)
            await s.commit(); cid = conv.id
        result = await get_controller().handle(cid, env.text, env.external_id or None)
        if result.text:
            await send_telegram(env.conversation, result.text)
    return {"ok": True}
