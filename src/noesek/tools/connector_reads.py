"""Connector reads as chat-controller tools.

The agent can check the user's Gmail, Calendar, and GitHub mid-conversation,
riding the OAuth grant the chat connected through the computer's OAuth loop.
READ risk only: writes stay endpoint-level until Ethan asks for them.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import connectors
from ..connectors import default_store
from ..connectors import github as ghtool
from ..connectors import google as gtool
from ..db import Conversation, Session

_GRANT_ERRORS = (gtool.GrantMissing, ghtool.GrantMissing)


def _reconnect(connector: str, chat_id: str) -> dict:
    return {"error": f"the {connector} grant expired and could not be refreshed - "
                     "please reconnect (auth-start link again)",
            "connect": f"POST /connectors/{connector}/auth-start with chat_id={chat_id!r}, "
                       "open the returned URL, approve once"}


async def _call_with_refresh(connector: str, chat_id: str, grant: dict, fn, *args):
    """Run fn(access_token, *args); on a rejected grant, try one refresh and retry.
    Returns the fn result, or None when the grant is dead and a reconnect is needed.
    GitHub grants carry no refresh token, so they fall through to None."""
    try:
        return await fn(grant["access_token"], *args)
    except _GRANT_ERRORS:
        fresh = await connectors.refresh_grant(connector, chat_id)
        if not fresh:
            return None
        try:
            return await fn(fresh, *args)
        except _GRANT_ERRORS:
            return None


class ConnectorReadInput(BaseModel):
    max_results: int = Field(default=5, ge=1, le=20)


async def _chat_grant(conversation_id: int, connector: str) -> tuple[str, dict | None]:
    async with Session() as s:
        conv = await s.get(Conversation, conversation_id)
    chat_id = conv.external_user_id if conv else ""
    return chat_id, await default_store().get(connector, chat_id)


def connector_read_handler(conversation_id: int, connector: str, fn):
    async def h(inp: ConnectorReadInput):
        chat_id, grant = await _chat_grant(conversation_id, connector)
        if grant is None:
            return {"error": f"{connector} is not connected for this chat",
                    "connect": f"POST /connectors/{connector}/auth-start with chat_id={chat_id!r}, "
                               "open the returned URL, approve once"}
        items = await _call_with_refresh(connector, chat_id, grant, fn, inp.max_results)
        if items is None:
            return _reconnect(connector, chat_id)
        return {"count": len(items), "items": items}
    return h


def gmail_read_handler(conversation_id: int):
    return connector_read_handler(conversation_id, "google", gtool.list_messages)


def calendar_read_handler(conversation_id: int):
    return connector_read_handler(conversation_id, "google", gtool.list_events)


def github_notifications_handler(conversation_id: int):
    return connector_read_handler(conversation_id, "github", ghtool.list_notifications)


class GmailSendInput(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(default="", max_length=998)
    body: str = Field(min_length=1, max_length=50000)


def gmail_send_handler(conversation_id: int):
    """Send one email via the chat's Google grant. Registered at EXTERNAL
    risk, so the controller's approval contract (digest + 'approve N')
    always gates it before anything leaves the box."""
    async def h(inp: GmailSendInput):
        chat_id, grant = await _chat_grant(conversation_id, "google")
        if grant is None:
            return {"error": "google is not connected for this chat",
                    "connect": f"POST /connectors/google/auth-start with chat_id={chat_id!r}, "
                               "open the returned URL, approve once"}
        sent = await _call_with_refresh("google", chat_id, grant, gtool.send_message,
                                        inp.to, inp.subject, inp.body)
        if sent is None:
            return _reconnect("google", chat_id)
        return {"sent": True, "to": inp.to, "subject": inp.subject, **sent}
    return h
