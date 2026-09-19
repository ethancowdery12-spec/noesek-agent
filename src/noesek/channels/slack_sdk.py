"""Slack channel transport via the pinned slack-sdk (MIT).

Noesek owns policy (authorization gate, approvals); slack-sdk owns request
signing verification and Web API calls. No workspace credentials are embedded:
the bot token and signing secret come from NOESEK_SLACK_BOT_TOKEN /
NOESEK_SLACK_SIGNING_SECRET. The HTTP client is injectable for tests; nothing
here calls Slack without an operator-configured token.
"""
from __future__ import annotations

from slack_sdk.signature import SignatureVerifier
from slack_sdk.web.async_client import AsyncWebClient

from ..config import settings


class SlackTransport:
    def __init__(self, *, bot_token: str | None = None, signing_secret: str | None = None,
                 client: AsyncWebClient | None = None):
        self.bot_token = bot_token if bot_token is not None else getattr(settings, "slack_bot_token", "")
        self.signing_secret = (signing_secret if signing_secret is not None
                               else getattr(settings, "slack_signing_secret", ""))
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.bot_token)

    def verify_request(self, body: bytes, timestamp: str, signature: str) -> bool:
        if not self.signing_secret or not timestamp or not signature:
            return False  # fail closed without a configured secret or headers
        try:
            return SignatureVerifier(self.signing_secret).is_valid(body, timestamp, signature)
        except (ValueError, TypeError):
            return False

    async def send_text(self, channel: str, text: str) -> dict:
        if not self.configured:
            return {"dry_run": True, "channel": channel, "chars": len(text)}
        client = self._client or AsyncWebClient(token=self.bot_token)
        resp = await client.chat_postMessage(channel=channel, text=text)
        return {"sent": True, "ts": resp.get("ts"), "channel": resp.get("channel")}
