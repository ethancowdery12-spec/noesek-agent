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
import re
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .. import __version__
from ..channels.core_controller import get_controller
from ..channels.whatsapp import router as whatsapp_router
from ..channels.slack_router import router as slack_router
from ..channels.telegram_router import router as telegram_router
from ..config import settings
from ..db import Session, init_db, migrate, get_or_create_conversation
from ..core.browser_backend import PlaywrightExecutor, BrowserBackendError
from ..core.computer_use import ComputerPlan
from .. import connectors
from .. import proactive
from .. import vault
from .. import filestore
from .. import voice

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


_APPROVE_RE = re.compile(r"\s*(approve|reject)\s+(\d+)\s*", re.I)

app = FastAPI(title="Noesek Computer", version=__version__)
app.include_router(whatsapp_router)
app.include_router(slack_router)
app.include_router(telegram_router)


@app.on_event("startup")
async def _startup() -> None:
    await init_db()
    await migrate()
    # Item 89: AST code-intel startup index behind the flag. Best-effort: a
    # failure here must never block boot. The log line doubles as the staging
    # validation signal (deploy shells are not always available).
    if settings.code_intel_enabled:
        try:
            from ..core.code_intel import default_root, index_root
            _root = settings.code_intel_root or default_root()
            _stats = index_root(_root, settings.code_intel_db)
            log.info(
                "code_intel index: %d files, %d symbols, %d edges (%d changed, root=%s)",
                _stats["files"], _stats["symbols"], _stats["edges"], _stats["changed"], _root)
        except Exception:
            log.exception("code_intel startup index failed (non-fatal)")
    from ..channels import outbound
    from ..jobs import recover_interrupted, task_worker
    recovered = await recover_interrupted()
    if recovered["requeued"] or recovered["failed"]:
        log.warning("task durability sweep: %s", recovered)
    _ensure_display()
    # Without this the job queue never drains on the computer service:
    # delegate_task enqueues work that nothing executes (found by live test).
    app.state.task_worker_stop = asyncio.Event()
    app.state.task_worker = asyncio.create_task(
        task_worker(app.state.task_worker_stop, deliver=outbound.deliver))
    asyncio.create_task(_proactive_sweep())


@app.on_event("shutdown")
async def _shutdown() -> None:
    stop = getattr(app.state, "task_worker_stop", None)
    worker = getattr(app.state, "task_worker", None)
    if stop is not None:
        stop.set()
    if worker is not None:
        try:
            await worker
        except Exception:
            pass


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
    controller = get_controller()
    m = _APPROVE_RE.fullmatch(text)
    if m:
        result = await controller.decide_approval(cid, int(m.group(2)), m.group(1).lower() == "approve")
    elif re.fullmatch(r"\s*pending\s*", text, re.I):
        result = await controller.pending_approvals(cid)
    else:
        result = await controller.handle(cid, text)
    return {"chat_id": body.chat_id, "conversation_id": cid, "reply": result.text}


@app.get("/computer/screenshot")
async def screenshot():
    """PNG of the machine's display. The computer is a tool."""
    if not os.environ.get("DISPLAY") or not shutil.which("scrot"):
        raise HTTPException(503, "no display or scrot unavailable")
    fd, path = tempfile.mkstemp(suffix=".png")  # mkstemp: no mktemp race (security_audit insecure-temp)
    os.close(fd)
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


class BrowseIn(BaseModel):
    url: str
    actions: list[dict] | None = None
    timeout_ms: int = 30_000


_BROWSE_ACTIONS = {"navigate", "click", "type", "extract_text", "screenshot"}
_TEXT_CAP = 8000


@app.post("/computer/browser-state/import")
async def import_browser_state(request: Request):
    """Secure session import (item 56). Raw cookies.txt / JSON body goes
    straight into the Fernet-encrypted store - never through chat, model
    context, or logs. Response is domain names and counts only. Imported
    domains land DISABLED until explicitly enabled via the browser_cookies
    chat tool (the per-site approval)."""
    from ..core import browser_state as bstate
    if not (settings.browser_state_key or "").strip():
        raise HTTPException(400, "NOESEK_BROWSER_STATE_KEY is not set")
    body = (await request.body())
    if not body or len(body) > 1_000_000:
        raise HTTPException(400, "empty or oversized import body")
    try:
        cookies = bstate.parse_import(body.decode("utf-8", "replace"))
    except (bstate.BrowserStateError, ValueError):
        raise HTTPException(400, "unrecognized import format (expected cookies.txt or storage_state JSON)")
    state = (await bstate.load_state()) or {"cookies": [], "origins": [], "enabled": []}
    domains = bstate.merge_import(state, cookies)
    await bstate.save_state(state)
    await bstate.audit("import", ",".join(domains), f"{len(cookies)} cookies")
    return {"imported": len(cookies), "domains": domains, "pending": domains,
            "next": "enable per site with the browser_cookies chat tool"}


