"""Noesek authorization gate over the vendored upstream gateway authz chain.

Hosts the vendored GatewayAuthorizationMixin (authz_mixin.py), PairingStore
(pairing.py), BotLoopGuard (bot_loop_guard.py), SessionSource (session bridge)
and WhatsApp identity canonicalization (whatsapp_identity.py) without an upstream
GatewayRunner. Noesek is the single orchestrator and configuration owner:
Noesek settings project into the platform env allowlist keys the vendored mixin
reads (upstream's single-profile contract is env-over-config; an env var already
set by the operator always wins), and the pairing store lives under NOESEK_HOME.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from ..vendor.hermes.gateway.authz_mixin import GatewayAuthorizationMixin
from ..vendor.hermes.gateway.config import Platform
from ..vendor.hermes.gateway.pairing import PairingStore
from ..vendor.hermes.gateway.session import SessionSource
from ..vendor.hermes.gateway.whatsapp_identity import (
    canonical_whatsapp_identifier, normalize_whatsapp_identifier, to_whatsapp_jid)
from ..vendor.hermes.hermes_constants import set_hermes_home_override

__all__ = ["NoesekAuthorizationGate", "canonical_whatsapp_identifier",
           "normalize_whatsapp_identifier", "to_whatsapp_jid"]

# Noesek settings -> the env allowlist keys the vendored chain reads.
_PLATFORM_ALLOWLIST_PROJECTION = {"whatsapp": "WHATSAPP_ALLOWED_USERS"}


def default_home() -> Path:
    return Path(os.getenv("NOESEK_HOME", str(Path.home() / ".noesek")))


class NoesekAuthorizationGate(GatewayAuthorizationMixin):
    def __init__(self, *, allowlists: dict[str, str] | None = None,
                 allow_all_users: bool = False,
                 unauthorized_dm_behavior: str = "pair",
                 home: str | Path | None = None):
        home = Path(home) if home else default_home()
        home.mkdir(parents=True, exist_ok=True)
        set_hermes_home_override(home)
        # Project Noesek configuration into the env keys the vendored mixin reads;
        # operator-set env always wins (upstream env-over-config contract).
        for platform, key in _PLATFORM_ALLOWLIST_PROJECTION.items():
            value = (allowlists or {}).get(platform, "")
            if value.strip() and key not in os.environ:
                os.environ[key] = value
        if allow_all_users and "GATEWAY_ALLOW_ALL_USERS" not in os.environ:
            os.environ["GATEWAY_ALLOW_ALL_USERS"] = "true"
        self.config = SimpleNamespace(
            platforms={}, multiplex_profiles=False,
            unauthorized_dm_behavior=unauthorized_dm_behavior)
        self.pairing_store = PairingStore()
        self.pairing_stores: dict = {}
        self.adapters: list = []

    # GatewayRunner hooks the mixin expects; Noesek has no upstream adapters.
    def _primary_adapters(self) -> dict:
        return {}

    def _profile_adapters_map(self) -> dict:
        return {}

    def _authorization_adapter(self, platform, profile=None):
        return None

    def make_source(self, *, platform: str, chat_id: str, user_id: str | None = None,
                    chat_type: str = "dm", user_name: str | None = None,
                    is_bot: bool = False) -> SessionSource:
        return SessionSource(platform=Platform(platform), chat_id=str(chat_id),
                             chat_type=chat_type, user_id=user_id,
                             user_name=user_name, is_bot=is_bot)

    def is_authorized(self, source: SessionSource) -> bool:
        return self._is_user_authorized(source)

    def admit_bot_message(self, source: SessionSource) -> bool:
        return self._admit_bot_message(source)

    def unauthorized_dm_behavior(self, platform: str) -> str:
        return self._get_unauthorized_dm_behavior(Platform(platform))

    # --- pairing lifecycle (operator-approved grants) ---
    def start_pairing(self, platform: str, user_id: str, user_name: str = "") -> str | None:
        return self.pairing_store.generate_code(platform, user_id, user_name)

    def approve_code(self, platform: str, code: str):
        return self.pairing_store.approve_code(platform, code)

    def revoke(self, platform: str, user_id: str) -> bool:
        return self.pairing_store.revoke(platform, user_id)

    def list_approved(self, platform: str | None = None) -> list:
        return self.pairing_store.list_approved(platform)


_GATE = None


def get_gate() -> NoesekAuthorizationGate:
    """Process-wide gate built from Noesek settings (Noesek owns configuration)."""
    global _GATE
    if _GATE is None:
        from ..config import settings
        _GATE = NoesekAuthorizationGate(
            allowlists={"whatsapp": settings.whatsapp_allowed_users},
            allow_all_users=settings.gateway_allow_all_users,
            unauthorized_dm_behavior=settings.unauthorized_dm_behavior)
    return _GATE
