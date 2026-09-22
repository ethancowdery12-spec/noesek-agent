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