@app.post("/computer/browse")
async def browse(body: BrowseIn):
    """Drive Chromium as a tool: build a plan, validate it, execute it.

    Default plan: navigate + extract body text + screenshot. The server is
    the operator on-box, so it self-approves the plan digest after
    validation; remote approval rides the same digest contract later.
    """
    from urllib.parse import urlparse

    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "url must be http(s)")
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    actions = body.actions or [
        {"type": "navigate", "url": url},
        {"type": "extract_text", "selector": "body"},
        {"type": "screenshot"},
    ]
    allowed = {o.strip() for o in settings.computer_allowed_origins.split(",") if o.strip()}
    try:
        plan = ComputerPlan(origin=origin, actions=tuple(actions)).validate(
            allowed or {origin}, _BROWSE_ACTIONS)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    headless = os.environ.get("NOESEK_COMPUTER_BROWSER_HEADED", "") != "1"
    # Persistent sessions (item 56): profile dir + encrypted storage_state in the
    # DB. Degrades to the old fresh-profile behavior when no state key is set.
    profile_dir = ""
    restore = None
    state = None
    if settings.browser_state_key:
        from ..core import browser_state as bstate
        profile_dir = settings.browser_profile_dir or str(Path.home() / ".noesek" / "browser-profile")
        try:
            state = await bstate.load_state()
        except bstate.BrowserStateError:
            state = None  # unreadable state: start clean rather than fail the browse
        if state:
            # Approval-before-use: only ENABLED domains matching this origin
            # are restored into the run (item 56).
            restore = bstate.state_for_origin(state, origin)
            if restore["cookies"] or restore["origins"]:
                await bstate.audit("restore", origin, f"{len(restore['cookies'])} cookies, {len(restore['origins'])} origins")
            else:
                restore = None
    executor = PlaywrightExecutor(timeout_ms=body.timeout_ms, headless=headless,
                                  profile_dir=profile_dir or None, restore_state=restore)
    try:
        result = await execute_plan_for(plan, executor)
    except BrowserBackendError as exc:
        raise HTTPException(502, str(exc))
    exported = result.pop("storage_state", None)
    if profile_dir and exported and state is not None:
        from ..core import browser_state as bstate
        await bstate.save_state(bstate.merge_export(state, exported, origin))
    from ..core.content_guard import scan_untrusted
    for step in result["steps"]:
        if isinstance(step.get("text"), str):
            rep = scan_untrusted(step["text"])
            if not rep.clean:
                step["content_flags"] = [f["pattern"] for f in rep.flags] + [r["pattern"] for r in rep.redactions]
            if len(step["text"]) > _TEXT_CAP:
                step["text"] = step["text"][:_TEXT_CAP]
                step["text_truncated"] = True
    return result


async def execute_plan_for(plan, executor):
    """Self-approval seam: the on-box server is the operator."""
    from ..core.computer_use import execute_plan
    return await execute_plan(plan, plan.digest, executor)


class AuthStartIn(BaseModel):
    chat_id: str
    redirect_uri: str = "http://127.0.0.1:8780/connectors/callback"


class TokenIn(BaseModel):
    chat_id: str
    access_token: str


@app.get("/connectors")
async def list_connectors(chat_id: str = ""):
    """What can be connected, and which chats hold a grant."""
    store = connectors.default_store()
    out = []
    for c in connectors.all_connectors():
        entry = {
            "name": c.name,
            "tools": list(c.tools),
            "scopes": list(c.scopes),
            "configured": bool(c.client_id()),
        }
        if chat_id:
            entry["connected"] = store.get(c.name, chat_id) is not None
        out.append(entry)
    return {"connectors": out}


@app.post("/connectors/{name}/auth-start")
async def auth_start(name: str, body: AuthStartIn):
    """Build the browser consent URL; state binds the grant to the chat."""
    c = connectors.get(name)
    if c is None:
        raise HTTPException(404, f"unknown connector {name!r}")
    if not body.chat_id:
        raise HTTPException(400, "chat_id is required")
    if not c.client_id():
        raise HTTPException(400, f"NOESEK_CONNECTOR_{name.upper()}_CLIENT_ID is not set")
    url, state = connectors.build_authorize_url(c, body.chat_id, body.redirect_uri)
    connectors.default_store().put_state(state, name, body.chat_id, body.redirect_uri)
    return {"authorize_url": url, "state": state}


