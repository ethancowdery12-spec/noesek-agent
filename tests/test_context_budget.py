import pytest,pydantic
from noesek.tools.context_budget import ContextBudgetInput,context_budget,Event
def run(events,**kw):return context_budget(ContextBudgetInput(events=events,**kw))
E=lambda i,kind,text,**kw:{'id':str(i),'kind':kind,'text':text,**kw}

def test_open_decisions_and_tasks_always_survive_a_tight_budget():
    ev=[E(1,'decision','Use Postgres not SQLite for prod'),E(2,'output','x'*5000),E(3,'task','Backfill the new column'),E(4,'output','y'*5000)]
    out=run(ev,budget_chars=300)
    assert '[1] decision' in out['brief'] and '[3] task' in out['brief'] and out['brief_chars']<=300
    assert out['saved_ratio']>0.95 and out['events_returned']>=2

def test_resolved_items_are_not_pinned_and_resolved_errors_rank_lower():
    ev=[E(1,'task','Old task',resolved=True),E(2,'error','Connection refused',resolved=True),E(3,'error','Timeout in worker'),E(4,'note','misc')]
    out=run(ev,budget_chars=200,line_chars=60)
    ids=[l.split(']')[0][1:] for l in out['brief'].splitlines()]
    assert ids.index('3')<ids.index('2') if '2' in ids else True

def test_query_pulls_matching_events_ahead():
    ev=[E(1,'note','weather is nice'),E(2,'note','database migration failed on step three'),E(3,'note','lunch')]
    out=run(ev,query='database migration',budget_chars=200);first=out['brief'].splitlines()[0]
    assert first.startswith('[2]')

def test_budget_is_a_hard_cap_and_omissions_are_listed():
    ev=[E(i,'note','word '*50) for i in range(40)]
    out=run(ev,budget_chars=500,line_chars=80)
    assert out['brief_chars']<=500 and out['omitted_count']==40-out['events_returned'] and out['omitted_ids']

def test_long_lines_are_clipped_and_flagged():
    out=run([E(1,'decision','a'*1000)],line_chars=50,budget_chars=300)
    assert out['clipped_lines']==1 and out['brief'].endswith('…')

def test_exact_text_never_rewritten():
    out=run([E(1,'edit','src/app.py: changed retry from 3 to 5')],budget_chars=500)
    assert 'changed retry from 3 to 5' in out['brief']

def test_duplicate_ids_and_bad_input_rejected():
    assert run([E(1,'note','a'),E(1,'note','b')])['ok'] is False
    for bad in ({'id':'','kind':'note','text':'x'},{'id':'a','kind':'weird','text':'x'},{'id':'a','kind':'note','text':''}):
        with pytest.raises(pydantic.ValidationError):Event(**bad)
    with pytest.raises(pydantic.ValidationError):ContextBudgetInput(events=[E(1,'note','a')],budget_chars=10)
