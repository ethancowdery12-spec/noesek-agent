"""Connector framework: OAuth-capable tool providers for the Noesek computer.

A connector is metadata + a token store. Ethan registers OAuth apps himself
(Google, GitHub, ...); the VM never ships client secrets - client IDs come
from env (NOESEK_CONNECTOR_<NAME>_CLIENT_ID) and tokens live in a 0600 JSON
file under NOESEK_HOME, keyed by connector + chat_id so each messaging chat
carries its own grants. v4.1 wires real tool surfaces on top of these grants.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode


@dataclass(frozen=True)
class Connector:
    name: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    tools: tuple[str, ...] = field(default=())

    def client_id(self) -> str:
        return os.environ.get(f"NOESEK_CONNECTOR_{self.name.upper()}_CLIENT_ID", "")


_REGISTRY: dict[str, Connector] = {}


def register(connector: Connector) -> Connector:
    _REGISTRY[connector.name] = connector
    return connector


def all_connectors() -> list[Connector]:
    return sorted(_REGISTRY.values(), key=lambda c: c.name)


def get(name: str) -> Connector | None:
    return _REGISTRY.get(name)


# Built-in definitions: endpoints and scopes only, no secrets.
register(Connector(
    name="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=("https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly"),
    tools=("gmail", "calendar"),
))
register(Connector(
    name="github",
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    scopes=("repo", "read:user"),
    tools=("github",),
))


class TokenStore:
    """0600 JSON file: {connector: {chat_id: {access_token, obtained_at, scopes}}}."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n")
        os.chmod(self.path, 0o600)

    def put(self, connector: str, chat_id: str, token: str, scopes: tuple[str, ...] = ()) -> None:
        data = self._load()
        data.setdefault(connector, {})[chat_id] = {
            "access_token": token,
            "obtained_at": int(time.time()),
            "scopes": list(scopes),
        }
        self._save(data)

    def get(self, connector: str, chat_id: str) -> dict | None:
        return self._load().get(connector, {}).get(chat_id)

    def connected_chats(self, connector: str) -> list[str]:
        return sorted(self._load().get(connector, {}))


def build_authorize_url(connector: Connector, chat_id: str, redirect_uri: str) -> tuple[str, str]:
    """(url, state) for Ethan's browser consent; state binds the grant to the chat."""
    state = f"{chat_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": connector.client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(connector.scopes),
        "state": state,
        "access_type": "offline",
    }
    return f"{connector.authorize_url}?{urlencode(params)}", state


def default_store() -> TokenStore:
    home = Path(os.environ.get("NOESEK_HOME", Path.home() / ".noesek"))
    return TokenStore(home / "connectors.json")