@app.get("/connectors/callback")
async def oauth_callback(code: str = "", state: str = ""):
    """Browser redirect target: verify state, exchange code, store the grant."""
    from fastapi.responses import HTMLResponse

    if not code or not state:
        raise HTTPException(400, "code and state are required")
    store = connectors.default_store()
    pending = store.pop_state(state)
    if pending is None:
        raise HTTPException(400, "unknown or expired state")
    c = connectors.get(pending["connector"])
    if c is None:
        raise HTTPException(400, "unknown connector in state")
    try:
        token = await connectors.exchange_code(c, code, pending.get("redirect_uri") or "")
    except connectors.ConnectorError as exc:
        raise HTTPException(502, str(exc))
    store.put(c.name, pending["chat_id"], token, c.scopes)
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif'>Connected {c.name} for chat "
        f"<b>{pending['chat_id']}</b>. You can close this tab.</body></html>")


@app.post("/connectors/{name}/token")
async def store_token(name: str, body: TokenIn):
    """Deposit a token for a chat (from the vault or a completed exchange)."""
    c = connectors.get(name)
    if c is None:
        raise HTTPException(404, f"unknown connector {name!r}")
    if not body.chat_id or not body.access_token:
        raise HTTPException(400, "chat_id and access_token are required")
    connectors.default_store().put(name, body.chat_id, body.access_token, c.scopes)
    return {"ok": True, "connector": name, "chat_id": body.chat_id}


class ProactiveIn(BaseModel):
    chat_id: str
    goal: str = ""
    interval_seconds: int = proactive.DEFAULT_INTERVAL_SECONDS


class ProactiveChatIn(BaseModel):
    chat_id: str


async def _run_tick(chat_id: str) -> dict:
    """One bounded wake for a chat. IDLE replies are withheld from the chat."""
    store = proactive.default_store()
    entry = store.get(chat_id)
    if entry is None or not entry.get("active"):
        raise HTTPException(404, "chat is not proactive-active")
    async with Session() as s:
        conv = await get_or_create_conversation(s, "local", chat_id)
        await s.commit()
        cid = conv.id
    result = await get_controller().handle(cid, proactive.nudge_text(entry.get("goal", "")))
    acted = result.text.strip() != proactive.IDLE
    store.reschedule(chat_id)
    return {"chat_id": chat_id, "acted": acted, "reply": result.text if acted else ""}


@app.post("/proactive/tick")
async def proactive_tick(body: ProactiveChatIn):
    if not body.chat_id:
        raise HTTPException(400, "chat_id is required")
    return await _run_tick(body.chat_id)


@app.post("/proactive/activate")
async def proactive_activate(body: ProactiveIn):
    if not body.chat_id:
        raise HTTPException(400, "chat_id is required")
    entry = proactive.default_store().activate(body.chat_id, body.goal, body.interval_seconds)
    return {"chat_id": body.chat_id, **entry}


@app.post("/proactive/pause")
async def proactive_pause(body: ProactiveChatIn):
    if not proactive.default_store().pause(body.chat_id):
        raise HTTPException(404, "chat was not proactive-active")
    return {"chat_id": body.chat_id, "active": False}


@app.get("/proactive")
async def proactive_list():
    return {"chats": proactive.default_store().all()}


async def _proactive_sweep() -> None:
    """Idle engine: wake due chats forever. Quiet unless a chat acts."""
    interval = float(os.environ.get("NOESEK_COMPUTER_PROACTIVE_SWEEP", "30"))
    while True:
        await asyncio.sleep(interval)
        try:
            for chat_id in proactive.default_store().due_chats():
                try:
                    outcome = await _run_tick(chat_id)
                    if outcome["acted"]:
                        log.info("proactive tick acted for %s", chat_id)
                except Exception:
                    log.exception("proactive tick failed for %s", chat_id)
        except Exception:
            log.exception("proactive sweep failed")


@app.get("/connectors/google/gmail/messages")
async def gmail_messages(chat_id: str, max_results: int = 5):
    """First real connector tool: read the chat's Gmail via its stored grant."""
    from ..connectors import google as gtool

    if not chat_id:
        raise HTTPException(400, "chat_id is required")
    grant = connectors.default_store().get("google", chat_id)
    if grant is None:
        raise HTTPException(403, "no google grant for this chat - run auth-start first")
    try:
        messages = await gtool.list_messages(grant["access_token"], max_results)
    except gtool.GrantMissing as exc:
        raise HTTPException(403, str(exc))
    return {"chat_id": chat_id, "count": len(messages), "messages": messages}


@app.get("/connectors/google/calendar/events")
async def calendar_events(chat_id: str, max_results: int = 5):
    """Upcoming events on the chat's primary calendar via its stored grant."""
    from ..connectors import google as gtool

    if not chat_id:
        raise HTTPException(400, "chat_id is required")
    grant = connectors.default_store().get("google", chat_id)
    if grant is None:
        raise HTTPException(403, "no google grant for this chat - run auth-start first")
    try:
        events = await gtool.list_events(grant["access_token"], max_results)
    except gtool.GrantMissing as exc:
        raise HTTPException(403, str(exc))
    return {"chat_id": chat_id, "count": len(events), "events": events}


