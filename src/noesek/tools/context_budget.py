"""Own-code session-continuity brief under a hard character budget.
Ideas only from Context-Mode (Elastic License 2.0, which bars copying): keep raw output out of the
conversation, track edits, errors, tasks and decisions as events, and after a compaction bring back
only what is relevant. Stateless here: the caller passes the events; nothing is stored or sent.
Ranking is term overlap plus kind weight plus recency. Exact event text is returned, never a summary.
"""
import re
from typing import Literal
from pydantic import BaseModel,Field
_KIND_WEIGHT={'decision':5,'error':4,'task':4,'edit':3,'command':2,'note':1,'output':0}
_PIN={'decision','task'}
class Event(BaseModel):
    id:str=Field(min_length=1,max_length=60)
    kind:Literal['decision','error','task','edit','command','note','output']
    text:str=Field(min_length=1,max_length=20000)
    resolved:bool=False
class ContextBudgetInput(BaseModel):
    events:list[Event]=Field(min_length=1,max_length=2000)
    query:str=Field(default='',max_length=500)
    budget_chars:int=Field(default=3000,ge=200,le=20000)
    line_chars:int=Field(default=300,ge=40,le=2000)

def _terms(t):return set(re.findall(r'\w+',t.casefold()))

def context_budget(inp):
    ids=[e.id for e in inp.events]
    if len(set(ids))!=len(ids):return {'ok':False,'error':'duplicate event ids'}
    raw=sum(len(e.text) for e in inp.events);want=_terms(inp.query);n=len(inp.events)
    scored=[]
    for i,e in enumerate(inp.events):
        overlap=len(want&_terms(e.text)) if want else 0
        score=overlap*6+_KIND_WEIGHT[e.kind]+i/max(1,n-1)*2-(3 if e.resolved and e.kind=='error' else 0)
        pinned=e.kind in _PIN and not e.resolved
        scored.append((pinned,score,i,e))
    # pinned (open decisions/tasks) first in time order, then the rest by score, all inside the budget
    order=[s for s in scored if s[0]]
    order.sort(key=lambda s:s[2])
    rest=[s for s in scored if not s[0] and (not want or s[1]>=_KIND_WEIGHT[s[3].kind]+0.0)]
    rest.sort(key=lambda s:(-s[1],-s[2]))
    out=[];used=0;clipped=0;dropped=[]
    for _,score,i,e in order+rest:
        text=e.text.strip().replace('\n',' ')
        if len(text)>inp.line_chars:text=text[:inp.line_chars-1]+'…';clipped+=1
        line=f'[{e.id}] {e.kind}: {text}'
        if used+len(line)+1>inp.budget_chars:dropped.append(e.id);continue
        out.append({'id':e.id,'kind':e.kind,'text':text,'clipped':text.endswith('…') and len(e.text.strip())>inp.line_chars,'pinned':_pin(e)});used+=len(line)+1
    brief='\n'.join(f"[{o['id']}] {o['kind']}: {o['text']}" for o in out)
    return {'ok':True,'brief':brief,'events_returned':len(out),'events_total':n,'omitted_ids':dropped[:50],'omitted_count':n-len(out),
            'raw_chars':raw,'brief_chars':len(brief),'saved_ratio':round(1-len(brief)/raw,3) if raw else 0.0,'clipped_lines':clipped,
            'caveat':'Selection by simple ranking, not understanding. Omitted events still exist with the caller; ask for them by id if the brief looks incomplete. Nothing was stored.'}
def _pin(e):return e.kind in _PIN and not e.resolved
