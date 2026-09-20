"""Noesek secrets vault - 0600 JSON store on the VM.

Names are the only thing ever listed or logged. Values are write-only over
the API surface except for an explicit single-name read, and are never
written to logs, errors, or other endpoints.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class VaultError(ValueError):
    """Invalid vault request (bad name, empty value, missing entry)."""


class VaultStore:
    """0600 JSON file: {name: {value, stored_at}}. Values never logged."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    @staticmethod
    def _check_name(name: str) -> str:
        if not _NAME_RE.match(name or ""):
            raise VaultError("invalid secret name")
        return name

    def put(self, name: str, value: str) -> None:
        self._check_name(name)
        if not value:
            raise VaultError("empty value")
        data = self._load()
        data[name] = {"value": value, "stored_at": int(time.time())}
        self._save(data)

    def get(self, name: str) -> dict | None:
        self._check_name(name)
        return self._load().get(name)

    def delete(self, name: str) -> bool:
        self._check_name(name)
        data = self._load()
        if name not in data:
            return False
        del data[name]
        self._save(data)
        return True

    def names(self) -> list[dict]:
        """Names + metadata only. Never values."""
        return [
            {"name": k, "stored_at": v.get("stored_at", 0)}
            for k, v in sorted(self._load().items())
        ]


def default_store() -> VaultStore:
    override = os.environ.get("NOESEK_VAULT_PATH")
    if override:
        return VaultStore(Path(override))
    return VaultStore(Path.home() / ".noesek" / "vault.json")
