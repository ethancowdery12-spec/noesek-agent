"""Adapter for upstream evals/webhook_auth/standard_webhooks_ab.py (Hermes c712f06d).

Upstream intent: webhook authentication A/B - correctly signed requests pass,
tampered/unsigned requests fail closed. Deviation: upstream measures the
Standard Webhooks (svix) scheme; Noesek implements provider-native schemes
(Slack v0 HMAC, Telegram secret token), so this adapter proves the same
accept/reject matrix against Noesek's real routers over ASGI.
"""
import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir

SECRET = "adapter-signing-secret"


async def go():
    from httpx import ASGITransport, AsyncClient
    from noesek.db import init_db
    from noesek.main import app

    await init_db()

    def sign(body: bytes):
        ts = str(int(time.time()))
        return ts, "v0=" + hmac.new(SECRET.encode(), b"v0:" + ts.encode() + b":" + body,
                                    hashlib.sha256).hexdigest()

    cases = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        good = json.dumps({"type": "url_verification", "challenge": "c"}).encode()
        ts, sig = sign(good)
        cases["slack_valid"] = (await client.post("/webhooks/slack", content=good, headers={
            "X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig})).status_code
        ts, sig = sign(good)
        cases["slack_tampered"] = (await client.post(
            "/webhooks/slack", content=good.replace(b'"c"', b'"evil"'), headers={
                "X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig})).status_code
        cases["slack_missing_headers"] = (await client.post(
            "/webhooks/slack", content=good)).status_code
        tg = {"update_id": 1, "message": {"from": {"id": 1}, "chat": {"id": 1}, "text": "x"}}
        cases["telegram_valid"] = (await client.post("/webhooks/telegram", json=tg, headers={
            "X-Telegram-Bot-Api-Secret-Token": "tg-secret"})).status_code
        cases["telegram_wrong_secret"] = (await client.post("/webhooks/telegram", json=tg, headers={
            "X-Telegram-Bot-Api-Secret-Token": "wrong"})).status_code
        cases["telegram_missing"] = (await client.post("/webhooks/telegram", json=tg)).status_code
    return cases


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    import os
    os.environ.update({"NOESEK_HOME": str(home), "HERMES_HOME": str(home),
                       "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{home}/noesek.db",
                       "NOESEK_SLACK_SIGNING_SECRET": SECRET,
                       "NOESEK_TELEGRAM_WEBHOOK_SECRET": "tg-secret"})
    cases = asyncio.run(go())
    expect = {"slack_valid": 200, "slack_tampered": 401, "slack_missing_headers": 401,
              "telegram_valid": 200, "telegram_wrong_secret": 401, "telegram_missing": 401}
    ok = cases == expect
    (out / "auth_matrix.json").write_text(json.dumps({"expect": expect, "got": cases}, indent=2))
    emit("pass" if ok else "fail", cases=cases,
         deviation="provider-native schemes (Slack v0 HMAC, Telegram secret token) instead of svix")


if __name__ == "__main__":
    main()
