"""Channel-native file delivery: push outbox files into the chat's channel.

When the conversation lives on WhatsApp, the user gets the actual document -
not a link they have to click. Falls back to the download path when the
channel has no native delivery or the push fails; the file is always in the
outbox either way.
"""
from __future__ import annotations

from ..db import Conversation, Session


async def deliver_file(conversation_id: int, name: str, data: bytes, mime: str,
                       caption: str = "") -> dict | None:
    """Try a native push. Returns a delivery note dict, or None for link-only."""
    async with Session() as s:
        conv = await s.get(Conversation, conversation_id)
    if conv is None or conv.channel != "whatsapp":
        return None
    try:
        from ..channels import whatsapp
        out = await whatsapp.send_document(conv.external_user_id, name, data, mime, caption)
    except Exception:
        return {"delivered": None, "note": "whatsapp push failed; use the download link"}
    if out.get("dry_run"):
        return {"delivered": None, "note": "whatsapp not configured; use the download link"}
    return {"delivered": "whatsapp", "media_id": out.get("media_id", "")}
