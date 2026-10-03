import pytest,pydantic
from noesek.tools.task_next import TaskNextInput,task_next,complexity,Item
def run(tasks,**kw):return task_next(TaskNextInput(tasks=[{'id':str(i),'title':f't{i}',**t} for i,t in tasks],**kw))

def test_picks_highest_priority_ready_task_and_lists_blocked():
    out=run([(1,{'status':'done'}),(2,{'dependencies':['1'],'priority':'low'}),(3,{'dependencies':['1'],'priority':'high'}),(4,{'dependencies':['3']})])
    assert out['next']=='3' and out['ready']==['3','2'] and out['blocked']=={'4':['waiting on 3']}
    assert out['progress']=={'done':1,'total':4,'percent':25.0}

def test_in_progress_work_comes_before_new_work_and_unblocking_breaks_ties():
    out=run([(1,{'status':'in_progress','priority':'low'}),(2,{'priority':'high'})]);assert out['next']=='1'
    out=run([(1,{}),(2,{}),(3,{'dependencies':['2']}),(4,{'dependencies':['2']})]);assert out['next']=='2' and 'unblocks 2' in out['why_next']

def test_caller_blocked_and_deferred_are_not_ready():
    out=run([(1,{'status':'blocked'}),(2,{'status':'deferred'}),(3,{})])
    assert out['ready']==['3'] and out['blocked']['1'][0]=='marked blocked by caller' and '2' not in out['blocked']

def test_all_done_and_nothing_ready():
    out=run([(1,{'status':'done'}),(2,{'status':'cancelled'})]);assert out['all_done'] and out['next'] is None and out['why_next']=='nothing ready'

def test_invalid_graphs_rejected():
    assert run([(1,{'dependencies':['9']})])['error']=='unknown dependencies'
    assert run([(1,{'dependencies':['2']}),(2,{'dependencies':['1']})])['error']=='dependency cycle'
    assert run([(1,{'dependencies':['1']})])['error']=='task depends on itself'
    assert task_next(TaskNextInput(tasks=[Item(id='a',title='x'),Item(id='a',title='y')]))['error']=='duplicate task id'

def test_complexity_grows_with_size_deps_and_heavy_words_and_flags_unsplit_big_tasks():
    small=Item(id='s',title='Fix typo');big=Item(id='b',title='Migrate payment schema and integrate authentication',description=' '.join(['detail']*200),dependencies=['1','2','3'])
    assert complexity(small)<complexity(big)<=10 and complexity(small)>=1
    out=run([(1,{}),(2,{}),(3,{}),(4,{'title':'Migrate payment schema and integrate authentication','description':' '.join(['detail']*200),'dependencies':['1','2','3']})])
    assert '4' in out['suggest_split']
    out=run([(1,{}),(2,{}),(3,{}),(4,{'title':'Migrate payment schema and integrate authentication','description':' '.join(['detail']*200),'dependencies':['1','2','3'],'subtasks':['a','b','c']})])
    assert '4' not in out['suggest_split']

def test_limits():
    for bad in ({'id':' ','title':'x'},{'id':'a','title':''},{'id':'a','title':'x','status':'weird'}):
        with pytest.raises(pydantic.ValidationError):Item(**bad)
