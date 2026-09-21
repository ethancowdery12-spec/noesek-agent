"""Multi-model layer (roadmap item 20, Ethan's call Sep 21): role catalog,
per-task defaults, per-chat switching via switch_model."""
import pytest
from sqlalchemy import select

from noesek.config import settings
from noesek.core.llm import OpenAICompatibleLLM, allowed_models, model_catalog, model_for_task
from noesek.db import Conversation, Session
from noesek.tools.state import SwitchModelInput, switch_model_handler


@pytest.fixture
def deepseek_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(settings, "llm_model", "deepseek-chat")
    monkeypatch.setattr(settings, "llm_models", "")
    return settings


def test_catalog_defaults_on_deepseek(deepseek_settings):
    c = model_catalog()
    assert c["chat"] == "deepseek-chat"
    assert c["reasoning"] == "deepseek-reasoner"


def test_catalog_reasoning_falls_back_off_deepseek(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "llm_model", "gpt-5")
    monkeypatch.setattr(settings, "llm_models", "")
    assert model_catalog()["reasoning"] == "gpt-5"


def test_catalog_env_json_override(deepseek_settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_models", '{"reasoning": "deepseek-v4-pro", "vision": "deepseek-v4-flash"}')
    c = model_catalog()
    assert c["reasoning"] == "deepseek-v4-pro" and c["vision"] == "deepseek-v4-flash"
    assert "deepseek-v4-pro" in allowed_models()


def test_catalog_bad_json_keeps_defaults(deepseek_settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_models", "{not json")
    assert model_catalog()["reasoning"] == "deepseek-reasoner"


def test_task_defaults(deepseek_settings):
    assert model_for_task("researcher") == "deepseek-reasoner"
    assert model_for_task("evaluator") == "deepseek-reasoner"
    assert model_for_task("coder") == "deepseek-chat"
    assert model_for_task("chat") == "deepseek-chat"


def test_bound_adapter_overrides_model(deepseek_settings):
    assert OpenAICompatibleLLM(model="deepseek-reasoner")._model == "deepseek-reasoner"
    assert OpenAICompatibleLLM()._model is None


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def test_switch_model_persists_override(db, deepseek_settings):
    cid = await _conv()
    r = await switch_model_handler(cid)(SwitchModelInput(model="deepseek-reasoner"))
    assert r["switched"] and r["model"] == "deepseek-reasoner"
    async with Session() as s:
        conv = (await s.execute(select(Conversation).where(Conversation.id == cid))).scalar_one()
        assert conv.model_override == "deepseek-reasoner"


async def test_switch_model_rejects_unknown(db, deepseek_settings):
    cid = await _conv()
    r = await switch_model_handler(cid)(SwitchModelInput(model="gpt-99-turbo"))
    assert "error" in r and "deepseek-chat" in r["error"]


async def test_switch_model_default_clears(db, deepseek_settings):
    cid = await _conv()
    await switch_model_handler(cid)(SwitchModelInput(model="deepseek-reasoner"))
    r = await switch_model_handler(cid)(SwitchModelInput(model="default"))
    assert r["switched"] and r["model"] == "deepseek-chat"
    async with Session() as s:
        conv = (await s.execute(select(Conversation).where(Conversation.id == cid))).scalar_one()
        assert conv.model_override is None


def test_controller_llm_for_model_caches(db, deepseek_settings):
    from noesek.core.controller import Controller
    from noesek.testing import ScriptedLLM
    c = Controller(llm=ScriptedLLM([]))
    a = c._llm_for_model("deepseek-reasoner")
    assert a is c._llm_for_model("deepseek-reasoner") and a._model == "deepseek-reasoner"
    assert c._llm_for_model(None) is c.llm
