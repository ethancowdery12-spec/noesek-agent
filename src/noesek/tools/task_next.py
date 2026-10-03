"""Next-task selection and complexity hints for a dependency-ordered task list, own code.
Ideas only from Task Master (MIT + Commons Clause, so no copying): pick the next ready task by
priority, show what blocks the rest, flag tasks too big to start and suggest splitting them.
Offline. No model call, nothing is run or changed; statuses are caller-supplied claims.
"""
import re
from typing import Literal
from pydantic import BaseModel,Field,field_validator
_PRIORITY={'high':0,'medium':1,'low':2}
_HEAVY=('migrate','migration','integrate','integration','refactor','rewrite','redesign','authentication','payment','encrypt','deploy','infrastructure','schema','concurrency','distributed','multi','backfill','security')
class Item(BaseModel):
    id:str=Field(min_length=1,max_length=60)
    title:str=Field(min_length=1,max_length=200)
    status:Literal['pending','in_progress','done','blocked','deferred','cancelled']='pending'
    priority:Literal['high','medium','low']='medium'
    dependencies:list[str]=Field(default_factory=list,max_length=100)
    description:str=Field(default='',max_length=4000)
    subtasks:list[str]=Field(default_factory=list,max_length=50)
    @field_validator('id')
    @classmethod
    def _id(cls,v):
        if not v.strip():raise ValueError('blank id')
        return v.strip()
class TaskNextInput(BaseModel):
    tasks:list[Item]=Field(min_length=1,max_length=1000)
    split_threshold:int=Field(default=7,ge=2,le=10)

def complexity(t):
    text=(t.title+' '+t.description).lower();words=len(text.split())
    score=1+min(3,words//40)+min(3,len(t.dependencies))+min(2,sum(1 for h in _HEAVY if h in text))
    score+=1 if len(re.findall(r'\b(and|then|also|plus)\b',text))>=4 else 0
    return max(1,min(10,score-(1 if t.subtasks and len(t.subtasks)>=3 else 0)))

def task_next(inp):
    by={};
    for t in inp.tasks:
        if t.id in by:return {'ok':False,'error':'duplicate task id','id':t.id}
        by[t.id]=t
    missing={t.id:[d for d in t.dependencies if d not in by] for t in inp.tasks}
    missing={k:v for k,v in missing.items() if v}
    if missing:return {'ok':False,'error':'unknown dependencies','missing':missing}
    if any(t.id in t.dependencies for t in inp.tasks):return {'ok':False,'error':'task depends on itself'}
    # cycle check by repeated peeling
    left=set(by);order=[]
    while left:
        ready=sorted(i for i in left if all(d in order or d not in left for d in by[i].dependencies))
        if not ready:return {'ok':False,'error':'dependency cycle','pending':sorted(left)}
        order.extend(ready);left.difference_update(ready)
    finished={'done','cancelled'}
    dependents={i:0 for i in by}
    for t in inp.tasks:
        for d in t.dependencies:dependents[d]+=1
    ready=[];blocked={}
    for t in inp.tasks:
        if t.status in finished or t.status=='deferred':continue
        waiting=[d for d in t.dependencies if by[d].status not in finished]
        if t.status=='blocked':blocked[t.id]=['marked blocked by caller']+[f'waiting on {d}' for d in waiting]
        elif waiting:blocked[t.id]=[f'waiting on {d}' for d in waiting]
        else:ready.append(t)
    ready.sort(key=lambda t:(0 if t.status=='in_progress' else 1,_PRIORITY[t.priority],-dependents[t.id],len(t.dependencies),t.id))
    scored={t.id:complexity(t) for t in inp.tasks if t.status not in finished}
    big=sorted(i for i,s in scored.items() if s>=inp.split_threshold and not by[i].subtasks)
    total=len(inp.tasks);done=sum(1 for t in inp.tasks if t.status=='done')
    return {'ok':True,'next':ready[0].id if ready else None,'ready':[t.id for t in ready],'blocked':blocked,
            'complexity':scored,'suggest_split':big,'progress':{'done':done,'total':total,'percent':round(100*done/total,1)},
            'all_done':all(t.status in finished for t in inp.tasks),
            'why_next':(f'{ready[0].status}, priority {ready[0].priority}, unblocks {dependents[ready[0].id]} task(s)' if ready else 'nothing ready'),
            'caveat':'Selection from caller-supplied statuses and a keyword/size heuristic for complexity. It does not run, verify or schedule any work.'}
