from noesek.tools.source_reference import SourceReferenceInput,source_reference

def test_manifest_content_hash_and_notice():
    catalog=source_reference(SourceReferenceInput())
    assert len(catalog['references'])==2
    for item in catalog['references']:
        for file in item['files']:
            out=source_reference(SourceReferenceInput(action='get',name=item['name'],file=file))
            assert out['ok'] and out['provenance']['license']=='MIT' and not out['grants_authority']
    text=source_reference(SourceReferenceInput(action='get',name='fixing-accessibility',file='LICENSE'))['content']
    assert 'Julien Thibeaut' in text

def test_path_escape_and_unknown_ref_refused():
    for name,file in [('../secret','SKILL.md'),('fixing-accessibility','../../config.py'),('unknown','LICENSE')]:
        assert not source_reference(SourceReferenceInput(action='get',name=name,file=file))['ok']
