import time
from types import SimpleNamespace

import pytest

from noesek import hermes_ui as ui


# --- markdown stripping -----------------------------------------------------

def test_strip_markdown_prose():
    assert ui.strip_markdown("## Title\n**bold** and *italic*") == "Title\nbold and italic"

def test_strip_markdown_keeps_code_and_lists():
    src = "```python\n**not stripped**\n```\n- item **bold**"
    out = ui.strip_markdown(src)
    assert "**not stripped**" in out
    assert "- item bold" in out


# --- status bar -------------------------------------------------------------

def snap(**kw):
    base = dict(model="claude-sonnet-4", tokens_used=12_400, tokens_max=200_000,
                started_at=time.monotonic() - 900)
    base.update(kw)
    return ui.StatusSnapshot(base.pop("model"), base.pop("tokens_used"), base.pop("tokens_max"),
                             base.pop("started_at"), **base)

def test_status_bar_full_layout():
    line = ui.format_status_bar(snap(title="My Session", yolo=True), width=100, color=False)
    assert "☤ claude-sonnet-4" in line
    assert "12.4K/200K" in line
    assert "[█░░░░░░░░░] ~6%" in line
    assert "$" not in line and "n/a" in line
    assert "⚠ YOLO" in line
    assert "❖ My Session" in line
    assert "15m" in line

def test_status_bar_minimal_under_52():
    line = ui.format_status_bar(snap(), width=40, color=False)
    assert "12.4K" not in line and "☤ claude-sonnet-4" in line and "15m" in line

def test_status_bar_compact_52_to_75_has_no_title():
    line = ui.format_status_bar(snap(title="x" * 60), width=70, color=False)
    assert "❖" not in line and "[█" in line

def test_status_bar_color_thresholds():
    for pct, color in [(0.3, "#32CD32"), (0.6, "#FFD700"), (0.85, "#FF8C00"), (0.97, "#FF4500")]:
        line = ui.format_status_bar(snap(tokens_used=int(200_000 * pct)), width=100, color=True)
        assert ui._hex_fg(color) in line

def test_status_bar_long_model_truncated():
    line = ui.format_status_bar(snap(model="x" * 40), width=100, color=False)
    assert "x" * 25 + "…" in line


# --- shell mode --------------------------------------------------------------

def test_shell_kind():
    assert ui.shell_command_kind("") == "usage"
    assert ui.shell_command_kind("rm -rf /") == "dangerous"
    assert ui.shell_command_kind("git status") == "ok"

def test_run_shell_ok_and_exit_code(capsys, tmp_path):
    assert ui.run_shell("echo hello", cwd=tmp_path) == 0
    assert "hello" in capsys.readouterr().out
    assert ui.run_shell("exit 3", cwd=tmp_path) == 3
    assert "! exited 3" in capsys.readouterr().out

def test_run_shell_dangerous_refused(capsys, tmp_path):
    assert ui.run_shell("rm -rf /", cwd=tmp_path) == 2
    assert "refused" in capsys.readouterr().out


# --- registry ----------------------------------------------------------------

def test_registry_loads_full_manifest():
    reg = ui.load_slash_registry()
    assert len(reg) == 102
    names = {n for row in reg for n in row["names"]}
    assert "help" in names and "model" in names and "sessions" in names


# --- banner ------------------------------------------------------------------

def test_banner_contains_key_sections(capsys):
    ui.print_banner("anthropic/claude-sonnet-4", "/repo", ["terminal", "web_search"],
                    {"writing": ["notes"], "dev": ["repo-map"]}, session_id="42",
                    context_length=200_000, no_color=True)
    out = capsys.readouterr().out
    assert "claude-sonnet-4" in out and "/repo" in out and "Session: 42" in out
    assert "Available Tools" in out and "web_search" in out
    assert "Available Skills" in out and "notes" in out
    assert "2 tools" in out and "2 skills" in out and "/help for commands" in out
    assert "200K context" in out

def test_banner_unconfigured_model_warns(capsys):
    ui.print_banner("", "/repo", [], {}, no_color=True)
    assert "no model configured" in capsys.readouterr().out


# --- dispatcher ---------------------------------------------------------------

class FakeController:
    def __init__(self):
        self.handled = []

    async def handle(self, cid, text):
        self.handled.append(text)
        return SimpleNamespace(text=f"reply to {text}", citations=[], pending_approval_id=None)

    async def pending_approvals(self, cid):
        return SimpleNamespace(text="no pending approvals")

    async def decide_approval(self, cid, approval_id, approved):
        return SimpleNamespace(text=f"{'approved' if approved else 'rejected'} {approval_id}")


def make_disp(capsys=None):
    s = ui.ChatSession("test-user", model="test-model")
    s.conversation_id = 7
    s.controller = FakeController()
    lines = []
    disp = ui.SlashDispatcher(s, out=lines.append)
    return disp, s, lines


@pytest.mark.asyncio
async def test_dispatch_help_lists_registry():
    disp, s, lines = make_disp()
    assert await disp.dispatch("/help") is True
    text = "\n".join(lines)
    assert "/model" in text and "not executed yet" in text

@pytest.mark.asyncio
async def test_dispatch_quit_returns_false():
    disp, s, lines = make_disp()
    assert await disp.dispatch("/quit") is False
    assert await disp.dispatch("/exit") is False

@pytest.mark.asyncio
async def test_dispatch_title_and_status():
    disp, s, lines = make_disp()
    await disp.dispatch("/title My Session")
    assert s.title == "My Session"
    lines.clear()
    await disp.dispatch("/status")
    text = "\n".join(lines)
    assert "test-model" in text and "conversation: 7" in text

@pytest.mark.asyncio
async def test_dispatch_unknown_and_unimplemented():
    disp, s, lines = make_disp()
    await disp.dispatch("/definitely-not-real")
    assert "Unknown command" in lines[-1]
    row = next(r for r in disp.registry if r["name"] not in ui.IMPLEMENTED_SLASH)
    await disp.dispatch("/" + row["name"])
    assert "no safe Noesek execution yet" in lines[-1]

@pytest.mark.asyncio
async def test_dispatch_approve_reject_and_bad_id():
    disp, s, lines = make_disp()
    await disp.dispatch("/approve 12")
    assert "approved 12" in lines[-1]
    await disp.dispatch("/reject nope")
    assert "usage" in lines[-1]

@pytest.mark.asyncio
async def test_handle_line_routes_chat_shell_slash():
    disp, s, lines = make_disp()
    await disp.handle_line("hello there")
    assert s.controller.handled == ["hello there"]
    assert lines[-1] == "reply to hello there"
    assert s.history and s.tokens_used > 0
    await disp.handle_line("!echo hi")
    assert any("hi" == l or l.endswith("hi") for l in lines)

@pytest.mark.asyncio
async def test_retry_and_undo():
    disp, s, lines = make_disp()
    await disp.handle_line("first")
    await disp.dispatch("/retry")
    assert s.controller.handled == ["first", "first"]
    await disp.dispatch("/undo")
    assert len(s.history) == 1

def test_chat_session_token_estimate():
    s = ui.ChatSession("u")
    s.note_exchange("a" * 40, "b" * 40)
    assert s.tokens_used == 20
