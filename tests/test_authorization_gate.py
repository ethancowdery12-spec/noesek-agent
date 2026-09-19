"""Contract tests for Noesek's authorization gate over the vendored Hermes authz chain."""
import os

import pytest

from noesek.channels.authorization import (NoesekAuthorizationGate,
                                           canonical_whatsapp_identifier,
                                           normalize_whatsapp_identifier,
                                           to_whatsapp_jid)


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.delenv("WHATSAPP_ALLOWED_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOW_ALL_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOWED_USERS", raising=False)
    return NoesekAuthorizationGate(home=tmp_path)


def wa(gate, sender, **kw):
    return gate.make_source(platform="whatsapp", chat_id=sender, user_id=sender, **kw)


def test_deny_by_default(gate):
    assert gate.is_authorized(wa(gate, "15550001111")) is False


def test_settings_allowlist_projection(gate, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "15550001111, +15550002222")
    assert gate.is_authorized(wa(gate, "15550001111")) is True
    assert gate.is_authorized(wa(gate, "+15550002222")) is True
    assert gate.is_authorized(wa(gate, "15550003333")) is False


def test_operator_env_wins_over_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "999")
    gate = NoesekAuthorizationGate(home=tmp_path,
                                   allowlists={"whatsapp": "15550001111"})
    assert os.environ["WHATSAPP_ALLOWED_USERS"] == "999"
    assert gate.is_authorized(wa(gate, "999")) is True
    assert gate.is_authorized(wa(gate, "15550001111")) is False


def test_pairing_handshake_grant(gate):
    src = wa(gate, "15550004444")
    assert gate.is_authorized(src) is False
    code = gate.start_pairing("whatsapp", "15550004444", "Sam")
    assert code
    assert gate.is_authorized(src) is False
    approved = gate.approve_code("whatsapp", code)
    assert approved is not None
    assert gate.is_authorized(src) is True
    assert gate.revoke("whatsapp", "15550004444") is True
    assert gate.is_authorized(src) is False


def test_lid_and_jid_aliases_share_identity(gate, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "15550001111")
    lid = gate.make_source(platform="whatsapp", chat_id="15550001111@lid",
                           user_id="15550001111:47@s.whatsapp.net")
    assert gate.is_authorized(lid) is True


def test_unauthorized_dm_behaviors(gate):
    assert gate.unauthorized_dm_behavior("whatsapp") == "pair"
    gate_ignore = NoesekAuthorizationGate(home=gate.pairing_store._dir.parent.parent,
                                          unauthorized_dm_behavior="ignore")
    assert gate_ignore.unauthorized_dm_behavior("whatsapp") == "ignore"


def test_bot_loop_guard_bounds_bot_traffic(gate, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "*")
    src = wa(gate, "15550007777", is_bot=True)
    for _ in range(20):
        assert gate.admit_bot_message(src) is True
    assert gate.admit_bot_message(src) is False  # budget exhausted
    assert gate.is_authorized(src) is False  # guard overrides allowlist while tripped


def test_whatsapp_identity_helpers():
    assert normalize_whatsapp_identifier("6012:47@s.whatsapp.net") == "6012"
    assert to_whatsapp_jid("+1 555 000-1111") == "15550001111@s.whatsapp.net"
    assert canonical_whatsapp_identifier("+15550001111") == "15550001111"
