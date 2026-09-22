import json

import pytest

from noesek.core import browser_state as bs

COOKIE = {"name": "sid", "value": "abc123", "domain": ".example.com", "path": "/",
          "expires": -1, "httpOnly": True, "secure": True, "sameSite": "Lax"}
OTHER = {"name": "tok", "value": "zzz999", "domain": ".other.org", "path": "/",
         "httpOnly": False, "secure": True}
STATE = {"cookies": [COOKIE], "origins": [{"origin": "https://example.com", "localStorage": [{"name": "k", "value": "v"}]}],
         "enabled": ["example.com"]}
SECRETS = ["abc123", "zzz999"]


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(bs.settings, "browser_state_key", "test-passphrase")


def test_encrypt_round_trip():
    blob = bs.encrypt_state(STATE)
    assert "abc123" not in blob
    assert bs.decrypt_state(blob) == STATE


def test_wrong_key_rejected(monkeypatch):
    blob = bs.encrypt_state(STATE)
    monkeypatch.setattr(bs.settings, "browser_state_key", "different-passphrase")
    with pytest.raises(bs.BrowserStateError):
        bs.decrypt_state(blob)


def test_no_key_rejected(monkeypatch):
    monkeypatch.setattr(bs.settings, "browser_state_key", "")
    with pytest.raises(bs.BrowserStateError):
        bs.encrypt_state(STATE)


def test_parse_cookies_txt():
    txt = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t1893456000\tsid\tabc123\n"
    cookies = bs.parse_cookies_txt(txt)
    assert cookies[0]["name"] == "sid" and cookies[0]["value"] == "abc123"
    assert cookies[0]["domain"] == ".example.com" and cookies[0]["secure"] is True


def test_parse_cookies_txt_httponly_prefix():
    txt = "#HttpOnly_.example.com\tTRUE\t/\tFALSE\t0\ttok\txyz\n"
    cookies = bs.parse_cookies_txt(txt)
    assert cookies[0]["httpOnly"] is True
    assert cookies[0]["domain"] == ".example.com"


def test_parse_import_storage_state_json():
    assert bs.parse_import(json.dumps(STATE)) == STATE["cookies"]


def test_parse_import_cookie_array_json():
    assert bs.parse_import(json.dumps([COOKIE])) == [COOKIE]


def test_parse_import_garbage():
    with pytest.raises(bs.BrowserStateError):
        bs.parse_import("not cookies at all {{{")


def test_summary_leaks_no_values():
    summary = bs.session_summary(STATE)
    assert summary["cookie_count"] == 1 and "example.com" in summary["domains"]
    assert summary["enabled"] == ["example.com"] and summary["pending"] == []
    assert "abc123" not in json.dumps(summary)


def test_merge_import_lands_disabled():
    state = {"cookies": [], "origins": [], "enabled": []}
    domains = bs.merge_import(state, [COOKIE, OTHER])
    assert domains == ["example.com", "other.org"]
    assert state["enabled"] == []  # imported domains are NOT auto-enabled
    summary = bs.session_summary(state)
    assert summary["pending"] == ["example.com", "other.org"]


def test_enable_then_scope_restore():
    state = {"cookies": [COOKIE, OTHER], "origins": [], "enabled": []}
    assert bs.set_enabled(state, "example.com", True) is True
    assert bs.set_enabled(state, "missing.net", True) is False
    got = bs.state_for_origin(state, "https://app.example.com")
    assert got["cookies"] == [COOKIE]  # subdomain match, enabled only
    got = bs.state_for_origin(state, "https://other.org")
    assert got["cookies"] == []  # stored but NOT enabled -> not restored


def test_revoke_domain():
    state = {"cookies": [COOKIE, OTHER], "origins": STATE["origins"][:], "enabled": ["example.com"]}
    removed = bs.revoke_domain(state, "example.com")
    assert removed == 1 and state["cookies"] == [OTHER] and state["enabled"] == []


