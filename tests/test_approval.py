import pytest
from datetime import timedelta
from pydantic import BaseModel
from sqlalchemy import select
from noesek.core.controller import APPROVAL_RISKS, Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Approval, Conversation, Session, now

def test_risk_policy():
    assert Risk.READ not in APPROVAL_RISKS
    assert {Risk.WRITE, Risk.EXTERNAL, Risk.MONEY, Risk.DESTRUCTIVE} <= APPROVAL_RISKS

class W(BaseModel): v: int = 1

def stub_controller(calls):
    async def handler(inp): calls.append(inp.v); return {"ok": True, "v": inp.v}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec("write_thing", "d", W, Risk.WRITE, handler)); return r
    return Controller(registry_factory=factory)

async def _conv():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); return c.id

async def _approval(cid, **kw):
    async with Session() as s:
        a = Approval(conversation_id=cid, tool_name="write_thing", arguments={"v": 7}, rationale="r", **kw)
        s.add(a); await s.commit(); return a.id

async def test_approve_executes_once(db):
    cid = await _conv(); aid = await _approval(cid)
    calls = []; c = stub_controller(calls)
    r1 = await c.decide_approval(cid, aid, True)
    assert "executed" in r1.text and calls == [7]
    r2 = await c.decide_approval(cid, aid, True)
    assert "already executed" in r2.text and calls == [7]

async def test_reject_does_not_execute(db):
    cid = await _conv(); aid = await _approval(cid)
    calls = []; c = stub_controller(calls)
    r = await c.decide_approval(cid, aid, False)
    assert "Rejected" in r.text and calls == []

async def test_cross_conversation_blocked(db):
    cid = await _conv(); aid = await _approval(cid)
    async with Session() as s:
        other = Conversation(channel="cli", external_user_id="u2"); s.add(other); await s.commit(); oid = other.id
    calls = []; c = stub_controller(calls)
    r = await c.decide_approval(oid, aid, True)
    assert "not found" in r.text and calls == []

async def test_expired_approval_cannot_execute(db):
    cid = await _conv(); aid = await _approval(cid, expires_at=now() - timedelta(hours=1))
    calls = []; c = stub_controller(calls)
    r = await c.decide_approval(cid, aid, True)
    assert "expired" in r.text.lower() and calls == []

async def test_pending_listing_scoped_and_live_only(db):
    cid = await _conv()
    await _approval(cid)
    await _approval(cid, expires_at=now() - timedelta(hours=1))
    c = stub_controller([])
    r = await c.pending_approvals(cid)
    assert "Pending approvals" in r.text and r.text.count("#") == 1
