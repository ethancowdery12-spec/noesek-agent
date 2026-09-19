from typing import Any, Awaitable, Callable
from ..db import Conversation

Sender = Callable[[str, str], Awaitable[Any]]  # (external_user_id, text)

_senders: dict[str, Sender] = {}

def register(channel: str, sender: Sender):
    _senders[channel] = sender

async def deliver(conversation: Conversation, text: str):
    sender = _senders.get(conversation.channel)
    if sender: await sender(conversation.external_user_id, text)
