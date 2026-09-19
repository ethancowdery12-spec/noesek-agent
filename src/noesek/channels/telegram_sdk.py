"""Telegram channel transport via the pinned aiogram SDK (MIT).

Noesek owns policy; aiogram owns the Bot API calls. Webhook authenticity uses
Telegram's secret-token header (constant-time compare); the bot token and
webhook secret come from NOESEK_TELEGRAM_BOT_TOKEN / NOESEK_TELEGRAM_WEBHOOK_SECRET.
The Bot instance is injectable for tests; nothing calls Telegram without an
operator-configured token.
"""
from __future__ import annotations

import hmac

from ..config import settings


class TelegramTransport:
    def __init__(self, *, bot_token: str | None = None, webhook_secret: str | None = None,
                 bot=None):
        self.bot_token = bot_token if bot_token is not None else settings.telegram_bot_token
        self.webhook_secret = (webhook_secret if webhook_secret is not None
                               else getattr(settings, "telegram_webhook_secret", ""))
        self._bot = bot

    @property
    def configured(self) -> bool:
        return bool(self.bot_token)

    def verify_webhook(self, secret_token_header: str | None) -> bool:
        """Constant-time check of Telegram's X-Telegram-Bot-Api-Secret-Token header."""
        if not self.webhook_secret:
            return False  # fail closed without a configured secret
        return hmac.compare_digest(secret_token_header or "", self.webhook_secret)

    async def send_text(self, chat_id: int | str, text: str) -> dict:
        if not self.configured:
            return {"dry_run": True, "chat_id": str(chat_id), "chars": len(text)}
        bot = self._bot
        if bot is None:
            from aiogram import Bot
            bot = Bot(token=self.bot_token)
        msg = await bot.send_message(chat_id=chat_id, text=text)
        return {"sent": True, "message_id": getattr(msg, "message_id", None),
                "chat_id": str(chat_id)}
