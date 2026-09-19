"""Adapter for upstream evals/slack_stream_wire_contract.py (Hermes c712f06d).

Upstream intent: wire-contract proof - run the real send path against a real
SDK client whose base_url points at a local receiver that records every
request, and prove the bytes satisfy the documented contract. No Slack
workspace or token involved. Noesek target: SlackTransport (pinned slack-sdk)
plus the /webhooks/slack router with a correctly signed inbound event.
"""
import asyncio
import hashlib
import hmac
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir

SECRET = "adapter-signing-secret"
RECEIVED = []


async def go(out):
    from aiohttp import web

    async def handler(request):
        RECEIVED.append({"path": request.path,
                         "auth": request.headers.get("Authorization", ""),
                         "body": await request.text()})
        return web.json_response({"ok": True, "ts": "1.0"})

    receiver = web.Application(); receiver.router.add_post("/{tail:.*}", handler)
    runner = web.AppRunner(receiver); await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]

    from slack_sdk.web.async_client import AsyncWebClient
    from noesek.channels.slack_sdk import SlackTransport
    transport = SlackTransport(bot_token="xoxb-adapter", signing_secret=SECRET,
                               client=AsyncWebClient(token="xoxb-adapter",
                                                     base_url=f"http://127.0.0.1:{port}"))
    send_result = await transport.send_text("C123", "wire contract hello")

    # inbound: correctly signed event through the real router
    import noesek.channels.slack_router as sr
    import noesek.channels.core_controller as cc
    from noesek.channels.authorization import get_gate
    from noesek.core.controller import Controller
    from noesek.db import init_db

    class EchoLLM:
        async def complete(self, messages, schemas):
            class Reply:
                content = "echo"
                tool_calls = []
            return Reply()

    await init_db()
    gate = get_gate()
    code = gate.pairing_store.generate_code("slack", "U7", "Wire User")
    assert code and gate.approve_code("slack", code)
    cc._controller = Controller(llm=EchoLLM())
    sr.transport = transport

    from httpx import ASGITransport, AsyncClient
    from noesek.main import app

    def sign(body: bytes):
        ts = str(int(time.time()))
        base = b"v0:" + ts.encode() + b":" + body
        return ts, "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        body = json.dumps({"type": "url_verification", "challenge": "ch-1"}).encode()
        ts, sig = sign(body)
        challenge = await client.post("/webhooks/slack", content=body,
                                      headers={"X-Slack-Request-Timestamp": ts,
                                               "X-Slack-Signature": sig})
        body = json.dumps({"type": "event_callback", "event_id": "Ev1",
                           "event": {"type": "message", "user": "U7",
                                     "channel": "C123", "text": "hi"}}).encode()
        ts, sig = sign(body)
        event = await client.post("/webhooks/slack", content=body,
                                  headers={"X-Slack-Request-Timestamp": ts,
                                           "X-Slack-Signature": sig})
    await runner.cleanup()
    return {"challenge_status": challenge.status_code,
            "challenge_echo": challenge.text,
            "event_status": event.status_code,
            "outbound_calls": RECEIVED,
            "send_result_ok": bool(send_result)}


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    import os
    os.environ.update({"NOESEK_HOME": str(home), "HERMES_HOME": str(home),
                       "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{home}/noesek.db",
                       "NOESEK_SLACK_BOT_TOKEN": "xoxb-adapter",
                       "NOESEK_SLACK_SIGNING_SECRET": SECRET})
    res = asyncio.run(go(out))
    (out / "wire.json").write_text(json.dumps(res, indent=2) + "\n")
    posts = [r for r in res["outbound_calls"] if r["path"].endswith("chat.postMessage")]
    contract = (all(r["auth"] == "Bearer xoxb-adapter" for r in posts)
                and all('"channel"' in r["body"] and '"text"' in r["body"] for r in posts))
    ok = (res["challenge_status"] == 200 and "ch-1" in res["challenge_echo"]
          and res["event_status"] == 200 and len(posts) >= 2 and contract)
    emit("pass" if ok else "fail", outbound_post_message_calls=len(posts),
         contract_ok=contract, challenge_status=res["challenge_status"],
         event_status=res["event_status"], wire_path=str(out / "wire.json"))


if __name__ == "__main__":
    main()
