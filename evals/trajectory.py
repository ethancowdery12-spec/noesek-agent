"""Trajectory assertions over the turn spine (v2, stage G).

Fake-model (ScriptedLLM) controller runs leave a full turn-events trail;
these helpers assert on it: event ordering, required/absent events, and
tool-call evidence. Used by the injection suite and loop tests.
"""
from __future__ import annotations

from noesek.core.turn_spine import get_turn_events


async def trajectory(turn_id: str) -> list[dict]:
    events = await get_turn_events(turn_id)
    return [{"seq": e.seq, "kind": e.kind, "data": e.data} for e in events]


def kinds(traj: list[dict]) -> list[str]:
    return [e["kind"] for e in traj]


def assert_subsequence(traj: list[dict], expected: list[str]) -> None:
    """Every expected kind appears, in order (other events may interleave)."""
    it = iter(kinds(traj))
    missing = [k for k in expected if k not in it]
    assert not missing, f"trajectory missing ordered events {missing}; got {kinds(traj)}"


def assert_absent(traj: list[dict], kind: str) -> None:
    assert kind not in kinds(traj), f"unexpected {kind} in {kinds(traj)}"


def tool_calls(traj: list[dict]) -> list[str]:
    return [e["data"]["tool"] for e in traj if e["kind"] == "tool_call_requested"]


def assert_tool_not_requested(traj: list[dict], tool: str) -> None:
    assert tool not in tool_calls(traj), f"{tool} was requested: {tool_calls(traj)}"
