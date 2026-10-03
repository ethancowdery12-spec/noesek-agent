from noesek.tools.org_chart import OrgChartInput as I, org_chart as f

A = [dict(id="ceo", budget_usd=100, spent_usd=10),
     dict(id="cto", reports_to="ceo", skills=["infra"], budget_usd=50, spent_usd=45),
     dict(id="net", reports_to="cto", skills=["network"], budget_usd=20, spent_usd=5),
     dict(id="sto", reports_to="cto", skills=["storage", "network"], budget_usd=20, spent_usd=20)]
T = [dict(id="t1", assignee="net", goal="g2", status="in_progress"), dict(id="t2", goal="g2", needs_skill="network")]
G = [dict(id="g1", title="Fix NAS"), dict(id="g2", title="Stop disconnects", parent="g1")]


def run(action, **kw):
    return f(I(action=action, agents=kw.pop("agents", A), tasks=kw.pop("tasks", T), goals=kw.pop("goals", G), **kw))


def test_validate_ok_and_problems():
    assert run("validate")["ok"] is True
    bad = [dict(id="a", reports_to="b"), dict(id="b", reports_to="a")]
    r = run("validate", agents=bad, tasks=[], goals=[])
    assert not r["ok"] and any("cycle" in p for p in r["problems"]) and any("top agent" in p for p in r["problems"])
    r = run("validate", agents=A + [dict(id="x", reports_to="ghost")])
    assert any("unknown agent ghost" in p for p in r["problems"])
    r = run("validate", tasks=[dict(id="t", assignee="zz", goal="gx")])
    assert len([p for p in r["problems"] if "unknown" in p]) == 2


def test_chain_and_direct_reports():
    r = run("chain", agent="net")
    assert r["escalation_path"] == ["cto", "ceo"]
    assert run("chain", agent="cto")["direct_reports"] == ["net", "sto"]
    assert run("chain", agent="nobody")["ok"] is False


def test_delegate_picks_skill_and_skips_exhausted_budget():
    r = run("delegate", agent="cto", task="t2")
    assert r["assign_to"] == "net"  # sto has the skill but its budget is spent
    r = run("delegate", agent="net", task="t2")
    assert r["assign_to"] is None and r["escalate_to"] == "cto"


def test_goal_path_and_missing_goal():
    r = run("goal_path", task="t1")
    assert [g["id"] for g in r["goal_path"]] == ["g2", "g1"]
    r = run("goal_path", task="t3", tasks=T + [dict(id="t3")])
    assert r["goal_path"] == [] and r["note"]


def test_budget_rollup_states():
    r = run("budget", alert_at=0.7)
    by = {x["agent"]: x for x in r["rollup"]}
    assert by["cto"]["team_budget"] == 90 and by["cto"]["team_spent"] == 70 and by["cto"]["state"] == "alert"
    assert by["ceo"]["state"] == "ok" and {o["agent"]: o["state"] for o in r["own"]}["sto"] == "paused"
    assert r["spend_authorized"] is False and r["executed"] is False


def test_invalid_org_blocks_other_actions():
    r = f(I(action="chain", agents=[dict(id="a", reports_to="a")], agent="a"))
    assert r["ok"] is False and r["problems"]
