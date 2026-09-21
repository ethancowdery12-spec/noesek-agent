"""Live-test follow-up: /chat must resolve approvals like the channels do."""
import inspect

import noesek.computer.server as srv
from noesek.tools.humanize import humanize_text


def test_chat_handler_routes_approve_reject():
    src = inspect.getsource(srv.chat)
    assert "_APPROVE_RE.fullmatch" in src
    assert "decide_approval" in src


def test_approve_regex_matches_channel_shape():
    m = srv._APPROVE_RE.fullmatch("approve 3")
    assert m and m.group(1) == "approve" and m.group(2) == "3"
    assert srv._APPROVE_RE.fullmatch("Reject  12")
    assert not srv._APPROVE_RE.fullmatch("approved by 3 people")


def test_chat_handler_supports_pending():
    src = inspect.getsource(srv.chat)
    assert "pending_approvals" in src


def test_humanize_never_returns_empty_for_nonempty_input():
    out = humanize_text("I'd be happy to help you with that.")
    assert out["humanized_text"].strip()
    assert any(f["pattern"] == "all-filler input" for f in out["flags"])


def test_humanize_empty_input_stays_empty():
    out = humanize_text("   ")
    assert out["humanized_text"] == ""


def test_computer_service_starts_task_worker():
    """delegate_task enqueues jobs; the computer service must drain them."""
    src = inspect.getsource(srv._startup)
    assert "task_worker" in src
    assert "create_task" in src
    shutdown = inspect.getsource(srv._shutdown)
    assert "stop.set()" in shutdown
