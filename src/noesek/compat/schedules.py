"""Portable interval schedule model used by durable background tasks."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class IntervalSchedule:
    every_seconds: int
    def __post_init__(self):
        if not 60 <= self.every_seconds <= 31_536_000: raise ValueError("interval must be between one minute and one year")
    def next_after(self, moment: datetime) -> datetime:
        if moment.tzinfo is None: moment=moment.replace(tzinfo=timezone.utc)
        return moment + timedelta(seconds=self.every_seconds)
