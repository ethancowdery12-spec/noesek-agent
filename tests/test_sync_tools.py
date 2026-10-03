"""Sync tool handlers must work through ToolRegistry.invoke (Sep 22 live bug:
design_system/office_doc/playbook are sync defs; the runner awaited their dict
result -> TypeError: object dict can't be used in 'await' expression)."""
import pytest

from noesek.core.tools import ToolRegistry
from noesek.core.types import Risk
from noesek.tools.chat_extras import register_chat_extras


@pytest.fixture()
def reg():
    r = ToolRegistry()
    register_chat_extras(r, conversation_id=1, controller=None, timeout=30.0)
    return r


@pytest.mark.asyncio
async def test_design_system_list_themes(reg):
    out = await reg.invoke("design_system", {"action": "list"})
    assert "themes" in out and len(out["themes"]) == 3


@pytest.mark.asyncio
async def test_playbook_load_terse(reg):
    out = await reg.invoke("playbook", {"action": "load", "name": "terse"})
    assert "error" not in out


@pytest.mark.asyncio
async def test_playbook_load_spec_first(reg):
    out = await reg.invoke("playbook", {"action": "load", "name": "spec_first"})
    assert "error" not in out


@pytest.mark.asyncio
async def test_office_doc_missing_binary_degrades(reg):
    out = await reg.invoke("office_doc", {"action": "create", "file": "demo.pptx"})
    assert "officecli" in str(out).lower()

@pytest.mark.asyncio
async def test_real_registry_new_tools_and_consent_risk(reg):
    assert reg.get('writing_profile').risk==Risk.WRITE
    out=await reg.invoke('video_learn',{'video_url':'https://youtu.be/abcdefghijk','transcript':'hello'})
    assert out['ok'] and not out['timestamps_available']
    out=await reg.invoke('task_manifest',{'tasks':[{'id':'a','owner':'me'}]})
    assert out['ok'] and not out['executed']
    out=await reg.invoke('writing_profile',{'samples':['hello world'],'user_authorized':True})
    assert out['ok'] and out['authorization_trust']=='caller_assertion_not_verified'

@pytest.mark.asyncio
async def test_controller_holds_writing_profile_for_approval(db):
    from noesek.core.controller import Controller
    from noesek.testing import ScriptedLLM,tool_reply
    from noesek.db import Conversation,Session
    async with Session() as s:
        c=Conversation(channel='cli',external_user_id='owner');s.add(c);await s.commit();cid=c.id
    llm=ScriptedLLM([tool_reply('writing_profile',{'samples':['private writing'],'user_authorized':True})])
    out=await Controller(llm=llm).handle(cid,'describe my writing')
    assert out.pending_approval_id is not None

@pytest.mark.parametrize('name',['frontend_reference','legal_review','finance_review','crm_support_workflow','linkedin_draft','motion_render','evidence_handoff'])
@pytest.mark.asyncio
async def test_batch_workflow_playbooks_are_available_without_actions(reg,name):
    out=await reg.invoke('playbook',{'action':'load','name':name})
    assert 'error' not in out and out['grants_authority'] is False
