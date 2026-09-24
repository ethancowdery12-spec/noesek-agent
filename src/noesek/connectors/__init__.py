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
    scope_sep: str = " "  # Strava wants comma-joined scopes; Google/GitHub take spaces

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
            "https://www.googleapis.com/auth/gmail.send",
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
register(Connector(
    name="strava",
    authorize_url="https://www.strava.com/oauth/authorize",
    token_url="https://www.strava.com/oauth/token",
    scopes=("read", "activity:read_all"),
    tools=("fitness",),
    scope_sep=",",
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

    async def put(self, connector: str, chat_id: str, token: str, scopes: tuple[str, ...] = (),
                  refresh_token: str = "", expires_at: int = 0) -> None:
        data = self._load()
        data.setdefault(connector, {})[chat_id] = {
            "access_token": token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "obtained_at": int(time.time()),
            "scopes": list(scopes),
        }
        self._save(data)

    async def get(self, connector: str, chat_id: str) -> dict | None:
        return self._load().get(connector, {}).get(chat_id)

    async def connected_chats(self, connector: str) -> list[str]:
        return sorted(self._load().get(connector, {}))

    async def put_state(self, state: str, connector: str, chat_id: str, redirect_uri: str = "") -> None:
        data = self._load()
        states = data.setdefault("_states", {})
        # drop expired while we are here
        now = int(time.time())
        for k in [k for k, v in states.items() if now - v.get("issued_at", 0) > 3600]:
            del states[k]
        states[state] = {"connector": connector, "chat_id": chat_id,
                         "redirect_uri": redirect_uri, "issued_at": now}
        self._save(data)

    async def pop_state(self, state: str, max_age_seconds: int = 3600) -> dict | None:
        data = self._load()
        states = data.get("_states", {})
        entry = states.get(state)
        if entry is None:
            return None
        if int(time.time()) - entry.get("issued_at", 0) > max_age_seconds:
            return None
        del states[state]
        self._save(data)
        return entry


class ConnectorError(RuntimeError):
    pass


async def exchange_code(connector: Connector, code: str, redirect_uri: str) -> str:
    """Swap an auth code for an access token. Secret comes from env only."""
    import httpx

    secret = os.environ.get(f"NOESEK_CONNECTOR_{connector.name.upper()}_CLIENT_SECRET", "")
    if not connector.client_id() or not secret:
        raise ConnectorError(f"{connector.name}: client id/secret env vars are not set")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(connector.token_url, data={
            "client_id": connector.client_id(),
            "client_secret": secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, headers={"Accept": "application/json"})
    if resp.status_code != 200:
        raise ConnectorError(f"{connector.name}: token exchange failed ({resp.status_code})")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ConnectorError(f"{connector.name}: no access_token in response")
    return {"access_token": token, "refresh_token": data.get("refresh_token", ""),
            "expires_at": int(data.get("expires_at", 0) or 0)}


def build_authorize_url(connector: Connector, chat_id: str, redirect_uri: str) -> tuple[str, str]:
    """(url, state) for Ethan's browser consent; state binds the grant to the chat."""
    state = f"{chat_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": connector.client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": connector.scope_sep.join(connector.scopes),
        "state": state,
        "access_type": "offline",
    }
    return f"{connector.authorize_url}?{urlencode(params)}", state


class DbTokenStore:
    """Database-backed grant/state store. The 0600 JSON file sat on the host
    filesystem, which is ephemeral on Render - every redeploy silently wiped
    each chat's OAuth grants and in-flight states. Rows survive deploys.

    The public async interface matches TokenStore exactly so the file store
    remains a drop-in test double."""

    async def put(self, connector: str, chat_id: str, token: str, scopes: tuple[str, ...] = (),
                  refresh_token: str = "", expires_at: int = 0) -> None:
        from sqlalchemy import select
        from ..db import ConnectorGrant, Session
        async with Session() as s:
            row = (await s.execute(select(ConnectorGrant).where(
                ConnectorGrant.connector == connector,
                ConnectorGrant.chat_id == chat_id))).scalar_one_or_none()
            if row is None:
                s.add(ConnectorGrant(connector=connector, chat_id=chat_id,
                                     access_token=token, refresh_token=refresh_token,
                                     expires_at=expires_at, scopes=list(scopes),
                                     obtained_at=int(time.time())))
            else:
                row.access_token = token
                if refresh_token:
                    row.refresh_token = refresh_token
                row.expires_at = expires_at
                row.scopes = list(scopes)
                row.obtained_at = int(time.time())
            await s.commit()

    async def get(self, connector: str, chat_id: str) -> dict | None:
        from sqlalchemy import select
        from ..db import ConnectorGrant, Session
        async with Session() as s:
            row = (await s.execute(select(ConnectorGrant).where(
                ConnectorGrant.connector == connector,
                ConnectorGrant.chat_id == chat_id))).scalar_one_or_none()
        if row is None:
            return None
        return {"access_token": row.access_token, "refresh_token": row.refresh_token,
                "expires_at": row.expires_at, "obtained_at": row.obtained_at,
                "scopes": list(row.scopes or [])}

    async def connected_chats(self, connector: str) -> list[str]:
        from sqlalchemy import select
        from ..db import ConnectorGrant, Session
        async with Session() as s:
            rows = (await s.execute(select(ConnectorGrant.chat_id).where(
                ConnectorGrant.connector == connector))).scalars().all()
        return sorted(rows)

    async def put_state(self, state: str, connector: str, chat_id: str, redirect_uri: str = "") -> None:
        from sqlalchemy import delete
        from ..db import ConnectorState, Session
        now = int(time.time())
        async with Session() as s:
            await s.execute(delete(ConnectorState).where(
                ConnectorState.issued_at < now - 3600))
            await s.merge(ConnectorState(state=state, connector=connector,
                                         chat_id=chat_id, redirect_uri=redirect_uri,
                                         issued_at=now))
            await s.commit()

    async def pop_state(self, state: str, max_age_seconds: int = 3600) -> dict | None:
        from sqlalchemy import delete
        from ..db import ConnectorState, Session
        async with Session() as s:
            row = await s.get(ConnectorState, state)
            if row is None:
                return None
            entry = {"connector": row.connector, "chat_id": row.chat_id,
                     "redirect_uri": row.redirect_uri, "issued_at": row.issued_at}
            if int(time.time()) - row.issued_at > max_age_seconds:
                return None
            await s.execute(delete(ConnectorState).where(ConnectorState.state == state))
            await s.commit()
        return entry


async def refresh_grant(connector: str, chat_id: str) -> str | None:
    """Swap a stored refresh_token for a fresh access token and persist it.
    Returns the new access token, or None when no usable refresh grant exists."""
    c = get(connector)
    if c is None:
        return None
    grant = await default_store().get(connector, chat_id)
    if not grant or not grant.get("refresh_token"):
        return None
    secret = os.environ.get(f"NOESEK_CONNECTOR_{connector.upper()}_CLIENT_SECRET", "")
    if not c.client_id() or not secret:
        return None
    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(c.token_url, data={
            "client_id": c.client_id(), "client_secret": secret,
            "grant_type": "refresh_token", "refresh_token": grant["refresh_token"],
        }, headers={"Accept": "application/json"})
    if resp.status_code != 200:
        return None
    data = resp.json()
    token = data.get("access_token")
    if not token:
        return None
    await default_store().put(connector, chat_id, token,
                              tuple(grant.get("scopes") or ()),
                              refresh_token=data.get("refresh_token", "") or grant["refresh_token"],
                              expires_at=int(data.get("expires_at", 0) or 0))
    return token


def default_store() -> DbTokenStore:
    return DbTokenStore()
