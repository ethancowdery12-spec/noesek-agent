"""Own-code offline agent org chart: roles, chain of command, delegation, goal
ancestry and budget roll-ups.

Ideas from Paperclip (paperclipai/paperclip, MIT; org chart, task-based
delegation, goal alignment, budgets with threshold alerts) re-implemented here.
No code was copied. Nothing is started, messaged or spent: it validates the
caller's declared org and answers questions about it. Budgets are labels for
planning, not authority to spend.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Agent(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    role: str = Field(default="", max_length=120)
    reports_to: str = Field(default="", max_length=80)
    skills: list[str] = Field(default_factory=list, max_length=40)
    budget_usd: float = Field(default=0, ge=0, le=1_000_000, allow_inf_nan=False)
    spent_usd: float = Field(default=0, ge=0, le=1_000_000, allow_inf_nan=False)


class Task(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    assignee: str = Field(default="", max_length=80)
    goal: str = Field(default="", max_length=80, description="goal id this task serves")
    needs_skill: str = Field(default="", max_length=80)
    status: Literal["open", "in_progress", "done", "blocked"] = "open"


class Goal(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=200)
    parent: str = Field(default="", max_length=80)


class OrgChartInput(BaseModel):
    action: Literal["validate", "chain", "delegate", "goal_path", "budget"]
    agents: list[Agent] = Field(min_length=1, max_length=200)
    tasks: list[Task] = Field(default_factory=list, max_length=500)
    goals: list[Goal] = Field(default_factory=list, max_length=200)
    agent: str = Field(default="", max_length=80, description="chain/delegate: the agent in question")
    task: str = Field(default="", max_length=80, description="delegate/goal_path: task id")
    alert_at: float = Field(default=0.8, gt=0, le=1, description="budget: fraction that raises an alert")


def _index(agents):
    by = {a.id: a for a in agents}
    return by, len(by) == len(agents)


def _problems(agents, tasks, goals):
    by, uniq = _index(agents)
    out = []
    if not uniq:
        out.append("duplicate agent ids")
    roots = [a.id for a in agents if not a.reports_to]
    if len(roots) != 1:
        out.append(f"expected exactly 1 top agent, found {len(roots)}: {sorted(roots)}")
    for a in agents:
        if a.reports_to and a.reports_to not in by:
            out.append(f"{a.id} reports to unknown agent {a.reports_to}")
        if a.reports_to == a.id:
            out.append(f"{a.id} reports to itself")
    for a in agents:  # cycle check
        seen, cur = {a.id}, a.reports_to
        while cur and cur in by:
            if cur in seen:
                out.append(f"reporting cycle through {a.id}")
                break
            seen.add(cur)
            cur = by[cur].reports_to
    tids = [t.id for t in tasks]
    if len(set(tids)) != len(tids):
        out.append("duplicate task ids")
    gids = {g.id for g in goals}
    for t in tasks:
        if t.assignee and t.assignee not in by:
            out.append(f"task {t.id} assigned to unknown agent {t.assignee}")
        if t.goal and t.goal not in gids:
            out.append(f"task {t.id} serves unknown goal {t.goal}")
    for g in goals:
        if g.parent and g.parent not in gids:
            out.append(f"goal {g.id} has unknown parent {g.parent}")
    return sorted(set(out))


def _chain(by, agent):
    chain, cur, guard = [], by[agent].reports_to, 0
    while cur and cur in by and guard < 500:
        chain.append(cur)
        cur, guard = by[cur].reports_to, guard + 1
    return chain


def _reports(agents, manager):
    kids = {}
    for a in agents:
        kids.setdefault(a.reports_to, []).append(a.id)
    out, stack = [], list(kids.get(manager, []))
    while stack:
        n = stack.pop()
        if n in out:
            continue
        out.append(n)
        stack.extend(kids.get(n, []))
    return out


def org_chart(inp: OrgChartInput) -> dict:
    by, _ = _index(inp.agents)
    probs = _problems(inp.agents, inp.tasks, inp.goals)
    base = {"executed": False, "spend_authorized": False}
    if inp.action == "validate":
        return {**base, "ok": not probs, "problems": probs, "agents": len(inp.agents),
                "tasks": len(inp.tasks), "goals": len(inp.goals)}
    if probs:
        return {**base, "ok": False, "error": "org is invalid; run validate", "problems": probs}
    if inp.action == "chain":
        if inp.agent not in by:
            return {**base, "ok": False, "error": f"unknown agent '{inp.agent}'"}
        return {**base, "ok": True, "agent": inp.agent, "escalation_path": _chain(by, inp.agent),
                "direct_reports": sorted(a.id for a in inp.agents if a.reports_to == inp.agent)}
    if inp.action == "goal_path":
        t = next((t for t in inp.tasks if t.id == inp.task), None)
        if not t:
            return {**base, "ok": False, "error": f"unknown task '{inp.task}'"}
        gb = {g.id: g for g in inp.goals}
        path, cur, guard = [], t.goal, 0
        while cur and cur in gb and guard < 200:
            path.append({"id": cur, "title": gb[cur].title})
            cur, guard = gb[cur].parent, guard + 1
        return {**base, "ok": True, "task": t.id, "goal_path": path,
                "note": "" if path else "task serves no goal"}
    if inp.action == "delegate":
        if inp.agent not in by:
            return {**base, "ok": False, "error": f"unknown agent '{inp.agent}'"}
        t = next((t for t in inp.tasks if t.id == inp.task), None)
        if not t:
            return {**base, "ok": False, "error": f"unknown task '{inp.task}'"}
        load = {a.id: sum(1 for x in inp.tasks if x.assignee == a.id and x.status in ("open", "in_progress"))
                for a in inp.agents}
        cands = []
        for r in _reports(inp.agents, inp.agent):
            a = by[r]
            if t.needs_skill and t.needs_skill not in a.skills:
                continue
            if a.budget_usd and a.spent_usd >= a.budget_usd:
                continue
            cands.append((load[r], r))
        cands.sort()
        if not cands:
            return {**base, "ok": True, "assign_to": None, "escalate_to": by[inp.agent].reports_to or None,
                    "reason": "no report under this agent has the skill and budget room"}
        return {**base, "ok": True, "assign_to": cands[0][1], "open_load": cands[0][0],
                "considered": [c[1] for c in cands]}
    # budget
    rows = []
    for a in inp.agents:
        team = [a.id] + _reports(inp.agents, a.id)
        budget = sum(by[x].budget_usd for x in team)
        spent = sum(by[x].spent_usd for x in team)
        frac = (spent / budget) if budget else None
        state = "no_budget" if not budget else ("paused" if spent >= budget else ("alert" if frac >= inp.alert_at else "ok"))
        rows.append({"agent": a.id, "team_budget": budget, "team_spent": spent,
                     "used": None if frac is None else round(frac, 3), "state": state})
    own = [{"agent": a.id, "state": "paused" if a.budget_usd and a.spent_usd >= a.budget_usd else "ok"} for a in inp.agents]
    return {**base, "ok": True, "rollup": rows, "own": own,
            "note": "Planning labels only. Nothing here pauses a real agent or limits real spend."}
