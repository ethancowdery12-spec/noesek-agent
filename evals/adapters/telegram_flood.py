"""Adapter for upstream evals/delivery_flood_wire.py (Hermes c712f06d).

Upstream intent: flood the delivery path with many inbound updates; every
authorized update must be processed and produce exactly one delivery attempt
through the final-send path, with waits and process ownership real. Noesek
target: POST /webhooks/telegram on the real FastAPI app (ASGI transport,
in-process), the authorization gate, and the telegram send path (dry-run
receipts - no bot token configured, nothing leaves the process).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir


async def go(out):
    import noesek.channels.telegram_router as tr
    from noesek.channels.authorization import get_gate
    from noesek.channels.core_controller import get_controller
    from noesek.core.controller import Controller
    from noesek.db import init_db

    class EchoLLM:
        async def complete(self, messages, schemas):
            class Reply:
                content = "echo: " + str(messages[-1].get("content", ""))
                tool_calls = []
            return Reply()

    await init_db()
    # real pairing persistence: generate + approve a code for the sender
    gate = get_gate()
    code = gate.pairing_store.generate_code("telegram", "7", "Sender Seven")
    assert code and gate.approve_code("telegram", code)
    import noesek.channels.core_controller as cc
    cc._controller = Controller(llm=EchoLLM())

    sends = []
    async def record_send(chat_id, text):
        sends.append({"chat_id": str(chat_id), "text": text})
        return {"dry_run": True}
    tr.send_telegram = record_send

    from httpx import ASGITransport, AsyncClient
    from noesek.main import app
    secret = tr.transport
    headers = {"X-Telegram-Bot-Api-Secret-Token": "adapter-secret"}
    N, DUP = 45, 5
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        statuses = []
        for i in range(N + DUP):
            uid = 1000 + (i % N)  # DUP resend the first update ids
            payload = {"update_id": uid,
                       "message": {"from": {"id": 7}, "chat": {"id": 42},
                                   "text": f"msg {uid}"}}
            r = await client.post("/webhooks/telegram", json=payload, headers=headers)
            statuses.append(r.status_code)
    return {"http_statuses": sorted(set(statuses)), "sends": len(sends),
            "unique_chats": len({s["chat_id"] for s in sends}), "posted": N + DUP}


def main():
    out = out_dir()
    home = out / "home"; home.mkdir()
    import os
    os.environ.update({"NOESEK_HOME": str(home), "HERMES_HOME": str(home),
                       "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{home}/noesek.db",
                       "NOESEK_TELEGRAM_WEBHOOK_SECRET": "adapter-secret"})
    res = asyncio.run(go(out))
    (out / "flood_sends.json").write_text(json.dumps(res, indent=2) + "\n")
    # exactly one delivery per UNIQUE update; duplicate update_ids dedup upstream
    res["deduped"] = res["posted"] - res["sends"]
    ok = res["http_statuses"] == [200] and res["sends"] == 45 and res["deduped"] == 5
    emit("pass" if ok else "fail", **res)


if __name__ == "__main__":
    main()
