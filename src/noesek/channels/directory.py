"""Real channel directory over the vendored upstream gateway channel directory.

The directory maps known channels to names/types from durable session history
and platform adapters; platform adapters that need live services simply yield
nothing when those services are absent.
"""
from __future__ import annotations

from ..core.cron_store import CronLedger


class ChannelDirectory:
    def __init__(self, home=None):
        self.ledger = CronLedger(home)

    @staticmethod
    def load() -> dict:
        from gateway import channel_directory
        return channel_directory.load_directory()

    @staticmethod
    def resolve(platform: str, name: str) -> str | None:
        from gateway import channel_directory
        return channel_directory.resolve_channel_name(platform, name)

    @staticmethod
    def channel_type(platform: str, chat_id: str) -> str | None:
        from gateway import channel_directory
        return channel_directory.lookup_channel_type(platform, chat_id)

    @staticmethod
    def display() -> str:
        from gateway import channel_directory
        return channel_directory.format_directory_for_display()
