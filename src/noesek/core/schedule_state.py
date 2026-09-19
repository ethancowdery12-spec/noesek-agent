"""Serializable cron/subscription state with idempotent cleanup."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import re,uuid
_CRON=re.compile(r"^(\*|[0-5]?\d) (\*|(?:[01]?\d|2[0-3])) (\*|(?:[12]?\d|3[01])) (\*|(?:[1-9]|1[0-2])) (\*|[0-7])$")
@dataclass
class CronJob:
    expression:str; payload:dict; job_id:str=""; state:str="active"; last_run_at:str|None=None
    def __post_init__(self):
        if not _CRON.fullmatch(self.expression): raise ValueError("unsupported cron expression")
        if not self.job_id:self.job_id=str(uuid.uuid4())
    def pause(self): self.state="paused"
    def resume(self): self.state="active"
    def mark_run(self,when:datetime): self.last_run_at=when.astimezone(timezone.utc).isoformat()
    def serialize(self): return asdict(self)
@dataclass
class Subscription:
    source:str; filter:dict; subscription_id:str=""; state:str="active"; cursor:str|None=None
    def __post_init__(self):
        if not self.source or not isinstance(self.filter,dict): raise ValueError("source and filter required")
        if not self.subscription_id:self.subscription_id=str(uuid.uuid4())
    def checkpoint(self,cursor): self.cursor=cursor
    def cleanup(self): self.state="closed"
    def resume(self):
        if self.state=="closed": raise ValueError("closed subscriptions cannot resume")
        self.state="active"
    def serialize(self): return asdict(self)
