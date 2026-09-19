"""Real plugin registry over the vendored Hermes plugin loader.

Discovery is rooted at the Noesek home's plugins/ dir (via the vendored home
override). Loading executes plugin code, so this adapter exposes discovery and
description only; code execution stays behind Noesek's approval gates and is a
deliberate later step (see BUILD_REPORT_V1.3.md ledger).
"""
from __future__ import annotations

from pathlib import Path

from ..core.cron_store import CronLedger


class PluginRegistry:
    def __init__(self, home: str | Path | None = None):
        self.ledger = CronLedger(home)
        (self.ledger.home / "plugins").mkdir(parents=True, exist_ok=True)

    def plugins_dir(self) -> Path | None:
        from ..vendor.hermes.plugins import plugin_loader
        return plugin_loader.user_plugins_dir()

    def discover(self) -> list[dict]:
        from ..vendor.hermes.plugins import plugin_loader
        root = self.plugins_dir()
        if root is None:
            return []
        out = []
        for d in plugin_loader.iter_plugin_dirs(root):
            out.append({"name": d.name, "path": str(d),
                        "description": plugin_loader.read_plugin_description(d)})
        return sorted(out, key=lambda p: p["name"])
