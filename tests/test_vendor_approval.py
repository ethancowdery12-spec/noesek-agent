"""The vendored upstream approval stack is the live command-risk gate."""
import pytest
from pydantic import BaseModel
from noesek.core.approval_engine import assess_command, assess_tool_arguments
from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Approval, Conversation, Session, now
from datetime import timedelta


def test_hardline_root_wipe_blocked():
    r = assess_command("rm -rf /")
    assert r.verdict == "block" and "recursive delete" in r.reason

def test_hardline_fork_bomb_blocked():
    assert assess_command(":(){ :|:& };:").verdict == "block"

def test_sudo_stdin_password_pipe_blocked():
    assert assess_command("echo hunter2 | sudo -S apt update").verdict == "block"

def test_benign_command_allowed():
    assert assess_command("ls -la /tmp").verdict == "allow"

def test_quoted_prose_not_blocked():
    # Hardline never fires on quoted prose; upstream conservatively flags the
    # commit message as dangerous (approval), while plain prose stays allowed.
    assert assess_command('git commit -m "docs: never run rm -rf /"').verdict == "approval"
    assert assess_command('echo "shutdown is a word here"').verdict == "allow"

def test_dangerous_requires_approval():
    assert assess_command("git reset --hard HEAD~3").verdict == "approval"

def test_arguments_scanning_nested():
    r = assess_tool_arguments({"script": {"lines": ["ok", "mkfs.ext4 /dev/sda1"]}})
    assert r.verdict == "block"

class W(BaseModel):
    command: str = "ls"

async def _conv():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); return c.id

def _controller():
    async def handler(inp): return {"ok": True}
    def factory(cid):
        r = ToolRegistry(); r.register(ToolSpec("run", "d", W, Risk.WRITE, handler)); return r
    return Controller(registry_factory=factory)

async def test_hardline_command_never_creates_approvable_request(db):
    cid = await _conv()
    class LLM:
        async def complete(self, messages, schemas):
            class Call: id="c1"; name="run"; arguments={"command": "rm -rf /"}
            class Reply: content=None; tool_calls=[Call()]
            return Reply()
    c = _controller(); c.llm = LLM()
    r = await c.handle(cid, "please clean up")
    assert "Blocked by policy" in r.text and r.pending_approval_id is None

async def test_decide_approval_refuses_hardline_even_if_approved(db):
    cid = await _conv()
    async with Session() as s:
        a = Approval(conversation_id=cid, tool_name="run", arguments={"command": "dd if=/dev/zero of=/dev/sda"},
                     rationale="r", expires_at=now()+timedelta(hours=1))
        s.add(a); await s.commit(); aid = a.id
    r = await _controller().decide_approval(cid, aid, True)
    assert "cannot run" in r.text and "hardline" in r.text.lower()
