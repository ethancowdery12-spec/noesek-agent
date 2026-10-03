"""Offline multi-node placement planner for agent tasks, own code.
Ideas from google/ax (Apache-2.0): declarative Task/Workspace/Model resources, DNS-label names,
namespaces ("atespace"), CPU/memory requests and limits, several workspaces per task with unique
mount paths. Nothing here talks to a cluster, starts a worker or spends money: it validates a
declared fleet, orders tasks by dependency, packs them onto declared nodes and can export
ax.io/v1alpha1 manifests for an operator who runs AX themselves. No AX source is copied.
"""
import json
import math
import re
from typing import Literal
from pydantic import BaseModel,Field,field_validator,model_validator
_LABEL=re.compile(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
_CPU=re.compile(r'^(\d+(?:\.\d+)?)(m?)$')
_MEM=re.compile(r'^(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|K|M|G|T)?$')
_MEM_MULT={None:1,'Ki':2**10,'Mi':2**20,'Gi':2**30,'Ti':2**40,'K':10**3,'M':10**6,'G':10**9,'T':10**12}

def cpu_millis(value):
    m=_CPU.match(str(value).strip())
    if not m:raise ValueError(f'bad cpu quantity {value!r}; use 2, 0.5 or 500m')
    n=float(m.group(1))*(1 if m.group(2) else 1000)
    if n<=0 or n>1_000_000:raise ValueError('cpu must be positive and under 1000 cores')
    return int(round(n))
def mem_bytes(value):
    m=_MEM.match(str(value).strip())
    if not m:raise ValueError(f'bad memory quantity {value!r}; use 512Mi, 4Gi or 2G')
    n=float(m.group(1))*_MEM_MULT[m.group(2)]
    if n<=0 or n>2**50:raise ValueError('memory must be positive and under 1 PiB')
    return int(n)
def _label(value,what):
    if not isinstance(value,str) or len(value)>63 or not _LABEL.match(value):
        raise ValueError(f'{what} must be a lowercase DNS label (max 63 chars, a-z 0-9 and -)')
    return value

class Node(BaseModel):
    name:str
    cpu:str|int|float
    memory:str
    labels:dict[str,str]=Field(default_factory=dict,max_length=20)
    max_tasks:int=Field(default=110,ge=1,le=10000)
    @field_validator('name')
    @classmethod
    def _n(cls,v):return _label(v,'node name')
    @model_validator(mode='after')
    def _q(self):
        cpu_millis(self.cpu);mem_bytes(self.memory);return self

class WorkspaceRef(BaseModel):
    name:str
    path:str=Field(default='',max_length=200)
    goal:str=Field(default='',max_length=1000)
    @field_validator('name')
    @classmethod
    def _n(cls,v):return _label(v,'workspace name')
    @field_validator('path')
    @classmethod
    def _p(cls,v):
        if v and (not v.startswith('/') or '..' in v.split('/')):raise ValueError('workspace path must be absolute without ..')
        return v

class GitSource(BaseModel):
    repo:str=Field(max_length=500)
    branch:str=Field(default='',max_length=200)
    @field_validator('repo')
    @classmethod
    def _r(cls,v):
        if not re.match(r'^https://[^\s/@]+/[^\s@]+$',v):raise ValueError('repo must be a plain https URL without credentials')
        return v

class Workspace(BaseModel):
    name:str
    git:list[GitSource]=Field(default_factory=list,max_length=20)
    files:dict[str,str]=Field(default_factory=dict,max_length=50)
    @field_validator('name')
    @classmethod
    def _n(cls,v):return _label(v,'workspace name')

class Task(BaseModel):
    name:str
    atespace:str='default'
    image:str=Field(default='',max_length=300)
    cpu_request:str|int|float='500m'
    memory_request:str='1Gi'
    cpu_limit:str|int|float|None=None
    memory_limit:str|None=None
    workspaces:list[WorkspaceRef]=Field(default_factory=list,max_length=20)
    depends_on:list[str]=Field(default_factory=list,max_length=100)
    node_selector:dict[str,str]=Field(default_factory=dict,max_length=20)
    priority:int=Field(default=0,ge=-1000,le=1000)
    budget_usd:float=Field(default=0,ge=0,le=100000,allow_inf_nan=False)
    @field_validator('name')
    @classmethod
    def _n(cls,v):return _label(v,'task name')
    @field_validator('atespace')
    @classmethod
    def _a(cls,v):return _label(v,'atespace')
    @model_validator(mode='after')
    def _q(self):
        req=(cpu_millis(self.cpu_request),mem_bytes(self.memory_request))
        if self.cpu_limit is not None and cpu_millis(self.cpu_limit)<req[0]:raise ValueError('cpu_limit below cpu_request')
        if self.memory_limit is not None and mem_bytes(self.memory_limit)<req[1]:raise ValueError('memory_limit below memory_request')
        return self

class ClusterPlanInput(BaseModel):
    nodes:list[Node]=Field(min_length=1,max_length=200)
    tasks:list[Task]=Field(min_length=1,max_length=1000)
    workspaces:list[Workspace]=Field(default_factory=list,max_length=200)
    strategy:Literal['spread','pack']='spread'
    export_ax:bool=False

def _key(t):return f'{t.atespace}/{t.name}'

def cluster_plan(inp):
    nodes={n.name:n for n in inp.nodes}
    if len(nodes)!=len(inp.nodes):return {'ok':False,'error':'duplicate node names'}
    tasks={_key(t):t for t in inp.tasks}
    if len(tasks)!=len(inp.tasks):return {'ok':False,'error':'duplicate task names within an atespace'}
    wsdefs={w.name:w for w in inp.workspaces}
    if len(wsdefs)!=len(inp.workspaces):return {'ok':False,'error':'duplicate workspace names'}
    for t in inp.tasks:
        paths=[(w.path or f'/workspace/{w.name}') for w in t.workspaces]
        if len(set(paths))!=len(paths):return {'ok':False,'error':'duplicate workspace mount path','task':_key(t)}
        unknown=[w.name for w in t.workspaces if wsdefs and w.name not in wsdefs]
        if unknown:return {'ok':False,'error':'task uses undefined workspace','task':_key(t),'workspaces':unknown}
    deps={}
    for k,t in tasks.items():
        resolved=[]
        for d in t.depends_on:
            full=d if '/' in d else f'{t.atespace}/{d}'
            if full not in tasks:return {'ok':False,'error':'unknown dependency','task':k,'dependency':d}
            resolved.append(full)
        if k in resolved:return {'ok':False,'error':'task depends on itself','task':k}
        deps[k]=resolved
    waves=[];done=set();left=set(tasks)
    while left:
        ready=sorted(k for k in left if all(d in done for d in deps[k]))
        if not ready:return {'ok':False,'error':'dependency cycle','pending':sorted(left)}
        waves.append(ready);done.update(ready);left.difference_update(ready)
    cap={n:(cpu_millis(v.cpu),mem_bytes(v.memory),v.max_tasks) for n,v in nodes.items()}
    placements={};unplaced={};wave_use=[]
    for wi,wave in enumerate(waves):
        free={n:list(c) for n,c in cap.items()}
        order=sorted(wave,key=lambda k:(-tasks[k].priority,-cpu_millis(tasks[k].cpu_request),-mem_bytes(tasks[k].memory_request),k))
        for k in order:
            t=tasks[k];c,m=cpu_millis(t.cpu_request),mem_bytes(t.memory_request)
            cands=[n for n in nodes if all(nodes[n].labels.get(a)==b for a,b in t.node_selector.items())]
            if not cands:unplaced[k]='no node matches node_selector';continue
            fits=[n for n in cands if free[n][0]>=c and free[n][1]>=m and free[n][2]>=1]
            if not fits:
                big=[n for n in cands if cap[n][0]>=c and cap[n][1]>=m]
                unplaced[k]='request exceeds every matching node' if not big else 'matching nodes are full in this wave'
                continue
            if inp.strategy=='spread':pick=max(fits,key=lambda n:(free[n][0]/cap[n][0]+free[n][1]/cap[n][1],-list(nodes).index(n)))
            else:pick=min(fits,key=lambda n:(free[n][0]/cap[n][0]+free[n][1]/cap[n][1],list(nodes).index(n)))
            free[pick][0]-=c;free[pick][1]-=m;free[pick][2]-=1
            placements[k]={'node':pick,'wave':wi}
        wave_use.append({n:{'cpu_millis':cap[n][0]-free[n][0],'memory_bytes':cap[n][1]-free[n][1],'tasks':cap[n][2]-free[n][2]} for n in nodes})
    # a task whose dependency could not be placed cannot start either
    for wave in waves:
        for k in wave:
            if k in placements and any(d in unplaced for d in deps[k]):
                placements.pop(k);unplaced[k]='a dependency could not be placed'
    peak={n:max((u[n]['cpu_millis']/cap[n][0] for u in wave_use),default=0) for n in nodes}
    out={'ok':True,'waves':waves,'placements':placements,'unplaced':unplaced,'strategy':inp.strategy,
         'node_peak_cpu_utilization':{n:round(v,3) for n,v in peak.items()},
         'approval_required':sorted(k for k,t in tasks.items() if t.budget_usd>0),
         'executed':False,'spend_authorized':False,
         'caveat':'Plan from declared capacity only. Each wave is assumed to finish before the next starts, so its resources are free again. No cluster contacted, nothing scheduled or started; budgets grant no authority.'}
    if inp.export_ax:out['ax_manifests']=export_ax(inp)
    return out

def export_ax(inp):
    """Multi-document YAML (JSON syntax is valid YAML) of ax.io/v1alpha1 Workspace and Task objects."""
    docs=[]
    for w in inp.workspaces:
        spec={}
        if w.git:spec['git']=[{k:v for k,v in {'repo':g.repo,'branch':g.branch}.items() if v} for g in w.git]
        if w.files:spec['files']=[{'path':p,'content':c} for p,c in sorted(w.files.items())]
        docs.append({'apiVersion':'ax.io/v1alpha1','kind':'Workspace','metadata':{'name':w.name,'atespace':'default'},'spec':spec})
    for t in inp.tasks:
        res={'requests':{'cpu':str(t.cpu_request),'memory':t.memory_request}}
        if t.cpu_limit is not None or t.memory_limit is not None:
            res['limits']={k:v for k,v in {'cpu':None if t.cpu_limit is None else str(t.cpu_limit),'memory':t.memory_limit}.items() if v}
        spec={'resources':res}
        if t.image:spec['image']=t.image
        if t.workspaces:spec['workspaces']=[{k:v for k,v in {'name':w.name,'path':w.path,'goal':w.goal}.items() if v} for w in t.workspaces]
        docs.append({'apiVersion':'ax.io/v1alpha1','kind':'Task','metadata':{'name':t.name,'atespace':t.atespace},'spec':spec})
    return '\n---\n'.join(json.dumps(d,indent=2,sort_keys=True) for d in docs)+'\n'
