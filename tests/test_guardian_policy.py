"""Guardian owner policy store: integrity, fail-closed semantics, floor
precedence, matching, and gate integration. No laya, no model."""
import json
import os

import pytest

from noesek.config import settings
from noesek.guardian import gate as gate_mod
from noesek.guardian import policy


@pytest.fixture()
def policy_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "pol")
    monkeypatch.setattr(settings, "guardian_policy_dir", d)
    return d


def _write(rules, known_tools=None):
    return policy.write_policy(rules, answers_summary="test", known_tools=known_tools or [])


def test_unconfigured_passes_model_verdict_through(policy_dir):
    for v in ("allow", "escalate", "deny"):
        assert policy.apply("gmail_send", 0.9, 0.1, "destructive", v) == (v, None)


def test_floor_beats_allow_pin(policy_dir):
    _write([{"match": "tool", "pattern": "read_file", "kind": "pin", "band": "allow", "note": ""}])
    verdict, tag = policy.apply("read_file", 0.9, 0.0, "credential_access", "deny")
    assert verdict == "deny" and tag == "floor"


def test_floor_classes_all_protected(policy_dir):
    _write([{"match": "tool", "pattern": "t", "kind": "pin", "band": "allow", "note": ""}])
    for cls in ("credential_access", "exfiltration", "remote_exec"):
        assert policy.apply("t", 0.9, 0.0, cls, "deny")[0] == "deny"


def test_destructive_pin_allow_softens(policy_dir):
    # payments/deletes land in destructive/external bands: owner-overridable by design
    _write([{"match": "tool", "pattern": "payments_send", "kind": "pin", "band": "allow", "note": ""}])
    assert policy.apply("payments_send", 0.9, 0.0, "destructive", "deny") == ("allow", "pin:payments_send")


def test_pin_escalate(policy_dir):
    _write([{"match": "tool", "pattern": "gmail_send", "kind": "pin", "band": "escalate", "note": ""}])
    assert policy.apply("gmail_send", 0.0, 0.0, "read_only", "allow") == ("escalate", "pin:gmail_send")


def test_prefix_floor_raises_severity(policy_dir):
    _write([{"match": "prefix", "pattern": "strava.", "kind": "floor", "band": "escalate", "note": ""}])
    assert policy.apply("strava.upload", 0.0, 0.0, "read_only", "allow") == ("escalate", "floor:strava.")
    # a model deny stays deny (floor never lowers)
    assert policy.apply("strava.delete", 0.9, 0.0, "destructive", "deny")[0] == "deny"


def test_exact_beats_prefix_and_longest_prefix_wins(policy_dir):
    _write([
        {"match": "prefix", "pattern": "a.", "kind": "pin", "band": "escalate", "note": ""},
        {"match": "prefix", "pattern": "a.b.", "kind": "pin", "band": "deny", "note": ""},
        {"match": "tool", "pattern": "a.b.c", "kind": "pin", "band": "allow", "note": ""},
    ])
    assert policy.apply("a.b.c", 0.0, 0.0, "read_only", "deny")[0] == "allow"
    assert policy.apply("a.b.d", 0.0, 0.0, "read_only", "allow")[0] == "deny"
    assert policy.apply("a.x", 0.0, 0.0, "read_only", "allow")[0] == "escalate"


def test_new_tool_default_escalates_unknown_tools(policy_dir):
    _write([], known_tools=["gmail_send", "calendar_read"])
    assert policy.apply("acme.new_tool", 0.0, 0.0, "read_only", "allow") == ("escalate", "new_tool_default")
    assert policy.apply("gmail_send", 0.0, 0.0, "read_only", "allow") == ("allow", None)


def test_cap_lowers_severity(policy_dir):
    _write([{"match": "tool", "pattern": "t", "kind": "cap", "band": "escalate", "note": ""}])
    assert policy.apply("t", 0.9, 0.0, "destructive", "deny")[0] == "escalate"
    assert policy.apply("t", 0.0, 0.0, "read_only", "allow")[0] == "allow"


def test_tampered_file_fails_closed(policy_dir):
    path = _write([{"match": "tool", "pattern": "t", "kind": "pin", "band": "allow", "note": ""}])
    assert policy.apply("t", 0.0, 0.0, "read_only", "escalate")[0] == "allow"
    raw = open(path, "rb").read()
    i = raw.index(b'"allow"')
    open(path, "wb").write(raw[:i] + b'"all0w"' + raw[i + 7:])
    with pytest.raises(policy.PolicyError):
        policy.apply("t", 0.0, 0.0, "read_only", "escalate")


def test_missing_file_after_setup_fails_closed(policy_dir):
    path = _write([])
    os.unlink(path)
    with pytest.raises(policy.PolicyError):
        policy.apply("t", 0.0, 0.0, "read_only", "allow")


def test_foreign_key_fails_closed(policy_dir, tmp_path, monkeypatch):
    _write([])
    # re-point at a second store and write there: different random key
    d2 = str(tmp_path / "other")
    monkeypatch.setattr(settings, "guardian_policy_dir", d2)
    _write([])
    # files from the first store must not verify under the second store's key
    src = os.path.join(policy_dir, "guardian_policy.json")
    dst = os.path.join(d2, "guardian_policy.json")
    import shutil
    shutil.copy(src, dst)
    with pytest.raises(policy.PolicyError):
        policy.apply("t", 0.0, 0.0, "read_only", "allow")


def test_invalid_marker_treated_as_configured(policy_dir):
    _write([])
    with open(os.path.join(policy_dir, "guardian_policy.configured"), "wb") as f:
        f.write(b'{"payload": {"configured": true}, "signature": "bogus"}')
    assert policy.is_configured() is True


def test_bad_rule_schema_rejected(policy_dir):
    with pytest.raises(policy.PolicyError):
        _write([{"match": "tool", "pattern": "t", "kind": "pin", "band": "yolo", "note": ""}])
    with pytest.raises(policy.PolicyError):
        _write([{"match": "regex", "pattern": ".*", "kind": "pin", "band": "allow", "note": ""}])


@pytest.mark.asyncio
async def test_gate_denies_closed_on_policy_error(policy_dir, monkeypatch):
    path = _write([])
    os.unlink(path)  # configured marker present, policy file gone -> fail closed
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_remote", False)
    monkeypatch.setattr(gate_mod._scorer, "score_state",
                        lambda model_dir, state: {"deny_score": 0.0, "esc_prob": 0.0, "top_risk": "read_only"})
    v = await gate_mod.gate_tool_call("calendar_read", {"q": "x"}, "r", "c")
    assert v is not None and v.verdict == "deny" and "policy store invalid" in (v.error or "")


@pytest.mark.asyncio
async def test_gate_applies_owner_rule(policy_dir, monkeypatch):
    _write([{"match": "tool", "pattern": "gmail_send", "kind": "pin", "band": "escalate", "note": ""}])
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_remote", False)
    monkeypatch.setattr(gate_mod._scorer, "score_state",
                        lambda model_dir, state: {"deny_score": 0.0, "esc_prob": 0.0, "top_risk": "read_only"})
    v = await gate_mod.gate_tool_call("gmail_send", {"to": "me"}, "r", "c")
    assert v is not None and v.verdict == "escalate" and v.error is None
