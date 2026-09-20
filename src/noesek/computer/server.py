"""Noesek computer runtime: channels + controller + computer tools.

One process serving:
- the messaging channel webhooks (WhatsApp/Slack/Telegram, same routers as
  the v2 service),
- a local chat channel (POST /chat) for on-box testing and simple
  front-ends - a chat_id is a session,
- computer endpoints (GET /computer/screenshot) proving the machine itself
  is a tool, behind the same process as the agent.

Starts a virtual display (Xvfb) when DISPLAY is unset so browser and
screenshot tools work headless.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from .. import __version__
from ..channels.core_controller import get_controller
from ..channels.whatsapp import router as whatsapp_router
from ..channels.slack_router import router as slack_router
from ..channels.telegram_router import router as telegram_router
from ..config import settings
from ..db import Session, init_db, migrate, get_or_create_conversation

log = logging.getLogger("noesek.computer")

DISPLAY = os.environ.get("NOESEK_COMPUTER_DISPLAY", ":99")


def _ensure_display() -> None:
    if os.environ.get("DISPLAY"):
        return
    if not shutil.which("Xvfb"):
        log.warning("Xvfb not installed; computer tools limited")
        return
    subprocess.Popen(
        ["Xvfb", DISPLAY, "-screen", "0", "1280x800x24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = DISPLAY
    log.info("virtual display up on %s", DISPLAY)


app = FastAPI(title="Noesek Computer", version=__version__)
app.include_router(whatsapp_router)
app.include_router(slack_router)
app.include_router(telegram_router)


@app.on_event("startup")
async def _startup() -> None:
    await init_db()
    await migrate()
    _ensure_display()


class ChatIn(BaseModel):
    chat_id: str
    text: str


@app.post("/chat")
async def chat(body: ChatIn):
    """Local channel: a chat_id is a session. Reply comes back inline."""
    text = (body.text or "").strip()
    if not body.chat_id or not text:
        raise HTTPException(400, "chat_id and text are required")
    async with Session() as s:
        conv = await get_or_create_conversation(s, "local", body.chat_id)
        await s.commit()
        cid = conv.id
    result = await get_controller().handle(cid, text)
    return {"chat_id": body.chat_id, "conversation_id": cid, "reply": result.text}


@app.get("/computer/screenshot")
async def screenshot():
    """PNG of the machine's display. The computer is a tool."""
    if not os.environ.get("DISPLAY") or not shutil.which("scrot"):
        raise HTTPException(503, "no display or scrot unavailable")
    path = tempfile.mktemp(suffix=".png")
    proc = await asyncio.create_subprocess_exec(
        "scrot", "-o", path,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await proc.wait()
    if proc.returncode != 0 or not os.path.exists(path):
        raise HTTPException(503, "screenshot failed")
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    return Response(content=data, media_type="image/png")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "version": __version__, "display": os.environ.get("DISPLAY", "")}


def main() -> int:
    import uvicorn

    port = int(os.environ.get("NOESEK_COMPUTER_PORT", "8780"))
    host = os.environ.get("NOESEK_COMPUTER_HOST", "127.0.0.1")
    uvicorn.run("noesek.computer.server:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
