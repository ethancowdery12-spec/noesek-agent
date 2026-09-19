"""Telegram transport: webhook secret check and send path via aiogram Bot."""
from noesek.channels.telegram_sdk import TelegramTransport


def test_webhook_secret_constant_time_check():
    t = TelegramTransport(bot_token="", webhook_secret="s3cret")
    assert t.verify_webhook("s3cret") is True
    assert t.verify_webhook("wrong") is False
    assert t.verify_webhook(None) is False


def test_missing_secret_fails_closed():
    t = TelegramTransport(bot_token="123:abc", webhook_secret="")
    assert t.verify_webhook("s3cret") is False


async def test_send_without_token_is_dry_run():
    t = TelegramTransport(bot_token="", webhook_secret="x")
    out = await t.send_text(42, "hello")
    assert out == {"dry_run": True, "chat_id": "42", "chars": 5}


async def test_send_with_injected_bot():
    class Msg:
        message_id = 777

    class FakeBot:
        async def send_message(self, chat_id, text):
            assert text == "hello"
            return Msg()

    t = TelegramTransport(bot_token="123:abc", webhook_secret="x", bot=FakeBot())
    out = await t.send_text(42, "hello")
    assert out == {"sent": True, "message_id": 777, "chat_id": "42"}
