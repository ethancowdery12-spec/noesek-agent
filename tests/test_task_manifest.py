import pytest
from noesek.tools.task_manifest import TaskManifestInput,TaskUnit,task_manifest

def test_order_pause_and_budget_are_explicit():
    inp=TaskManifestInput(tasks=[TaskUnit(id='review',owner='reviewer',dependencies=['build'],status='paused',output_ref='check:1'),TaskUnit(id='build',owner='builder',status='done',output_ref='commit:1')])
    out=task_manifest(inp)
    assert out['order']==['build','review'] and out['paused']==['review']
    assert out['executed'] is False and out['outbound_network']=='denied'

def test_cycle_missing_and_duplicate_are_not_partial_success():
    for tasks in ([TaskUnit(id='a',owner='x',dependencies=['b'])],[TaskUnit(id='a',owner='x',dependencies=['b']),TaskUnit(id='b',owner='x',dependencies=['a'])],[TaskUnit(id='a',owner='x'),TaskUnit(id='a',owner='y')]):
        assert not task_manifest(TaskManifestInput(tasks=tasks))['ok']

def test_done_requires_output_and_budget_does_not_authorize_spend():
    out=task_manifest(TaskManifestInput(tasks=[TaskUnit(id='a',owner='x',status='done')]))
    assert not out['ok']
    out=task_manifest(TaskManifestInput(tasks=[TaskUnit(id='a',owner='x',budget_usd=3)]))
    assert out['approval_required']==['a'] and not out['spend_authorized']
