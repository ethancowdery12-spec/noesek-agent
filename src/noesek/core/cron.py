"""Bounded standard five-field cron parser and minute dispatcher."""
from dataclasses import dataclass
from datetime import datetime,timezone

def _field(text,lo,hi):
    out=set()
    for part in text.split(','):
        step=1
        if '/' in part: part,s=part.split('/',1); step=int(s)
        if step<1: raise ValueError("invalid cron step")
        if part=='*': a,b=lo,hi
        elif '-' in part: a,b=map(int,part.split('-',1))
        else: a=b=int(part)
        if a<lo or b>hi or a>b: raise ValueError("cron value out of range")
        out.update(range(a,b+1,step))
    return frozenset(out)
@dataclass(frozen=True)
class CronExpression:
    minute:frozenset; hour:frozenset; day:frozenset; month:frozenset; weekday:frozenset
    @classmethod
    def parse(cls,text):
        p=text.split()
        if len(p)!=5: raise ValueError("cron needs five fields")
        return cls(_field(p[0],0,59),_field(p[1],0,23),_field(p[2],1,31),_field(p[3],1,12),_field(p[4],0,7))
    def matches(self,dt):
        wd=(dt.weekday()+1)%7
        return dt.minute in self.minute and dt.hour in self.hour and dt.day in self.day and dt.month in self.month and (wd in self.weekday or (wd==0 and 7 in self.weekday))
class CronDispatcher:
    def __init__(self): self.last={}
    def due(self,jobs:list[dict],moment:datetime):
        key=moment.astimezone(timezone.utc).replace(second=0,microsecond=0).isoformat(); out=[]
        for j in jobs:
            if j.get("state")=="active" and CronExpression.parse(j["expression"]).matches(moment) and self.last.get(j["job_id"])!=key:
                self.last[j["job_id"]]=key; out.append(j)
        return out
