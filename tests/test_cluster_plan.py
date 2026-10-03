import json
import pytest
from pydantic import ValidationError
from noesek.tools.cluster_plan import ClusterPlanInput,cluster_plan,cpu_millis,mem_bytes,Node,Task

def plan(nodes,tasks,**kw):return cluster_plan(ClusterPlanInput(nodes=nodes,tasks=tasks,**kw))
N=lambda name,cpu=4,mem='8Gi',**kw:{'name':name,'cpu':cpu,'memory':mem,**kw}
T=lambda name,**kw:{'name':name,**kw}

def test_quantities_parse_exactly_and_reject_junk():
    assert cpu_millis('500m')==500 and cpu_millis(2)==2000 and cpu_millis('0.25')==250
    assert mem_bytes('1Gi')==2**30 and mem_bytes('512Mi')==512*2**20 and mem_bytes('2G')==2*10**9
    for bad in ('0','-1','abc','1e3','5x'):
        with pytest.raises(ValueError):cpu_millis(bad)
    for bad in ('0','1gb','','Gi'):
        with pytest.raises(ValueError):mem_bytes(bad)

def test_spread_balances_and_pack_fills_first_node():
    nodes=[N('a'),N('b')];tasks=[T('t1',cpu_request='1',memory_request='1Gi'),T('t2',cpu_request='1',memory_request='1Gi')]
    s=plan(nodes,tasks,strategy='spread')['placements'];assert {s['default/t1']['node'],s['default/t2']['node']}=={'a','b'}
    p=plan(nodes,tasks,strategy='pack')['placements'];assert p['default/t1']['node']==p['default/t2']['node']=='a'

def test_never_exceeds_node_capacity():
    nodes=[N('a',cpu=2,mem='4Gi'),N('b',cpu=2,mem='4Gi')]
    tasks=[T(f't{i}',cpu_request='1',memory_request='1Gi') for i in range(5)]
    out=plan(nodes,tasks)
    assert len(out['placements'])==4 and len(out['unplaced'])==1
    assert 'full' in list(out['unplaced'].values())[0]
    per={};
    for v in out['placements'].values():per[v['node']]=per.get(v['node'],0)+1
    assert max(per.values())<=2

def test_request_larger_than_any_node_and_selector_mismatch_have_clear_reasons():
    out=plan([N('a',cpu=2,mem='4Gi',labels={'gpu':'no'})],[T('big',cpu_request='8'),T('sel',node_selector={'gpu':'yes'})])
    assert out['unplaced']['default/big']=='request exceeds every matching node'
    assert out['unplaced']['default/sel']=='no node matches node_selector'

def test_dependencies_make_waves_and_a_failed_dependency_blocks_dependents():
    out=plan([N('a',cpu=2)],[T('build'),T('test',depends_on=['build']),T('ship',depends_on=['test'])])
    assert out['waves']==[['default/build'],['default/test'],['default/ship']]
    out=plan([N('a',cpu=2)],[T('big',cpu_request='9'),T('after',depends_on=['big'])])
    assert out['unplaced']['default/after']=='a dependency could not be placed'
    assert not out['placements']

def test_cycles_unknown_deps_duplicates_rejected():
    assert plan([N('a')],[T('x',depends_on=['y']),T('y',depends_on=['x'])])['error']=='dependency cycle'
    assert plan([N('a')],[T('x',depends_on=['nope'])])['error']=='unknown dependency'
    assert plan([N('a')],[T('x',depends_on=['x'])])['error']=='task depends on itself'
    assert plan([N('a')],[T('x'),T('x')])['error'].startswith('duplicate task')
    assert plan([N('a'),N('a')],[T('x')])['error']=='duplicate node names'

def test_same_name_in_different_atespaces_and_cross_space_dependency():
    out=plan([N('a')],[T('job',atespace='dev'),T('job',atespace='prod',depends_on=['dev/job'])])
    assert out['ok'] and out['waves']==[['dev/job'],['prod/job']]

def test_priority_decides_who_gets_the_last_slot():
    out=plan([N('a',cpu=1)],[T('low',cpu_request='1',priority=0),T('high',cpu_request='1',priority=5)])
    assert 'default/high' in out['placements'] and 'default/low' in out['unplaced']

def test_names_limits_and_paths_validated():
    for bad in (T('Bad_Name'),T('x',atespace='UP'),T('x',cpu_limit='100m',cpu_request='1'),T('x',memory_limit='1Mi',memory_request='1Gi'),
                T('x',workspaces=[{'name':'w','path':'../etc'}]),T('x',workspaces=[{'name':'w','path':'rel'}])):
        with pytest.raises(ValidationError):Task(**bad)
    with pytest.raises(ValidationError):Node(**N('a'*64))
    assert plan([N('a')],[T('x',workspaces=[{'name':'w'},{'name':'v','path':'/workspace/w'}])])['error']=='duplicate workspace mount path'
    assert plan([N('a')],[T('x',workspaces=[{'name':'zzz'}])],workspaces=[{'name':'w'}])['error']=='task uses undefined workspace'

def test_repo_urls_with_credentials_or_other_schemes_rejected():
    from noesek.tools.cluster_plan import GitSource
    GitSource(repo='https://github.com/golang/go.git')
    for bad in ('http://x.com/a','https://user:pw@x.com/a'  # pragma: allowlist secret
        ,'git@github.com:a/b.git','file:///etc','https://x.com'):
        with pytest.raises(ValidationError):GitSource(repo=bad)

def test_ax_export_is_parseable_and_matches_declared_fleet():
    out=plan([N('a')],[T('t',image='ghcr.io/o/i',cpu_limit='2',memory_limit='4Gi',workspaces=[{'name':'golang','goal':'build it'}],budget_usd=5)],
             workspaces=[{'name':'golang','git':[{'repo':'https://github.com/golang/go.git','branch':'my-fix'}],'files':{'AGENTS.md':'be brief'}}],export_ax=True)
    docs=[json.loads(d) for d in out['ax_manifests'].split('\n---\n')]
    assert [d['kind'] for d in docs]==['Workspace','Task'] and all(d['apiVersion']=='ax.io/v1alpha1' for d in docs)
    assert docs[0]['spec']['git'][0]['branch']=='my-fix' and docs[0]['spec']['files'][0]['path']=='AGENTS.md'
    t=docs[1];assert t['spec']['resources']=={'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'2','memory':'4Gi'}}
    assert t['spec']['workspaces']==[{'name':'golang','goal':'build it'}]
    assert out['approval_required']==['default/t'] and out['executed'] is False and out['spend_authorized'] is False

def test_large_fleet_is_fast_and_deterministic():
    import time
    nodes=[N(f'n{i}',cpu=16,mem='64Gi') for i in range(50)];tasks=[T(f't{i}',cpu_request='500m',memory_request='1Gi') for i in range(1000)]
    start=time.monotonic();a=plan(nodes,tasks);b=plan(nodes,tasks)
    assert a==b and len(a['placements'])==1000 and time.monotonic()-start<10
    assert max(a['node_peak_cpu_utilization'].values())<=1.0
