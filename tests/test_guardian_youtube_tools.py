import json
from evals.guardian_youtube_tools import CASES,PENDING_TRACES
from finetune.dump_tools import production_specs

def test_new_pending_traces_match_actual_schemas_and_risks():
    specs={s.name:s for s in production_specs()}
    assert len(PENDING_TRACES)==len(CASES)*6
    for tool,args in CASES.items():specs[tool].input_model.model_validate(args)
    for t in PENDING_TRACES:
        tool=t['state'].split(': ',1)[0]
        assert t['gold']==('escalate' if tool=='writing_profile' else 'allow')
        assert 'Untrained supplement' in t['note']
        json.loads(t['state'].split('\n',1)[0].split(': ',1)[1])
