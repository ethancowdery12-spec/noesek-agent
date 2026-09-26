"""Obsidian channel: bearer-token store + context folding for the thin plugin client.

The Obsidian plugin is a thin channel client (docs/OBSIDIAN_PLUGIN.md): it pairs
through the existing authorization gate, stores the issued token locally, POSTs
messages with explicit @mentioned vault context, and applies returned edit
proposals locally. The server never holds vault write access.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from gateway.platform_registry import PlatformEntry, platform_registry

from .authorization import default_home

CONTEXT_CAP_CHARS = 50_000

# Register the channel with the vendored platform registry (runtime registration,
# vendored tree untouched) so Platform("obsidian") resolves and the authz gate can
# issue/approve pairing codes for it. Noesek serves the channel itself; there is no
# vendored adapter to construct.
platform_registry.register(PlatformEntry(
    name="obsidian", label="Obsidian",
    adapter_factory=lambda cfg: None,
    check_fn=lambda: True,
    allowed_users_env="OBSIDIAN_ALLOWED_USERS",
    source="plugin"))


class ContextTooLarge(ValueError):
    pass


def fold_context(text: str, context: list[dict]) -> tuple[str, list[str]]:
    """Fold plugin-supplied vault context into the message text with a manifest.

    Each item: {path, content?} for a file, {path, paths: [...]} for a folder
    listing, plus optional selection text. Total folded context is capped at
    CONTEXT_CAP_CHARS; the manifest names exactly what was attached.
    """
    if not context:
        return text, []
    manifest: list[str] = []
    parts: list[str] = []
    for item in context:
        path = str(item.get("path", "")).strip() or "(untitled)"
        content = item.get("content")
        if content is None:
            listed = [str(p) for p in (item.get("paths") or [])]
            manifest.append(f"{path} ({len(listed)} paths listed)")
            parts.append(f"# {path}\n" + "\n".join(listed))
        else:
            body = str(content)
            selection = item.get("selection")
            manifest.append(f"{path} ({len(body)} chars)")
            part = f"# {path}\n{body}"
            if selection:
                part += f"\n\n## selection\n{selection}"
            parts.append(part)
    folded = "\n\n".join(parts)
    if len(folded) > CONTEXT_CAP_CHARS:
        raise ContextTooLarge(f"context {len(folded)} chars over {CONTEXT_CAP_CHARS} cap")
    header = (f"[obsidian context: {len(context)} attachment(s): "
              + ", ".join(manifest) + "]")
    return f"{header}\n\n{folded}\n\n{text}", manifest


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ObsidianTokenStore:
    """Bearer tokens issued after gate pairing approval. Hashed at rest, 0600."""

    def __init__(self, home: str | Path | None = None):
        base = Path(home) if home else default_home()
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "obsidian_tokens.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def issue(self, device_id: str) -> str:
        token = secrets.token_urlsafe(32)
        data = self._load()
        data[_hash(token)] = {"device_id": device_id, "created_at": int(time.time())}
        self._save(data)
        return token

    def validate(self, token: str) -> str | None:
        if not token:
            return None
        entry = self._load().get(_hash(token))
        return entry["device_id"] if entry else None

    def revoke_device(self, device_id: str) -> int:
        data = self._load()
        doomed = [h for h, e in data.items() if e.get("device_id") == device_id]
        for h in doomed:
            del data[h]
        if doomed:
            self._save(data)
        return len(doomed)
