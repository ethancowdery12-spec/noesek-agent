import hashlib
import json
from pathlib import Path
import pytest
from noesek.tools.agent_roster import AgentRosterInput,agent_roster,_ROOT

COMMIT='156b7a5e7a8b'+'93642628a339ee4039c925b34c7f'  # pragma: allowlist secret

def call(**kw):return agent_roster(AgentRosterInput(**kw))

def test_all_202_agents_are_present_and_hash_exact():
    man=json.loads((_ROOT/'manifest.json').read_text())
    assert man['count']==len(man['agents'])==202 and man['license']=='MIT'
    assert len({a['name'] for a in man['agents']})==202
    on_disk=sorted(p.name for p in (_ROOT/'agents').glob('*.md'))
    assert on_disk==sorted(a['name']+'.md' for a in man['agents'])
    for a in man['agents']:
        raw=(_ROOT/'agents'/f"{a['name']}.md").read_bytes()
        assert hashlib.sha256(raw).hexdigest()==a['sha256'] and len(raw)==a['bytes']

def test_license_file_matches_recorded_hash_and_holder():
    man=json.loads((_ROOT/'manifest.json').read_text());raw=(_ROOT/'LICENSE').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==man['license_sha256'] and b'Seth Hobson' in raw and b'MIT License' in raw

def test_every_agent_can_be_read_through_the_tool():
    for a in json.loads((_ROOT/'manifest.json').read_text())['agents']:
        out=call(action='get',name=a['name'])
        assert out['ok'] and out['content'].startswith('---') and not out['grants_authority']
        assert out['agent']['sha256']==a['sha256']

def test_summary_counts():
    out=call()
    assert out['agents']==202 and out['plugins']==82 and out['provenance']['commit']==COMMIT
    assert sum(out['by_model'].values())==202

def test_search_ranks_name_and_description():
    out=call(action='search',query='terraform infrastructure')
    assert out['ok'] and out['agents'][0]['name'].endswith('terraform-specialist')
    assert call(action='search',query='!!!')['ok'] is False
    assert call(action='search',query='terraform',plugin='no-such-plugin')['total']==0

def test_list_filter_and_limit():
    out=call(action='list',limit=5)
    assert len(out['agents'])==5 and out['total']==202
    plugin=out['agents'][0]['plugin'];sub=call(action='list',plugin=plugin,limit=50)
    assert sub['total']>=1 and all(a['plugin']==plugin for a in sub['agents'])

def test_unknown_and_escape_names_refused():
    for name in ('../../config','unknown-agent','','A/B','agents/x'):
        assert call(action='get',name=name)['ok'] is False

def test_tampered_file_is_refused(tmp_path,monkeypatch):
    import noesek.tools.agent_roster as mod
    man=json.loads((_ROOT/'manifest.json').read_text());a=man['agents'][0]
    (tmp_path/'agents').mkdir();(tmp_path/'agents'/f"{a['name']}.md").write_bytes(b'changed')
    (tmp_path/'manifest.json').write_text(json.dumps(man))
    monkeypatch.setattr(mod,'_ROOT',tmp_path)
    assert call(action='get',name=a['name'])['ok'] is False
