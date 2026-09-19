"""Stage B: ordered policy engine + approval leases."""
import pytest
from pydantic import BaseModel
from sqlalchemy import select

from noesek.core.controller import Controller
from noesek.core.policy import ASK, DENY, ALLOW, evaluate_policy, parse_rules, PolicyRule
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Approval, Conversation, Session
from noesek.testing import ScriptedLLM, tool_reply


class W(BaseModel): v: int = 1
class R(BaseModel): cmd: str = ""


def _factory(name, model, risk, result=None, calls=None):
    async def handler(inp):
        if calls is not None: calls.append(dict(inp.model_dump()))
        return result or {"ok": True}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec(name, "d", model, risk, handler)); return r
    return factory


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


# --- pure engine ---

def test_first_match_wins():
    rules = (
        PolicyRule(DENY, tools=("deploy*",), rule="r0"),
        PolicyRule(ALLOW, tools=("deploy_prod",), rule="r1"),
    )
    d = evaluate_policy("deploy_prod", Risk.WRITE, {}, extra_rules=rules)
    assert d.effect == DENY and d.rule == "r0"


def test_defaults_preserve_v1_behavior():
    assert evaluate_policy("remember", Risk.WRITE, {}).needs_approval
    assert evaluate_policy("recall", Risk.READ, {}).allowed


def test_contains_matcher():
    rules = (PolicyRule(DENY, contains="prod-db", rule="r0"),)
    assert evaluate_policy("run", Risk.READ, {"cmd": "drop prod-db"}, extra_rules=rules).denied
    assert evaluate_policy("run", Risk.READ, {"cmd": "ls"}, extra_rules=rules).allowed


def test_hardline_content_cannot_be_overridden():
    rules = (PolicyRule(ALLOW, tools=("*",), rule="r0"),)
    d = evaluate_policy("run", Risk.READ, {"cmd": "rm -rf /"}, extra_rules=rules)
    assert d.denied and d.rule == "hardline"


def test_parse_rules_validation():
    assert parse_rules("") == ()
    rules = parse_rules('[{"effect":"deny","tools":["deploy*"],"reason":"no deploys"}]')
    assert rules[0].effect == DENY and rules[0].tools == ("deploy*",)
    with pytest.raises(ValueError):
        parse_rules('{"effect":"deny"}')
    with pytest.raises(ValueError):
        parse_rules('[{"effect":"yolo"}]')


# --- controller integration ---

async def test_configured_allow_runs_write_tool_without_approval(db, monkeypatch):
    from noesek.config import settings
    monkeypatch.setattr(settings, "policy_rules", '[{"effect":"allow","tools":["write_thing"],"reason":"trusted"}]')
    cid = await _conv()
    calls = []
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 1}), __import__("noesek.testing", fromlist=["text_reply"]).text_reply("done")]),
                   registry_factory=_factory("write_thing", W, Risk.WRITE, calls=calls))
    r = await c.handle(cid, "write")
    assert r.pending_approval_id is None and calls == [{"v": 1}] and r.text == "done"


async def test_lease_binds_turn_and_canonical_args(db):
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 7})]),
                   registry_factory=_factory("write_thing", W, Risk.WRITE))
    r = await c.handle(cid, "write")
    async with Session() as s:
        a = (await s.execute(select(Approval).where(Approval.id == r.pending_approval_id))).scalar_one()
        assert a.turn_id == r.turn_id
        assert '"v": 7' in a.canonical_args


async def test_lease_integrity_blocks_tampered_arguments(db):
    cid = await _conv()
    calls = []
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 7})]),
                   registry_factory=_factory("write_thing", W, Risk.WRITE, calls=calls))
    r = await c.handle(cid, "write")
    async with Session() as s:
        a = (await s.execute(select(Approval).where(Approval.id == r.pending_approval_id))).scalar_one()
        a.arguments = {"v": 999}  # tamper after lease creation
        await s.commit()
    r2 = await c.decide_approval(cid, r.pending_approval_id, True)
    assert calls == [] and "no longer match" in r2.text
    async with Session() as s:
        a = (await s.execute(select(Approval).where(Approval.id == r.pending_approval_id))).scalar_one()
        assert a.status == "blocked"


async def test_lease_single_use(db):
    cid = await _conv()
    calls = []
    c = Controller(llm=ScriptedLLM([tool_reply("write_thing", {"v": 1})]),
                   registry_factory=_factory("write_thing", W, Risk.WRITE, calls=calls))
    r = await c.handle(cid, "write")
    r1 = await c.decide_approval(cid, r.pending_approval_id, True)
    r2 = await c.decide_approval(cid, r.pending_approval_id, True)
    assert calls == [{"v": 1}] and "already executed" in r2.text
