"""Deterministic shell-command risk gate backed by the vendored Hermes approval stack.

This replaces Noesek's interface-level approval boundary with Hermes Agent's
battle-tested detection tables (vendored under noesek.vendor.hermes, MIT,
Nous Research): hardline blocks that no approval can override, the sudo -S
stdin guard, and dangerous-pattern classification. Noesek's own approval
persistence, expiry, and in-conversation flow stay authoritative; this gate
classifies what may even reach them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..vendor.hermes.tools.approval_detection import (
    _check_sudo_stdin_guard, detect_dangerous_command, detect_hardline_command)


@dataclass(frozen=True)
class CommandAssessment:
    verdict: str  # "allow" | "approval" | "block"
    reason: str = ""
    pattern: str | None = None

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"


_ALLOW = CommandAssessment("allow")


def assess_command(command: str) -> CommandAssessment:
    """Classify one shell command. Hardline and sudo-stdin matches are
    unconditional blocks - no approval, yolo mode, or cron mode may run them."""
    if not isinstance(command, str) or not command.strip():
        return _ALLOW
    is_hardline, description = detect_hardline_command(command)
    if is_hardline:
        return CommandAssessment("block", f"hardline: {description}", description)
    sudo_hit, sudo_description = _check_sudo_stdin_guard(command)
    if sudo_hit:
        return CommandAssessment("block", f"sudo-stdin: {sudo_description}", sudo_description)
    is_dangerous, pattern_key, danger_description = detect_dangerous_command(command)
    if is_dangerous:
        return CommandAssessment("approval", f"dangerous: {danger_description}", pattern_key)
    return _ALLOW


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _iter_strings(v)


def assess_tool_arguments(arguments: dict) -> CommandAssessment:
    """Classify every string in a tool call's arguments. The most severe
    finding wins: any hardline/sudo block vetoes the call outright; any
    dangerous match requires approval."""
    worst = _ALLOW
    for text in _iter_strings(arguments or {}):
        hit = assess_command(text)
        if hit.verdict == "block":
            return hit
        if hit.verdict == "approval" and worst.verdict == "allow":
            worst = hit
    return worst
