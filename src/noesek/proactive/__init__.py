"""Proactive engine: the computer acts first.

A chat opts in with a goal and an interval; the server sweep wakes due
chats and hands the controller a bounded nudge. The controller either acts
(reply is delivered into the chat) or answers IDLE, which is withheld - a
quiet tick never spams the channel. State lives in a 0600 JSON file so a
VM restart resumes every watch.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

IDLE = "IDLE"
DEFAULT_INTERVAL_SECONDS = 900  # 15 min: light on paid inference


class ProactiveStore:
    """0600 JSON: {chat_id: {active, goal, interval_seconds, next_tick_at}}."""

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

    def activate(self, chat_id: str, goal: str = "", interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> dict:
        data = self._load()
        entry = {
            "active": True,
            "goal": goal,
            "interval_seconds": max(60, int(interval_seconds)),
            "next_tick_at": int(time.time()),  # first tick immediately
        }
        data[chat_id] = entry
        self._save(data)
        return entry

    def pause(self, chat_id: str) -> bool:
        data = self._load()
        entry = data.get(chat_id)
        if entry is None:
            return False
        entry["active"] = False
        self._save(data)
        return True

    def get(self, chat_id: str) -> dict | None:
        return self._load().get(chat_id)

    def all(self) -> dict:
        return self._load()

    def due_chats(self, now: int | None = None) -> list[str]:
        now = now if now is not None else int(time.time())
        return sorted(k for k, v in self._load().items()
                      if v.get("active") and v.get("next_tick_at", 0) <= now)

    def reschedule(self, chat_id: str) -> None:
        data = self._load()
        entry = data.get(chat_id)
        if entry is not None:
            entry["next_tick_at"] = int(time.time()) + entry.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
            self._save(data)


def nudge_text(goal: str) -> str:
    base = ("[proactive tick] You are awake without a user message. "
            "If there is something useful to do or say for this chat, do it. "
            f"Otherwise reply with exactly: {IDLE}")
    return f"{base}\nGoal: {goal}" if goal else base


def default_store() -> ProactiveStore:
    home = Path(os.environ.get("NOESEK_HOME", Path.home() / ".noesek"))
    return ProactiveStore(home / "proactive.json")