def test_merge_export_preserves_other_domains_and_enablement():
    state = {"cookies": [COOKIE, OTHER], "origins": [], "enabled": ["example.com"]}
    updated = dict(COOKIE, value="newval")
    merged = bs.merge_export(state, {"cookies": [updated], "origins": []}, "https://example.com")
    vals = {c["name"]: c["value"] for c in merged["cookies"]}
    assert vals["sid"] == "newval" and vals["tok"] == "zzz999"
    assert merged["enabled"] == ["example.com"]


def test_restore_script_content():
    script = bs.restore_script(STATE["origins"])
    assert "localStorage" in script and "example.com" in script and '"k"' in script


async def test_save_load_audit_round_trip(db):
    from sqlalchemy import delete
    from noesek.db import BrowserAuditRow, BrowserStateRow, Session

    async with Session() as s:
        await s.execute(delete(BrowserStateRow))
        await s.execute(delete(BrowserAuditRow))
        await s.commit()
    assert await bs.load_state() is None
    await bs.save_state(STATE)
    loaded = await bs.load_state()
    assert loaded == STATE
    assert "abc123" not in json.dumps(bs.session_summary(loaded))
    await bs.audit("enable", "example.com")
    await bs.audit("restore", "https://example.com", "1 cookies, 1 origins")
    log = await bs.audit_log()
    assert [r["action"] for r in log] == ["enable", "restore"]
    assert not any(s in json.dumps(log) for s in SECRETS)


async def test_chat_tool_never_sees_or_shows_values(db):
    """The chat tool has no content field; its outputs are domain-only."""
    from sqlalchemy import delete
    from noesek.db import BrowserAuditRow, BrowserStateRow, Session
    from noesek.tools.browser_cookies import BrowserCookiesInput, browser_cookies

    assert "text" not in BrowserCookiesInput.model_fields
    assert "content" not in BrowserCookiesInput.model_fields
    async with Session() as s:
        await s.execute(delete(BrowserStateRow))
        await s.execute(delete(BrowserAuditRow))
        await s.commit()
    await bs.save_state({"cookies": [COOKIE, OTHER], "origins": [], "enabled": []})

    status = await browser_cookies(BrowserCookiesInput(action="status"))
    assert status["pending"] == ["example.com", "other.org"]
    out = await browser_cookies(BrowserCookiesInput(action="enable", domain="example.com"))
    assert out["enabled"] == "example.com"
    out = await browser_cookies(BrowserCookiesInput(action="revoke", domain="other.org"))
    assert out["cookies_removed"] == 1
    audit = await browser_cookies(BrowserCookiesInput(action="audit"))
    blob = json.dumps(status) + json.dumps(out) + json.dumps(audit)
    assert not any(s in blob for s in SECRETS)
    state = await bs.load_state()
    assert state["enabled"] == ["example.com"] and len(state["cookies"]) == 1


async def test_import_endpoint_flow(db):
    """Endpoint-equivalent: parse -> merge (disabled) -> save -> audit; the
    response payload carries domains and counts only."""
    from sqlalchemy import delete
    from noesek.db import BrowserAuditRow, BrowserStateRow, Session

    async with Session() as s:
        await s.execute(delete(BrowserStateRow))
        await s.execute(delete(BrowserAuditRow))
        await s.commit()
    body = "# Netscape\n.example.com\tTRUE\t/\tTRUE\t1893456000\tsid\tabc123\n"
    cookies = bs.parse_import(body)
    state = {"cookies": [], "origins": [], "enabled": []}
    domains = bs.merge_import(state, cookies)
    await bs.save_state(state)
    await bs.audit("import", ",".join(domains), f"{len(cookies)} cookies")
    response = {"imported": len(cookies), "domains": domains, "pending": domains}
    assert "abc123" not in json.dumps(response)
    loaded = await bs.load_state()
    assert loaded["enabled"] == [] and len(loaded["cookies"]) == 1
