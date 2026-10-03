import hashlib
import json
import pytest
from noesek.tools.skill_pack import SkillPackInput,skill_pack,_dirs,_man,parse_prompts

def call(**kw):return skill_pack(SkillPackInput(**kw))

def test_four_packs_present_with_exact_counts_and_licenses():
    out={p['pack']:p for p in call()['packs']}
    assert set(out)=={'agents','superpowers','i-have-adhd','awesome-gpt-image-2'}
    assert out['agents']['files']==202 and out['superpowers']['files']==74 and out['i-have-adhd']['files']==3 and out['awesome-gpt-image-2']['files']==1
    assert out['superpowers']['license']=='MIT' and out['awesome-gpt-image-2']['license']=='CC-BY-4.0'
    assert 'CC BY 4.0' in out['awesome-gpt-image-2']['attribution']

def test_every_vendored_file_is_hash_exact_and_license_matches():
    for name,d in _dirs().items():
        m=_man(d)
        assert hashlib.sha256((d/'LICENSE').read_bytes()).hexdigest()==m['license_sha256']
        for f in m['files']:
            raw=(d/f['dest']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==f['sha256'] and len(raw)==f['bytes'],(name,f['dest'])

def test_superpowers_has_the_fifteen_skill_files():
    files=call(action='files',pack='superpowers',query='SKILL.md')['files']
    assert len(files)==15
    out=call(action='get',pack='superpowers',file='files/skills/test-driven-development/SKILL.md')
    assert out['ok'] and out['content'].startswith('---') and not out['grants_authority']

def test_adhd_skill_and_eval_cases_readable():
    out=call(action='get',pack='i-have-adhd',file='files/skills/i-have-adhd/SKILL.md')
    assert out['ok'] and 'Lead with the next action' in out['content']
    cases=call(action='get',pack='i-have-adhd',file='files/evals/cases.jsonl')['content'].splitlines()
    assert len(cases)>=5 and all('prompt' in json.loads(c) for c in cases)

def test_search_finds_debugging_skill_and_ignores_agent_pack():
    out=call(action='search',query='systematic debugging root cause')
    assert out['ok'] and out['results'][0]['pack']=='superpowers' and 'debugging' in out['results'][0]['file']
    assert all(r['pack']!='agents' for r in out['results'])
    assert not call(action='search',query='???')['ok']

def test_image_prompts_parse_search_and_carry_attribution():
    out=call(action='image_prompts',query='exploded view poster',limit=3)
    assert out['ok'] and out['attribution_required'] and 'CC BY 4.0' in out['provenance']['attribution']
    assert 'VR Headset' in out['prompts'][0]['title'] and out['prompts'][0]['prompt'].strip()
    assert call(action='image_prompts',limit=30)['total']>=100

def test_parser_handles_missing_sections():
    text='### No. 1: A\n\n#### 📖 Description\n\nd\n\n#### 📝 Prompt\n\n```\nP\n```\n### No. 2: B\n\nno prompt here\n## Next'
    assert [e['number'] for e in parse_prompts(text)]==[1]

def test_unknown_pack_file_and_tamper_refused(tmp_path,monkeypatch):
    assert not call(action='files',pack='nope')['ok']
    assert not call(action='get',pack='superpowers',file='../../config.py')['ok']
    import noesek.tools.skill_pack as mod
    d=_dirs()['i-have-adhd'];m=_man(d);f=m['files'][0]
    (tmp_path/'packs'/'i-have-adhd'/'files'/'skills'/'i-have-adhd').mkdir(parents=True);(tmp_path/'packs'/'i-have-adhd'/f['dest']).write_bytes(b'changed')
    (tmp_path/'packs'/'i-have-adhd'/'manifest.json').write_text(json.dumps(m))
    monkeypatch.setattr(mod,'_DATA',tmp_path)
    assert not call(action='get',pack='i-have-adhd',file=f['dest'])['ok']
