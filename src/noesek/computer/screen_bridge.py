"""Screen HTTP + WebSocket bridge for noesek-computer.

HTTP routes manage the screen (status/start/stop/takeover/handback) and mint
single-use 30-second display tickets; the WebSocket route splices the screen's
0600 RFB Unix socket into binary frames for a noVNC viewer, running the client
stream through RfbClientFilter so keyboard, pointer and clipboard reach Xvnc
only from the viewer that currently holds the lease.

Adapted from Nous Research hermes-agent hermes_cli/web_routers/display.py (MIT
License; see THIRD_PARTY_NOTICES): same ticket + splice + lease-gate shape,
rebased on noesek's single-profile runtime and token gate.

Access model: every route here requires the NOESEK_SCREEN_TOKEN bearer or
?token= (the WS takes it as a query param because noVNC cannot set headers).
Unset token = the whole surface stays 503, so the feature is dark until an
operator flips it on. Tickets are single-use and expire in 30 seconds, so a
logged URL is spent by the time anyone reads it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from . import screen_lease, screen_runtime
from .rfb_filter import RfbClientFilter

log = logging.getLogger("noesek.computer.screen")
router = APIRouter()

_READ_CHUNK = 64 * 1024
_CLOSE_CONTROL_TAKEN = 4000
_CLEAN_CLOSE = frozenset({1000, 1001})
_CLOSE_DESKTOP_GONE = 4001
_CLOSE_BAD_TICKET = 4401
_CLOSE_NOT_ALLOWED = 4403
_CLOSE_PROTOCOL = 1003
_LEASE_REFRESH_S = 0.25
_TICKET_TTL_S = 30.0
_ACTIVITY_STAMP_S = 60.0

# ticket -> {"viewer_id": str, "expires": float}; consumed on first WS use.
_tickets: dict[str, dict] = {}


def _token() -> str:
    return os.environ.get("NOESEK_SCREEN_TOKEN", "").strip()


def _token_ok(request: Request) -> bool:
    tok = _token()
    if not tok:
        return False
    auth = request.headers.get("authorization", "")
    supplied = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
    return bool(supplied) and secrets.compare_digest(supplied, tok)


def _require_token(request: Request) -> None:
    if not _token():
        raise HTTPException(503, "screen access not configured (NOESEK_SCREEN_TOKEN unset)")
    if not _token_ok(request):
        raise HTTPException(403, "bad screen token")


@router.get("/computer/screen")
async def screen_status(request: Request):
    _require_token(request)
    return screen_runtime.status()


@router.post("/computer/screen/start")
async def screen_start(request: Request):
    _require_token(request)
    try:
        return screen_runtime.start()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@router.post("/computer/screen/stop")
async def screen_stop(request: Request, force: bool = False):
    _require_token(request)
    try:
        return screen_runtime.stop(force=force)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.post("/computer/screen/takeover")
async def screen_takeover(request: Request, reason: str = ""):
    """The calling human takes control; the agent's computer tools refuse with
    human_has_control until handback. Returns the viewer_id to present on the WS."""
    _require_token(request)
    viewer_id = secrets.token_hex(16)
    lease = screen_lease.acquire(viewer_id, reason=reason)
    return {"control": screen_lease.public_view(lease), "viewer_id": viewer_id}


@router.post("/computer/screen/handback")
async def screen_handback(request: Request, viewer_id: str = ""):
    _require_token(request)
    lease = screen_lease.release(viewer_id or None)
    return {"control": screen_lease.public_view(lease)}


@router.post("/computer/screen/ticket")
async def screen_ticket(request: Request, viewer_id: str = ""):
    """Mint a single-use 30 s display ticket. A watcher calls without a viewer_id
    (view-only); the controlling viewer passes the id from /takeover so its input
    passes the RFB gate."""
    _require_token(request)
    if not screen_runtime.running():
        raise HTTPException(503, "screen is not running")
    expired = [t for t, info in _tickets.items() if info["expires"] < time.time()]
    for t in expired:
        _tickets.pop(t, None)
    ticket = secrets.token_urlsafe(24)
    _tickets[ticket] = {"viewer_id": viewer_id, "expires": time.time() + _TICKET_TTL_S}
    return {"ticket": ticket, "expires_in": _TICKET_TTL_S}


def _consume_ticket(ticket: str) -> dict | None:
    info = _tickets.pop(ticket, None)  # pop = single-use, even on failure
    if not info or info["expires"] < time.time():
        return None
    return info


@router.websocket("/computer/screen/ws")
async def screen_ws(ws: WebSocket):
    # Token policy refused BEFORE accept (a cross-origin page never gets a completed
    # handshake); ticket and screen state refused AFTER accept so the code + reason
    # arrive in a close frame the viewer can read.
    tok = _token()
    supplied = ws.query_params.get("token", "")
    if not tok or not supplied or not secrets.compare_digest(supplied, tok):
        await ws.close(code=_CLOSE_NOT_ALLOWED)
        return
    await ws.accept()
    info = _consume_ticket(ws.query_params.get("ticket", ""))
    if info is None:
        await ws.close(code=_CLOSE_BAD_TICKET, reason="display ticket missing, expired or used")
        return
    await _bridge(ws, info)


async def _bridge(ws: WebSocket, info: dict) -> None:
    """Pump RFB bytes between the viewer socket (already accepted) and Xvnc, gated by the lease."""
    sock = screen_runtime.socket_path()
    viewer_id = str(info.get("viewer_id") or "")
    if not sock.exists():
        await ws.close(code=_CLOSE_DESKTOP_GONE, reason="screen is not running")
        return
    try:
        reader, writer = await asyncio.open_unix_connection(str(sock))
    except OSError as exc:
        log.warning("screen ws: cannot reach RFB socket %s: %s", sock, exc)
        await ws.close(code=_CLOSE_DESKTOP_GONE, reason="screen socket unreachable")
        return

    loop = asyncio.get_running_loop()
    evicted = asyncio.Event()
    # A viewer that held control during this connection and lost it to ANOTHER human is
    # kicked so its UI repaints; a plain hand-back to the agent, pure watchers and the new
    # holder stay connected.
    held = {"ever": bool(viewer_id) and screen_lease.viewer_may_send_input(viewer_id)}
    # Input gate cache: a stat+read of lease.json per client message is replaced by a
    # decision refreshed on this process's on_change callback and by a file re-read at
    # most every _LEASE_REFRESH_S, so another process's takeover still lands.
    allowed = {"input": held["ever"], "at": loop.time()}

    def _refresh_allowed(lease=None) -> None:
        if lease is None:
            lease = screen_lease.get()
        allowed["input"] = bool(viewer_id) and lease.holder == screen_lease.HUMAN and lease.viewer_id == viewer_id
        allowed["at"] = loop.time()

    def _may_send_input() -> bool:
        if loop.time() - allowed["at"] > _LEASE_REFRESH_S:
            _refresh_allowed()
        return allowed["input"]

    def _on_lease(lease) -> None:
        loop.call_soon_threadsafe(_refresh_allowed, lease)
        if lease.holder == screen_lease.HUMAN and lease.viewer_id != viewer_id and held["ever"]:
            loop.call_soon_threadsafe(evicted.set)
        elif lease.holder != screen_lease.HUMAN:
            held["ever"] = False
        elif lease.viewer_id == viewer_id:
            held["ever"] = True

    unsubscribe = screen_lease.on_change(_on_lease)
    rfb_filter = RfbClientFilter(_may_send_input)
    viewer_closed = asyncio.Event()
    stamped = {"at": 0.0}

    def _stamp_activity() -> None:
        # An attached viewer is use: the idle auto-stop must not take a screen someone
        # is watching.
        if loop.time() - stamped["at"] < _ACTIVITY_STAMP_S:
            return
        stamped["at"] = loop.time()
        try:
            screen_runtime.activity_path().touch()
        except OSError:
            pass

    async def rfb_to_ws() -> None:
        while True:
            chunk = await reader.read(_READ_CHUNK)
            if not chunk:
                return
            _stamp_activity()
            await ws.send_bytes(chunk)  # awaiting the send is the backpressure toward Xvnc

    async def ws_to_rfb() -> None:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                # 1000/1001 = the viewer closed the window; anything else is a dropped link.
                if message.get("code") in _CLEAN_CLOSE:
                    viewer_closed.set()
                return
            data = message.get("bytes")
            if data is None:
                await ws.close(code=_CLOSE_PROTOCOL, reason="RFB is binary")
                return
            try:
                out = rfb_filter.feed(data)
            except ValueError as exc:
                await ws.close(code=_CLOSE_PROTOCOL, reason=str(exc)[:100])
                return
            if out:
                writer.write(out)
                await writer.drain()  # backpressure toward the browser

    async def watch_eviction() -> None:
        await evicted.wait()
        await ws.close(code=_CLOSE_CONTROL_TAKEN, reason="control-taken")

    tasks = [asyncio.create_task(rfb_to_ws()), asyncio.create_task(ws_to_rfb()),
             asyncio.create_task(watch_eviction())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        # Cancelled pumps must finish before we tear down the socket they hold.
        await asyncio.gather(*pending, return_exceptions=True)
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, ConnectionError)):
                log.debug("screen ws ended: %r", exc)
    finally:
        unsubscribe()
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:  # Xvnc already gone (ECONNRESET / EPIPE on the FIN)
            pass
        # Closing the viewer window hands control back. A DROPPED link (laptop lid,
        # Wi-Fi, 1006) keeps the human's exclusion: they may be mid-login on that
        # screen and the agent must not resume into it.
        if viewer_closed.is_set() and viewer_id and screen_lease.viewer_may_send_input(viewer_id):
            screen_lease.release(viewer_id)
        try:
            await ws.close()
        except Exception:  # already closed by the peer or by an eviction
            pass
