"""Real skills backend: the vendored Hermes skill system behind Noesek's home policy.

The vendored tools/skills_tool stack (MIT, Nous Research) provides discovery,
viewing, linting, provenance, usage tracking, and safety scanning. Noesek's
home override scopes everything under the Noesek data dir.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..core.cron_store import CronLedger


class SkillStore:
    """Hermes-backed skill registry rooted at the Noesek home's skills/ dir."""

    def __init__(self, home: str | Path | None = None):
        self.ledger = CronLedger(home)
        (self.ledger.home / "skills").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def list(category: str | None = None) -> list[dict]:
        from ..vendor.hermes.tools import skills_tool
        result = json.loads(skills_tool.skills_list(category=category))
        if not result.get("success"):
            raise RuntimeError(result.get("error", "skills_list failed"))
        return result.get("skills", [])

    @staticmethod
    def view(name: str) -> dict:
        from ..vendor.hermes.tools import skills_tool
        result = skills_tool.skill_view(name)
        result = json.loads(result) if isinstance(result, str) else result
        if isinstance(result, dict) and not result.get("success", True):
            raise RuntimeError(result.get("error", "skill_view failed"))
        return result

    @staticmethod
    def check() -> bool:
        from ..vendor.hermes.tools import skills_tool
        return bool(skills_tool.check_skills_requirements())
