"""Slack transport: signature verification (real slack-sdk) and send path."""
import hashlib
import hmac
import time

from noesek.channels.slack_sdk import SlackTransport

SECRET = "test-signing-secret"


def sign(body: bytes) -> tuple[str, str]:
    ts = str(int(time.time()))
    base = b"v0:" + ts.encode() + b":" + body
    return ts, "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    t = SlackTransport(bot_token="", signing_secret=SECRET)
    body = b'{"type":"event_callback"}'
    ts, sig = sign(body)
    assert t.verify_request(body, ts, sig) is True


def test_forged_signature_rejected():
    t = SlackTransport(bot_token="", signing_secret=SECRET)
    ts, _ = sign(b'{"a":1}')
    assert t.verify_request(b'{"a":2}', ts, "v0=" + "0" * 64) is False


def test_missing_signing_secret_fails_closed():
    t = SlackTransport(bot_token="x", signing_secret="")
    body = b"{}"
    ts, sig = sign(body)
    assert t.verify_request(body, ts, sig) is False


async def test_send_without_token_is_dry_run():
    t = SlackTransport(bot_token="", signing_secret=SECRET)
    out = await t.send_text("C123", "hello")
    assert out == {"dry_run": True, "channel": "C123", "chars": 5}


async def test_send_with_injected_client():
    class FakeResponse(dict):
        pass

    class FakeClient:
        async def chat_postMessage(self, channel, text):
            return FakeResponse(ts="1726.1", channel=channel)

    t = SlackTransport(bot_token="xoxb-test", signing_secret=SECRET, client=FakeClient())
    out = await t.send_text("C123", "hello")
    assert out == {"sent": True, "ts": "1726.1", "channel": "C123"}
