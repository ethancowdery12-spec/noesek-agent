import hashlib, hmac, logging, re
import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from ..config import settings
from ..core.chunk import chunk_text
from ..core.controller import Controller
from ..core.metrics import inc
from ..core.ratelimit import RateLimiter
from ..db import Session, get_or_create_conversation
from . import outbound
from .authorization import get_gate

log = logging.getLogger("noesek.whatsapp")
router = APIRouter()
controller = Controller()
limiter = RateLimiter(settings.rate_limit_messages, settings.rate_limit_window_seconds)
authz_gate = get_gate()
notice_limiter = RateLimiter(1, settings.rate_limit_window_seconds)

HELP_TEXT = (
    "Commands:\n"
    "- approve ID / reject ID - decide a pending approval\n"
    "- pending - list pending approvals\n"
    "- help - this message\n"
    "Anything else is handled by the agent."
)
MEDIA_TYPES = {"image", "audio", "voice", "video", "document", "sticker", "location", "contacts"}
_APPROVE_RE = re.compile(r"\s*(approve|reject)\s+(\d+)\s*", re.I)

def valid_signature(body: bytes, signature: str | None) -> bool:
    if not settings.meta_app_secret: return True
    if not signature or not signature.startswith("sha256="): return False
    expected = hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))

@router.get("/webhooks/whatsapp")
async def verify(hub_mode: str = Query(alias="hub.mode"), hub_verify_token: str = Query(alias="hub.verify_token"), hub_challenge: str = Query(alias="hub.challenge")):
    if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, settings.verify_token):
        return Response(hub_challenge, media_type="text/plain")
    raise HTTPException(403, "verification failed")

async def send_text(to: str, text: str):
    chunks = chunk_text(text, 4096)
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return {"dry_run": True, "chunks": len(chunks)}
    url = f"https://graph.facebook.com/v22.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    out = []
    async with httpx.AsyncClient(timeout=30) as c:
        for chunk in chunks:
            payload = {"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":chunk}}
            r = await c.post(url, json=payload, headers=headers); r.raise_for_status(); out.append(r.json())
    return {"sent": len(out), "responses": out}

outbound.register("whatsapp", send_text)

async def _reply(sender: str, text: str):
    if text: await send_text(sender, text)

@router.post("/webhooks/whatsapp")
async def inbound(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    body = await request.body()
    if not valid_signature(body, x_hub_signature_256): raise HTTPException(401, "bad signature")
    payload = await request.json()
    for entry in payload.get("entry", []):
      for change in entry.get("changes", []):
        value = change.get("value", {})
        for msg in value.get("messages", []):
            sender = msg.get("from", "")
            inc("noesek_inbound_total")
            source = authz_gate.make_source(platform="whatsapp", chat_id=sender, user_id=sender)
            if not authz_gate.is_authorized(source):
                inc("noesek_unauthorized_total")
                behavior = authz_gate.unauthorized_dm_behavior("whatsapp")
                if behavior == "pair":
                    code = authz_gate.start_pairing("whatsapp", sender)
                    if code:
                        await _reply(sender, f"This Noesek agent hasn't been introduced to you yet. Pairing code: {code} - ask the owner to approve it.")
                elif behavior == "decline":
                    authz_gate.pairing_store.record_decline("whatsapp", sender)
                    await _reply(sender, "You're not authorized to talk to this agent.")
                continue
            if not limiter.allow(sender):
                inc("noesek_rate_limited_total")
                if notice_limiter.allow(sender):
                    await _reply(sender, "You're sending messages faster than I can handle. Give me a moment and try again.")
                continue
            async with Session() as s:
                conv = await get_or_create_conversation(s, "whatsapp", sender); await s.commit(); cid = conv.id
            mtype = msg.get("type")
            if mtype != "text":
                if mtype in MEDIA_TYPES:
                    await _reply(sender, f"I received your {mtype}. Media understanding isn't supported yet; describe it in text and I'll help.")
                continue
            text = msg.get("text", {}).get("body", "")
            if re.fullmatch(r"\s*help\s*", text, re.I):
                await _reply(sender, HELP_TEXT); continue
            if re.fullmatch(r"\s*pending\s*", text, re.I):
                await _reply(sender, (await controller.pending_approvals(cid)).text); continue
            m = _APPROVE_RE.fullmatch(text)
            if m:
                result = await controller.decide_approval(cid, int(m.group(2)), m.group(1).lower() == "approve")
            else:
                result = await controller.handle(cid, text, msg.get("id"))
            await _reply(sender, result.text)
    return {"ok": True}
