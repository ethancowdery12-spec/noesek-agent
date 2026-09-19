"""Telegram sidecar process: runs aiogram in its OWN environment.

aiogram caps pydantic below Noesek's exact pin, so the bot lives outside the
core dependency graph. Deploy with a separate venv: pip install aiogram==3.24.0
and forward inbound updates to Noesek's webhook endpoint over localhost.
Noesek remains the policy owner (authorization gate, approvals); this process
is transport only.
"""
import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
NOESEK_FORWARD_URL = os.getenv("NOESEK_TELEGRAM_FORWARD_URL", "http://127.0.0.1:8000/webhooks/telegram")


async def main():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required in the sidecar environment")
    from aiogram import Bot, Dispatcher
    from aiogram.types import Message
    import httpx

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.message()
    async def forward(message: Message):
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(NOESEK_FORWARD_URL, json={
                "chat_id": message.chat.id, "user_id": message.from_user.id if message.from_user else None,
                "text": message.text or "", "message_id": message.message_id,
            })

    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