@app.get("/connectors/github/notifications")
async def github_notifications(chat_id: str, max_results: int = 10):
    """Unread GitHub notifications via the chat-scoped grant."""
    from ..connectors import github as ghtool

    if not chat_id:
        raise HTTPException(400, "chat_id is required")
    grant = connectors.default_store().get("github", chat_id)
    if grant is None:
        raise HTTPException(403, "no github grant for this chat - run auth-start first")
    try:
        notes = await ghtool.list_notifications(grant["access_token"], max_results)
    except ghtool.GrantMissing as exc:
        raise HTTPException(403, str(exc))
    return {"chat_id": chat_id, "count": len(notes), "notifications": notes}


class InputIn(BaseModel):
    action: str  # click | type | key | move
    x: int = 0
    y: int = 0
    text: str = ""
    keys: str = ""  # xdotool key syntax, e.g. "ctrl+s"
    button: int = 1


_INPUT_ACTIONS = {"click", "type", "key", "move"}


@app.post("/computer/input")
async def computer_input(body: InputIn):
    """Touch the machine: mouse/keyboard on the virtual display via xdotool."""
    if body.action not in _INPUT_ACTIONS:
        raise HTTPException(400, f"action must be one of {sorted(_INPUT_ACTIONS)}")
    if not os.environ.get("DISPLAY") or not shutil.which("xdotool"):
        raise HTTPException(503, "no display or xdotool unavailable")
    if body.action == "move":
        cmd = ["xdotool", "mousemove", str(body.x), str(body.y)]
    elif body.action == "click":
        cmd = ["xdotool", "mousemove", str(body.x), str(body.y), "click", str(body.button)]
    elif body.action == "type":
        if not body.text:
            raise HTTPException(400, "text is required for type")
        cmd = ["xdotool", "type", "--delay", "20", "--", body.text]
    else:
        if not body.keys:
            raise HTTPException(400, "keys is required for key")
        cmd = ["xdotool", "key", "--", body.keys]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(502, f"input failed: {(err or b'').decode()[:200]}")
    return {"ok": True, "action": body.action}


class VaultIn(BaseModel):
    name: str
    value: str


@app.get("/vault")
async def vault_list():
    """Names + metadata only. Values are never listed."""
    return {"secrets": vault.default_store().names()}


@app.post("/vault")
async def vault_put(body: VaultIn):
    try:
        vault.default_store().put(body.name, body.value)
    except vault.VaultError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "name": body.name}


@app.get("/vault/{name}")
async def vault_get(name: str):
    """Single-name read for agent form fills. Localhost-only server."""
    try:
        entry = vault.default_store().get(name)
    except vault.VaultError as exc:
        raise HTTPException(400, str(exc))
    if entry is None:
        raise HTTPException(404, "no such secret")
    return {"name": name, "value": entry["value"], "stored_at": entry["stored_at"]}


@app.delete("/vault/{name}")
async def vault_delete(name: str):
    try:
        removed = vault.default_store().delete(name)
    except vault.VaultError as exc:
        raise HTTPException(400, str(exc))
    if not removed:
        raise HTTPException(404, "no such secret")
    return {"ok": True, "name": name}


@app.get("/files")
async def files_list():
    """Metadata for every agent-created file. Never contents."""
    return {"files": filestore.list_files()}


@app.get("/files/{name}")
async def files_get(name: str):
    """Download one agent-created file."""
    try:
        data = filestore.read_file(name)
    except filestore.FileStoreError as exc:
        raise HTTPException(404, str(exc))
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class VoiceIn(BaseModel):
    text: str
    name: str = "voice-note.wav"


@app.post("/voice/say")
async def voice_say(body: VoiceIn):
    """Synthesize a voice note (offline TTS) into the files outbox."""
    try:
        meta = await voice.synthesize(body.text, body.name)
    except voice.VoiceError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # bad file name etc.
        raise HTTPException(400, str(exc))
    return {"created": True, "download": f"/files/{meta['name']}", **meta}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "version": __version__, "display": os.environ.get("DISPLAY", "")}


def main() -> int:
    import uvicorn

    # Without a handler config the WARNING-level default swallows INFO lines
    # (e.g. the code_intel startup index validation signal). Env-tunable.
    logging.basicConfig(level=os.getenv("NOESEK_LOG_LEVEL", "INFO"))
    port = int(os.environ.get("NOESEK_COMPUTER_PORT", "8780"))
    host = os.environ.get("NOESEK_COMPUTER_HOST", "127.0.0.1")
    uvicorn.run("noesek.computer.server:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
