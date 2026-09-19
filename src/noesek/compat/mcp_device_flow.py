"""RFC 8628 device authorization grant for MCP servers that require it.

- Tokens live in an injected TokenStore (default: 0600 files under
  NOESEK_HOME/tokens); the client never logs or returns raw tokens.
- Polling honors the server-provided interval, slow_down (+5s per RFC 8628
  section 3.5), and the device code's expires_in deadline.
- Status surfaces are redacted: a sha256 prefix reference, never the secret.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class DeviceFlowError(RuntimeError):
    """Raised on terminal device-flow failures. Never carries secret material."""


def redact(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()[:12]


class FileTokenStore:
    """0600-permission JSON token files; the operator may swap in a vault-backed
    implementation with the same interface."""

    def __init__(self, directory: Path | None = None):
        root = directory or Path(os.environ.get("NOESEK_HOME", Path.home() / ".noesek")) / "tokens"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.dir = root

    def _path(self, ref: str) -> Path:
        safe = "".join(c for c in ref if c.isalnum() or c in "-_.")
        return self.dir / f"{safe}.json"

    def put(self, ref: str, token_response: dict) -> None:
        p = self._path(ref)
        p.write_text(json.dumps(token_response))
        p.chmod(0o600)

    def get(self, ref: str) -> dict | None:
        p = self._path(ref)
        return json.loads(p.read_text()) if p.exists() else None

    def delete(self, ref: str) -> bool:
        p = self._path(ref)
        if p.exists():
            p.unlink(); return True
        return False

    def status(self, ref: str) -> dict:
        """Redacted view: never includes access/refresh token values."""
        data = self.get(ref)
        if not data:
            return {"ref": ref, "present": False}
        out = {"ref": ref, "present": True}
        if "access_token" in data:
            out["access_token"] = redact(data["access_token"])
        if "refresh_token" in data:
            out["refresh_token"] = redact(data["refresh_token"])
        for k in ("token_type", "expires_in", "scope", "obtained_at"):
            if k in data:
                out[k] = data[k]
        return out


@dataclass
class DeviceFlowConfig:
    device_authorization_url: str
    token_url: str
    client_id: str
    scopes: list[str] = field(default_factory=list)
    timeout: float = 30.0


class DeviceFlowClient:
    def __init__(self, config: DeviceFlowConfig, store: FileTokenStore,
                 http: httpx.AsyncClient | None = None):
        self.config, self.store, self._http = config, store, http
        self._device_code: str | None = None  # private; never logged or returned

    async def _post(self, url: str, data: dict) -> tuple[int, dict]:
        if self._http is not None:
            r = await self._http.post(url, data=data)
        else:
            async with httpx.AsyncClient(timeout=self.config.timeout) as c:
                r = await c.post(url, data=data)
        try:
            return r.status_code, r.json()
        except json.JSONDecodeError:
            return r.status_code, {}

    async def begin(self) -> dict:
        """Request a device code. Returns only user-safe fields."""
        status, body = await self._post(self.config.device_authorization_url, {
            "client_id": self.config.client_id,
            "scope": " ".join(self.config.scopes)})
        if status != 200 or "device_code" not in body:
            raise DeviceFlowError(f"device authorization request failed (HTTP {status})")
        self._device_code = body["device_code"]
        self._interval = body.get("interval", 5)
        self._deadline = time.monotonic() + body.get("expires_in", 900)
        return {"user_code": body.get("user_code"),
                "verification_uri": body.get("verification_uri"),
                "expires_in": body.get("expires_in", 900),
                "interval": self._interval}

    async def complete(self, token_ref: str) -> dict:
        """Poll until approval, denial, or expiry. Returns REDACTED status."""
        if not self._device_code:
            raise DeviceFlowError("begin() must be called first")
        interval = self._interval
        while time.monotonic() < self._deadline:
            await self._sleep(interval)
            status, body = await self._post(self.config.token_url, {
                "grant_type": DEVICE_GRANT, "device_code": self._device_code,
                "client_id": self.config.client_id})
            if status == 200 and "access_token" in body:
                body["obtained_at"] = time.time()
                self.store.put(token_ref, body)
                self._device_code = None
                return self.store.status(token_ref)
            error = body.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5  # RFC 8628 section 3.5
                continue
            if error in ("access_denied", "expired_token"):
                self._device_code = None
                raise DeviceFlowError(f"device flow terminated: {error}")
            raise DeviceFlowError(f"token endpoint returned HTTP {status}")
        self._device_code = None
        raise DeviceFlowError("device flow terminated: expired_token")

    async def _sleep(self, seconds: float) -> None:
        import asyncio
        await asyncio.sleep(max(0.0, seconds))


def attach_device_flow(client, flow: DeviceFlowClient, token_ref: str, status: dict) -> None:
    """Give an MCPClient a stored bearer token without exposing it to callers."""
    token = flow.store.get(token_ref)
    if token and "access_token" in token:
        client.headers["Authorization"] = f"Bearer {token['access_token']}"
