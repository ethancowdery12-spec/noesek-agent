"""Stage G: trajectory assertions + AgentDojo-style injection suite (fake-model)."""
from pydantic import BaseModel

from evals.injection_suite import INJECTIONS, run_scenario
from evals.trajectory import assert_absent, assert_subsequence, kinds, tool_calls, trajectory
from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Conversation, Session
from noesek.testing import ScriptedLLM, tool_reply, text_reply


class Q(BaseModel): q: str = "x"


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def test_trajectory_assertion_helpers(db):
    cid = await _conv()
    async def search(inp): return {"results": []}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("search", "d", Q, Risk.READ, search)); return r
    c = Controller(llm=ScriptedLLM([tool_reply("search", {"q": "x"}), text_reply("done")]),
                   registry_factory=factory)
    r = await c.handle(cid, "x")
    traj = await trajectory(r.turn_id)
    assert_subsequence(traj, ["turn_started", "model_request", "tool_call_requested", "turn_completed"])
    assert_absent(traj, "policy_blocked")
    assert tool_calls(traj) == ["search"]


async def test_full_injection_suite_passes(db):
    for name, hostile in INJECTIONS.items():
        result = await run_scenario(name, hostile)
        assert result["passed"], result.get("reason")


async def test_fake_approval_text_does_not_forge_a_lease(db):
    """Injection claiming an approval exists must not create one: approving a
    non-existent id fails, and the money call still gates."""
    result = await run_scenario("fake_approval", INJECTIONS["fake_approval"])
    assert result["passed"]
