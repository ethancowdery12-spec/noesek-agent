"""Noesek safety-core wiring over the vendored upstream runtime (v3 S4).

Installed from noesek.upstream_boot before the vendored CLI starts. The
vendored tree stays byte-identical; every hook is a module-attribute wrap
applied at runtime:

- Noesek risk gate first: every command/code guard consults our approval
  engine (upstream detection tables). Hardline "block" verdicts are denied
  before the vendored gate runs - including under --yolo and permanent
  allowlists, which our gate suspends for calls we flag as approval-worthy.
- Durable turn spine: every gate decision (allow / force-approval / block /
  upstream outcome) is appended to <NOESEK_HOME>/state/turn-spine.jsonl.
  Conversation durability itself comes from the vendored hermes_state SQLite
  store, which lives under the same Noesek home via the boot env mapping.
"""
from __future__ import annotations

import contextvars
import json
import os
import time
from pathlib import Path

_FLAG = contextvars.ContextVar("noesek_force_approval", default=False)


def spine_path() -> Path:
    return Path(os.environ.get("NOESEK_HOME", "~/.noesek")).expanduser() / "state" / "turn-spine.jsonl"


def log_spine(event: dict) -> None:
    try:
        path = spine_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), **event}, sort_keys=True) + "\n")
    except OSError:
        pass  # spine is best-effort durable; never break the gate over I/O


def _summarize(result) -> str:
    if isinstance(result, dict):
        if result.get("approved"):
            return "allow"
        return result.get("outcome") or "deny"
    return "unknown"


def install() -> None:
    import tools.approval as ta
    if getattr(ta, "_noesek_wired", False):
        return
    from .approval_engine import assess_command

    orig_yolo = ta._yolo_active
    orig_allowlist = ta._command_matches_permanent_allowlist

    def yolo_guard() -> bool:
        return False if _FLAG.get() else orig_yolo()

    def allowlist_guard(command: str) -> bool:
        return False if _FLAG.get() else orig_allowlist(command)

    ta._yolo_active = yolo_guard
    ta._command_matches_permanent_allowlist = allowlist_guard

    def wrap(fn, kind: str):
        def inner(*args, **kwargs):
            target = str(args[0]) if args else str(kwargs.get("command") or kwargs.get("code") or "")
            assess = assess_command(target) if target else None
            preview = target[:200]
            if assess is not None and assess.blocked:
                log_spine({"type": "gate", "kind": kind, "decision": "block",
                           "pattern": assess.pattern, "reason": assess.reason, "cmd": preview})
                return {"approved": False,
                        "message": f"Noesek safety gate blocked this {kind.replace('_', ' ')}: {assess.reason}",
                        "pattern_key": assess.pattern or "", "description": assess.reason}
            forced = bool(assess is not None and assess.verdict == "approval")
            if forced:
                log_spine({"type": "gate", "kind": kind, "decision": "force-approval",
                           "pattern": assess.pattern, "reason": assess.reason, "cmd": preview})
            token = _FLAG.set(forced)
            try:
                result = fn(*args, **kwargs)
            finally:
                _FLAG.reset(token)
            if (forced and isinstance(result, dict) and result.get("approved")
                    and not result.get("user_consent")):
                # Our engine wants a human decision but the vendored path
                # auto-approved (yolo, allowlist, or simply not vendored-flagged).
                # Escalate to the vendored human gate ourselves.
                log_spine({"type": "gate", "kind": kind, "decision": "escalate",
                           "pattern": assess.pattern, "reason": assess.reason, "cmd": preview})
                result = ta._run_approval_gate(
                    pattern_key=assess.pattern or "noesek-risk",
                    description=assess.reason or "flagged by the Noesek risk gate",
                    display_target=target,
                    approval_callback=kwargs.get("approval_callback"),
                    subject=f"Command flagged by the Noesek risk gate ({assess.reason})",
                    noun="flagged commands",
                    advice="Find an alternative approach that avoids this command.",
                    autoapprove_log_prefix="AUTO-APPROVED Noesek-flagged command in non-interactive context")
            log_spine({"type": "gate", "kind": kind, "decision": _summarize(result),
                       "pattern": assess.pattern if assess else None, "cmd": preview})
            return result
        return inner

    ta.check_dangerous_command = wrap(ta.check_dangerous_command, "dangerous_command")
    ta.check_all_command_guards = wrap(ta.check_all_command_guards, "command_guards")
    ta.check_execute_code_guard = wrap(ta.check_execute_code_guard, "execute_code_guard")
    ta._noesek_wired = True
