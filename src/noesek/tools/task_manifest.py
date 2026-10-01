"""Own-code offline team/task manifest from AX/Paperclip/OpenRig patterns.
No orchestration, workers, external communication or spending launched.
"""
from typing import Literal
from pydantic import BaseModel,Field,field_validator

class TaskUnit(BaseModel):
    id:str=Field(min_length=1,max_length=100)
    owner:str=Field(min_length=1,max_length=100)
    dependencies:list[str]=Field(default_factory=list,max_length=100)
    status:Literal['planned','running','paused','done','failed']='planned'
    budget_usd:float=Field(default=0,ge=0,le=100000,allow_inf_nan=False)
    output_ref:str=Field(default='',max_length=2000)
    @field_validator('id','owner')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('nonblank task id/owner required')
        return value.strip()
    @field_validator('dependencies')
    @classmethod
    def refs(cls,value):
        if any(not x.strip() or len(x)>100 for x in value):raise ValueError('invalid dependency')
        return [x.strip() for x in value]

class TaskManifestInput(BaseModel):
    tasks:list[TaskUnit]=Field(min_length=1,max_length=100)
    outbound_network:Literal['denied','approval_required']='denied'

def task_manifest(inp:TaskManifestInput):
    by_id={t.id:t for t in inp.tasks}
    if len(by_id)!=len(inp.tasks):return {'ok':False,'error':'duplicate task ids'}
    missing=sorted({d for t in inp.tasks for d in t.dependencies if d not in by_id})
    if missing:return {'ok':False,'error':'unknown dependencies','missing':missing}
    bad=[t.id for t in inp.tasks if t.status=='done' and not t.output_ref.strip()]
    if bad:return {'ok':False,'error':'done tasks require output references','tasks':bad}
    order=[];remaining=set(by_id)
    while remaining:
        ready=sorted(i for i in remaining if all(d in order for d in by_id[i].dependencies))
        if not ready:return {'ok':False,'error':'dependency cycle','pending':sorted(remaining)}
        order.extend(ready);remaining.difference_update(ready)
    blocked={t.id:[d for d in t.dependencies if by_id[d].status!='done'] for t in inp.tasks}
    return {'ok':True,'order':order,'tasks':[by_id[i].model_dump() for i in order],
            'blocked_dependencies':{i:v for i,v in blocked.items() if v},
            'paused':[i for i in order if by_id[i].status=='paused'],
            'approval_required':[i for i in order if by_id[i].budget_usd>0],
            'outbound_network':inp.outbound_network,'spend_authorized':False,'executed':False,
            'caveat':'Caller-supplied state and references, not verified results. Budget limits and network labels grant no authority. A real executor must enforce isolation, approvals, pause and state transitions.'}
