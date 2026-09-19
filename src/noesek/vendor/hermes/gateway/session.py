"""Noesek-authored bridge (NOT upstream Hermes source).

Verbatim port of gateway/session.py's ``_CHAT_TYPE_PREFIX`` and ``SessionSource``
(upstream lines 60-161) at the pinned Hermes commit; the rest of upstream
session.py (SessionStore persistence/recovery/lifecycle/transcript mixins) is
not vendored - Noesek's SQL conversation store owns sessions. See VENDORING.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .config import Platform

_CHAT_TYPE_PREFIX = {"group": "group: ", "channel": "channel: "}


@dataclass
class SessionSource:
    """Where a message originated: routes responses, feeds the system-prompt
    context block, and records origin for cron delivery."""
    platform: Platform
    chat_id: str
    chat_name: Optional[str] = None
    chat_type: str = "dm"  # "dm", "group", "channel", "thread"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    thread_id: Optional[str] = None  # forum topics, Discord threads, etc.
    chat_topic: Optional[str] = None  # channel topic/description (Discord, Slack)
    user_id_alt: Optional[str] = None  # platform-specific stable alt ID (Signal UUID, Feishu union_id)
    chat_id_alt: Optional[str] = None  # Signal group internal ID
    is_bot: bool = False  # message author is a bot/webhook (Discord)
    # Platform-neutral SCOPE discriminator (Discord guild / Slack workspace / Matrix server) driving
    # isolation. ``guild_id`` is a deprecated alias: both written, ``scope_id`` wins on read.
    scope_id: Optional[str] = None
    guild_id: Optional[str] = None
    parent_chat_id: Optional[str] = None  # parent channel when chat_id is a thread
    message_id: Optional[str] = None  # triggering message (pin/reply/react)
    role_authorized: bool = False  # adapter granted access via role, not user ID
    # Multiplex profile this message routes to (None => active/default); namespaces the key.
    profile: Optional[str] = None
    # Transport-local fail-closed signal: explicit profile route whose target is not served.
    profile_route_rejected: bool = field(default=False, repr=False, compare=False)
    # Discord auto-thread metadata: explicit so pre-existing/renamed threads are never renamed.
    auto_thread_created: bool = False
    auto_thread_initial_name: Optional[str] = None
    # Discord auto-thread continuity: the thread id a CHANNEL message WILL be delivered into, so
    # the initiating message and later in-thread follow-ups share ONE session.
    prospective_thread_id: Optional[str] = None
    # Wire-INVISIBLE trust signal (never in to_dict/from_dict, so a peer cannot forge it): came
    # over the authenticated relay WebSocket. ``platform`` is the UNDERLYING platform, not
    # ``relay``, so authz must key upstream trust off THIS flag.
    delivered_via_upstream_relay: bool = False

    def __post_init__(self) -> None:
        # Mirror scope_id/guild_id onto each other (scope_id wins) so readers of EITHER agree.
        if self.scope_id is None and self.guild_id is not None:
            self.scope_id = self.guild_id
        elif self.scope_id is not None:
            self.guild_id = self.scope_id

    @staticmethod
    def _describe(chat_type: str, user_label: str, chat_label: str) -> str:
        if chat_type == "dm":
            return f"DM with {user_label}"
        return f"{_CHAT_TYPE_PREFIX.get(chat_type, '')}{chat_label}"

    @property
    def description(self) -> str:
        """Human-readable description of the source."""
        if self.platform == Platform.LOCAL:
            return "CLI terminal"
        user, chat = self.user_name or self.user_id or "user", self.chat_name or self.chat_id
        desc = self._describe(self.chat_type, user, chat)
        return f"{desc}, thread: {self.thread_id}" if self.thread_id else desc

    # Wire layout (order matters for byte-stable JSON): always-present, then truthy-only
    # optionals around the dual-written scope pair.
    _ALWAYS_FIELDS = ("chat_id", "chat_name", "chat_type", "user_id", "user_name", "thread_id", "chat_topic")
    _OPTIONAL_PRE_SCOPE = ("user_id_alt", "chat_id_alt")
    _OPTIONAL_POST_SCOPE = ("parent_chat_id", "message_id", "profile")
    _OPTIONAL_TAIL = ("auto_thread_initial_name", "prospective_thread_id")

    def to_dict(self) -> Dict[str, Any]:
        d = {"platform": self.platform.value}
        d.update((name, getattr(self, name)) for name in self._ALWAYS_FIELDS)

        def _optional(names) -> None:
            d.update((name, v) for name in names if (v := getattr(self, name)))

        _optional(self._OPTIONAL_PRE_SCOPE)
        # Dual-write scope_id + deprecated guild_id alias during the migration.
        scope = self.scope_id if self.scope_id is not None else self.guild_id
        if scope:
            d["scope_id"] = d["guild_id"] = scope
        _optional(self._OPTIONAL_POST_SCOPE)
        if self.auto_thread_created:
            d["auto_thread_created"] = True
        _optional(self._OPTIONAL_TAIL)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSource":
        plain = {
            name: data.get(name)
            for name in cls._ALWAYS_FIELDS[1:] + cls._OPTIONAL_PRE_SCOPE + cls._OPTIONAL_POST_SCOPE + cls._OPTIONAL_TAIL
            if name != "chat_type"
        }
        return cls(
            platform=Platform(data["platform"]), chat_id=str(data["chat_id"]),
            chat_type=data.get("chat_type", "dm"),
            scope_id=data.get("scope_id", data.get("guild_id")),
            auto_thread_created=bool(data.get("auto_thread_created", False)), **plain,
        )


