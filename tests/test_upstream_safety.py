"""Noesek safety-core wiring over the vendored approval gate (v3 S4)."""
import json

import pytest


@pytest.fixture
def gated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_HOME", str(tmp_path / "home"))
    import tools.approval as ta
    from noesek.core import upstream_safety
    monkeypatch.delattr(ta, "_noesek_wired", raising=False)
    upstream_safety.install()
    yield ta, upstream_safety
    # unwrap for other tests
    for name in ("check_dangerous_command", "check_all_command_guards", "check_execute_code_guard"):
        f = getattr(ta, name)
        while hasattr(f, "__wrapped__"):
            f = f.__wrapped__
    # reload to drop wraps
    import importlib
    importlib.reload(ta)


def _spine(us):
    p = us.spine_path()
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_hardline_block_denies_even_under_yolo(gated, monkeypatch):
    ta, us = gated
    monkeypatch.setenv("HERMES_YOLO", "1")  # best-effort; direct block happens before yolo consult
    # a hardline command our engine blocks (fork bomb class)
    import noesek.core.approval_engine as ae
    blocked_cmd = None
    for cand in ("mkfs.ext4 /dev/sda", ":(){ :|:& };:", "dd if=/dev/zero of=/dev/sda"):
        if ae.assess_command(cand).blocked:
            blocked_cmd = cand
            break
    assert blocked_cmd, "expected a hardline-blocked candidate"
    r = ta.check_dangerous_command(blocked_cmd, "host")
    assert r["approved"] is False
    spine = _spine(us)
    assert any(e["decision"] == "block" for e in spine)


def test_approval_verdict_escalates_to_human_gate(gated, monkeypatch):
    ta, us = gated
    import noesek.core.approval_engine as ae
    from tools.approval_detection import detect_dangerous_command
    # candidate our engine flags as approval-worthy that the vendored
    # pattern detector does NOT flag (so the vendored path would auto-approve)
    approval_cmd = None
    for cand in ("rm -rf /tmp/important", "git push --force origin main", "chmod -R 777 /",
                 "kill -9 1", "shutdown now"):
        a = ae.assess_command(cand)
        vendored_flag = detect_dangerous_command(cand)[0]
        if a.verdict == "approval" and not vendored_flag:
            approval_cmd = cand
            break
    if approval_cmd is None:
        # fall back: any approval-class command; the force-flag path covers it
        for cand in ("rm -rf /tmp/important", "git push --force origin main", "chmod -R 777 /"):
            if ae.assess_command(cand).verdict == "approval":
                approval_cmd = cand
                break
    assert approval_cmd, "no approval-class candidate in current tables"
    calls = {}
    def fake_gate(**kwargs):
        calls["reached"] = True
        return {"approved": True, "message": None, "user_consent": True}
    monkeypatch.setattr(ta, "_run_approval_gate", fake_gate)
    r = ta.check_dangerous_command(approval_cmd, "host")
    assert calls.get("reached"), "approval-class command must reach the human gate"
    assert r["approved"] is True
    decisions = [e["decision"] for e in _spine(us)]
    assert "force-approval" in decisions


def test_allow_decision_is_logged_to_spine(gated):
    ta, us = gated
    r = ta.check_dangerous_command("ls -la", "host")
    assert r["approved"] is True
    assert any(e["decision"] == "allow" and e["cmd"] == "ls -la" for e in _spine(us))


def test_install_is_idempotent(gated):
    from noesek.core import upstream_safety
    import tools.approval as ta
    first = ta.check_dangerous_command
    upstream_safety.install()
    assert ta.check_dangerous_command is first
