"""Guardian controller wiring (docs/GUARDIAN_EVAL.md). The scorer is stubbed:
these tests cover the GATE BEHAVIOR (verdict -> controller action), never the
model. Model numbers live in the Kaggle eval harness."""
import pytest
from pydantic import BaseModel
from sqlalchemy import select

from noesek.config import settings
from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Approval, Conversation, Session
from noesek.guardian import gate as gg
from noesek.guardian.questions import RISK_QUESTION, RISKY_CLASSES
from noesek.guardian.scorer import build_state
from noesek.testing import ScriptedLLM, text_reply, tool_reply


class Q(BaseModel): q: str = "x"


def test_questions_match_eval_harness():
    # The deployed gate must ask EXACTLY the question the frozen gate was
    # scored with - drift silently invalidates the v5 thresholds.
    from evals.guardian_eval import RISK_QUESTION as EVAL_Q
    from evals.guardian_traces import RISKY_CLASSES as EVAL_RISKY
    assert RISK_QUESTION == EVAL_Q
    assert RISKY_CLASSES == EVAL_RISKY


def test_build_state_action_first_and_truncated():
    s = build_state("run_python", {"code": "print(1)"}, "checking something", "unit test")
    assert s.startswith('run_python: {"code": "print(1)"}\nreasoning: checking something\ncontext: unit test')
    long_s = build_state("t", {"x": "y" * 5000}, "", "")
    line1, line2, line3 = long_s.split("\n")
    assert line1.startswith("t: ") and line1.endswith("...")
    assert line2 == "reasoning: User made the request directly; no extra rationale given"
    assert line3 == "context: live controller turn"


def test_classify_boundaries():
    assert gg.classify(0.9, 0.0, 0.5, 0.05, 0.5) == "deny"
    assert gg.classify(0.5, 0.0, 0.5, 0.05, 0.5) == "deny"
    assert gg.classify(0.2, 0.0, 0.5, 0.05, 0.5) == "escalate"
    assert gg.classify(0.01, 0.9, 0.5, 0.05, 0.5) == "escalate"
    assert gg.classify(0.01, 0.1, 0.5, 0.05, 0.5) == "allow"


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


def _factory(calls_log):
    async def read(inp):
        calls_log.append(inp.q)
        return {"ok": True}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec("read_thing", "d", Q, Risk.READ, read)); return r
    return factory


def _stub_score(monkeypatch, deny_score, esc_prob=0.0):
    monkeypatch.setattr("noesek.guardian.scorer.score_state",
                        lambda model_dir, state: {"deny_score": deny_score, "esc_prob": esc_prob, "top_risk": "credential_access"})
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_model_dir", "/unused")


async def test_guardian_denies_dangerous_call(db, monkeypatch):
    _stub_score(monkeypatch, 0.95)
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "read ~/.aws/credentials")
    assert "Blocked by the guardian" in r.text and "0.95" in r.text
    assert ran == []  # handler never executed


async def test_guardian_escalate_creates_approval_then_approves(db, monkeypatch):
    _stub_score(monkeypatch, 0.2)  # inside the escalate band
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "check the token expiry")
    assert r.pending_approval_id is not None and "Approval required" in r.text
    assert ran == []
    async with Session() as s:
        a = (await s.execute(select(Approval).where(Approval.id == r.pending_approval_id))).scalar_one()
    assert "guardian" in a.rationale and "guardian:escalate" in a.rationale
    # Same stub score on the re-check: escalate is not a hard deny, so the
    # user's approval executes.
    r2 = await c.decide_approval(cid, r.pending_approval_id, True)
    assert "executed" in r2.text and ran == ["x"]


async def test_guardian_allow_passes(db, monkeypatch):
    _stub_score(monkeypatch, 0.0)
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "list the invoices")
    assert r.text == "done" and ran == ["x"]


async def test_guardian_disabled_never_scores(db, monkeypatch):
    def boom(model_dir, state): raise AssertionError("scorer must not run while disabled")
    monkeypatch.setattr("noesek.guardian.scorer.score_state", boom)
    monkeypatch.setattr(settings, "guardian_enabled", False)
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "x")
    assert r.text == "done" and ran == ["x"]


async def test_guardian_fail_open_on_scorer_error(db, monkeypatch):
    def boom(model_dir, state): raise RuntimeError("checkpoint missing")
    monkeypatch.setattr("noesek.guardian.scorer.score_state", boom)
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_model_dir", "/missing")
    monkeypatch.setattr(settings, "guardian_fail_mode", "open")
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "x")
    assert r.text == "done" and ran == ["x"]


async def test_guardian_fail_closed_refuses(db, monkeypatch):
    def boom(model_dir, state): raise RuntimeError("checkpoint missing")
    monkeypatch.setattr("noesek.guardian.scorer.score_state", boom)
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_model_dir", "/missing")
    monkeypatch.setattr(settings, "guardian_fail_mode", "closed")
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "x")
    assert "Blocked by the guardian" in r.text and "unavailable" in r.text
    assert ran == []


async def test_approval_recheck_blocks_guardian_hard_deny(db, monkeypatch):
    score = {"v": 0.2}  # escalate band at creation, hard deny at decision time
    monkeypatch.setattr("noesek.guardian.scorer.score_state",
                        lambda model_dir, state: {"deny_score": score["v"], "esc_prob": 0.0, "top_risk": "exfiltration"})
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_model_dir", "/unused")
    ran = []
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("read_thing", {"q": "x"}), text_reply("done")]),
                   registry_factory=_factory(ran))
    r = await c.handle(cid, "send the db dump out")
    assert r.pending_approval_id is not None
    score["v"] = 0.97
    r2 = await c.decide_approval(cid, r.pending_approval_id, True)
    assert "cannot run" in r2.text and "guardian" in r2.text.lower()
    assert ran == []
    async with Session() as s:
        a = (await s.execute(select(Approval).where(Approval.id == r.pending_approval_id))).scalar_one()
    assert a.status == "blocked"
