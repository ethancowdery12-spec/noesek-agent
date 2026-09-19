"""Hermes-look interactive terminal UI for Noesek.

Layout, banner art, status-bar grammar, and interaction patterns follow the
MIT-licensed Hermes Agent (NousResearch/hermes-agent @ d7b836ab, see
docs/HERMES_CLI_COMPATIBILITY.md and docs/licenses). The caduceus and logo art
are copied verbatim from upstream hermes_cli/banner.py (MIT); everything else
is a Noesek implementation driving Noesek's thin controller. Execution never
imports Hermes' agent loop.

The UI runs on prompt_toolkit when installed (the upstream CLI's own toolkit)
and degrades to a plain input loop with identical dispatch when it is not.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .core.controller import Controller

# ---------------------------------------------------------------------------
# Styling (24-bit ANSI; prompt_toolkit and Windows Terminal both render VT)
# ---------------------------------------------------------------------------

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Skin fallbacks mirror upstream defaults (hermes_cli/skin_engine.py, MIT).
ACCENT = "#FFBF00"
DIM = "#B8860B"
TEXT = "#FFF8DC"
BORDER = "#CD7F32"
TITLE = "#FFD700"
SESSION_BORDER = "#8B8682"


def _hex_fg(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"\x1b[38;2;{r};{g};{b}m"


def paint(text: str, color: str | None = None, *, bold: bool = False, dim: bool = False) -> str:
    pre = (_BOLD if bold else "") + (_DIM if dim else "") + (_hex_fg(color) if color else "")
    return f"{pre}{text}{_RESET}" if pre else text


_MARKUP_RE = re.compile(r"\[(bold |dim )?(#[0-9A-Fa-f]{6})\](.*?)\[/\]", re.S)


def render_markup(template: str) -> str:
    """Render the small `[bold #RRGGBB]...[/]` subset used by the upstream art."""

    def _sub(m: re.Match) -> str:
        return paint(m.group(3), m.group(2), bold=bool(m.group(1) and "bold" in m.group(1)),
                     dim=bool(m.group(1) and "dim" in m.group(1)))

    prev = None
    while prev != template:
        prev = template
        template = _MARKUP_RE.sub(_sub, template)
    return template


def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


# ---------------------------------------------------------------------------
# Banner art (verbatim from upstream hermes_cli/banner.py @ d7b836ab, MIT)
# ---------------------------------------------------------------------------

HERMES_AGENT_LOGO = """[bold #FFD700]██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗       █████╗  ██████╗ ███████╗███╗   ██╗████████╗[/]
[bold #FFD700]██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝[/]
[#FFBF00]███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗█████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║[/]
[#FFBF00]██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║[/]
[#CD7F32]██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║[/]
[#CD7F32]╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝[/]"""

HERMES_CADUCEUS = """[#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⡀⠀⣀⣀⠀⢀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#CD7F32]⠀⠀⠀⠀⠀⠀⢀⣠⣴⣾⣿⣿⣇⠸⣿⣿⠇⣸⣿⣿⣷⣦⣄⡀⠀⠀⠀⠀⠀⠀[/]
[#FFBF00]⠀⢀⣠⣴⣶⠿⠋⣩⡿⣿⡿⠻⣿⡇⢠⡄⢸⣿⠟⢿⣿⢿⣍⠙⠿⣶⣦⣄⡀⠀[/]
[#FFBF00]⠀⠀⠉⠉⠁⠶⠟⠋⠀⠉⠀⢀⣈⣁⡈⢁⣈⣁⡀⠀⠉⠀⠙⠻⠶⠈⠉⠉⠀⠀[/]
[#FFD700]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣴⣿⡿⠛⢁⡈⠛⢿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#FFD700]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠿⣿⣦⣤⣈⠁⢠⣴⣿⠿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠻⢿⣿⣦⡉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢷⣦⣈⠛⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣴⠦⠈⠙⠿⣦⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⣿⣤⡈⠁⢤⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠷⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⠑⢶⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠁⢰⡆⠈⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⠈⣡⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]"""


# ---------------------------------------------------------------------------
# Status bar (mirrors upstream cli_status_bar_mixin.py grammar)
# ---------------------------------------------------------------------------

BAR_WIDTH = 10


def _context_bar(pct: float) -> str:
    filled = round(max(0.0, min(1.0, pct)) * BAR_WIDTH)
    return "[" + "█" * filled + "░" * (BAR_WIDTH - filled) + "]"


def _bar_color(pct: float) -> str:
    if pct < 0.50:
        return "#32CD32"  # green: plenty of room
    if pct < 0.80:
        return "#FFD700"  # yellow: getting full
    if pct < 0.95:
        return "#FF8C00"  # orange: approaching limit
    return "#FF4500"  # red: near overflow


def _fmt_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    v = f"{n / 1000:.1f}".rstrip("0").rstrip(".")
    return v + "K"


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


class StatusSnapshot:
    """Everything the status bar shows; all fields cheap to recompute."""

    def __init__(self, model: str, tokens_used: int, tokens_max: int, started_at: float,
                 *, cost: float | None = None, estimated: bool = True, compressions: int = 0,
                 background_tasks: int = 0, yolo: bool = False, title: str | None = None):
        self.model = model
        self.tokens_used = tokens_used
        self.tokens_max = tokens_max
        self.started_at = started_at
        self.cost = cost
        self.estimated = estimated
        self.compressions = compressions
        self.background_tasks = background_tasks
        self.yolo = yolo
        self.title = title


def format_status_bar(snap: StatusSnapshot, *, width: int | None = None, now: float | None = None,
                      color: bool = True) -> str:
    """Render the one-line status bar. Full layout >=76 cols, compact 52-75, minimal <52."""
    width = width or shutil.get_terminal_size().columns
    now = time.monotonic() if now is None else now
    model = snap.model if len(snap.model) <= 26 else snap.model[:25] + "…"
    duration = _fmt_duration(now - snap.started_at)
    p = lambda t, c=None, **kw: paint(t, c, **kw) if color else t
    head = p(" ☤ ", DIM) + p(model, TEXT, bold=True)
    if width < 52:  # minimal: model + duration (+ YOLO badge)
        tail = f" │ {duration}"
        if snap.yolo:
            tail += p(" ⚠ YOLO", "#FF4500", bold=True)
        return head + tail
    pct = (snap.tokens_used / snap.tokens_max) if snap.tokens_max else 0.0
    est = "~" if snap.estimated else ""
    tokens = f"{est}{_fmt_tokens(snap.tokens_used)}/{_fmt_tokens(snap.tokens_max)}"
    bar = p(_context_bar(pct), _bar_color(pct))
    cost = "n/a" if not snap.cost else f"${snap.cost:.2f}"
    parts = [head, tokens, f"{bar} {est}{pct:.0%}", cost]
    if snap.compressions:
        parts.append(f"🗜 {snap.compressions}")
    if snap.background_tasks:
        parts.append(f"▶ {snap.background_tasks}")
    parts.append(duration)
    line = " │ ".join(parts)
    if width >= 76:
        if snap.yolo:
            line += p(" ⚠ YOLO", "#FF4500", bold=True)
        if snap.title:
            budget = width - visible_len(line) - 3
            if budget > 8:
                title = snap.title if len(snap.title) <= budget else snap.title[: budget - 1] + "…"
                line += "  " + p(f"❖ {title}", TITLE)
    return line


# ---------------------------------------------------------------------------
# Markdown stripping for final replies (upstream behavior: prose, not source)
# ---------------------------------------------------------------------------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC_RE = re.compile(r"(?<!\w)\*([^*\n]+)\*(?!\w)")
_HEADING_RE = re.compile(r"^#{1,6}\s*", re.M)


def strip_markdown(text: str) -> str:
    """Strip bold/italic/heading markers from final replies; keep code blocks and lists."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        line = _HEADING_RE.sub("", line)
        line = _BOLD_RE.sub(r"\1", line)
        line = _ITALIC_RE.sub(r"\1", line)
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Slash command registry (generated manifest surface)
# ---------------------------------------------------------------------------


def load_slash_registry() -> list[dict]:
    manifest = Path(__file__).resolve().parent / "data" / "hermes-cli-manifest.json"
    rows = json.loads(manifest.read_text()).get("slash_commands", [])
    registry = []
    for row in rows:
        names = [row["name"], *(row.get("aliases") or [])]
        registry.append({
            "name": row["name"].lstrip("/"),
            "aliases": [a.lstrip("/") for a in row.get("aliases") or []],
            "description": row.get("description", ""),
            "args_hint": row.get("args_hint") or "",
            "names": [n.lstrip("/") for n in names],
        })
    return registry


# Commands this UI executes locally. Anything else in the registry is listed by
# /help but answers with an explicit not-yet note instead of pretending.
IMPLEMENTED_SLASH = {
    "help", "new", "reset", "clear", "history", "save", "title", "status", "context",
    "model", "tools", "skills", "sessions", "quit", "exit", "undo", "retry", "version",
    "pending", "approve", "reject", "usage", "compress",
}


# ---------------------------------------------------------------------------
# Welcome banner (panel + caduceus + tools/skills columns, upstream layout)
# ---------------------------------------------------------------------------


def _fmt_context_length(n: int | None) -> str:
    if not n:
        return ""
    return f"{n // 1000}K" if n >= 1000 else str(n)


def _short_model(model: str) -> str:
    short = model.split("/")[-1].removesuffix(".gguf")
    return short if len(short) <= 40 else short[:39] + "…"


def _truncate_names(names: list[str], budget: int = 42) -> list[str]:
    out: list[str] = []
    used = 0
    for n in names:
        if used + len(n) + 2 > budget:
            out.append("...")
            break
        out.append(n)
        used += len(n) + 2
    return out


def banner_lines(model: str, cwd: str, tools: list[str], skills: dict[str, list[str]],
                 *, session_id: str | None = None, context_length: int | None = None,
                 toolset_of=None, profile: str | None = None, no_color: bool = False) -> list[str]:
    """Build the banner body lines (no box); `print_banner` wraps them in a panel."""
    p = (lambda t, c=None, **kw: t) if no_color else paint
    left = ["", render_markup(HERMES_CADUCEUS) if not no_color else " (caduceus) ", ""]
    if model and model.lower() != "unknown":
        left.append(p(_short_model(model), ACCENT)
                    + (p(" · ", DIM) + p(f"{_fmt_context_length(context_length)} context", DIM) if context_length else "")
                    + p(" · ", DIM) + p("Nous Research CLI layout", DIM))
    else:
        left.append(p("no model configured", "#FF4500", bold=True) + p(" - run /model or noesek config", DIM))
    left.append(p(cwd, DIM))
    if session_id:
        left.append(p(f"Session: {session_id}", SESSION_BORDER))

    grouped: dict[str, list[str]] = {}
    for name in tools:
        ts = toolset_of(name) if toolset_of else "other"
        grouped.setdefault(ts, []).append(name)
    right = [p("Available Tools", ACCENT, bold=True)]
    for ts in sorted(grouped)[:8]:
        names = _truncate_names(sorted(grouped[ts]))
        right.append(p(f"{ts}:", DIM) + " " + ", ".join(p(n, TEXT) for n in names))
    if len(grouped) > 8:
        right.append(p(f"(and {len(grouped) - 8} more toolsets...)", DIM))

    right.append("")
    right.append(p("Available Skills", ACCENT, bold=True))
    total_skills = sum(len(v) for v in skills.values())
    if not skills:
        right.append(p("No skills installed", DIM))
    else:
        for cat in sorted(skills):
            packed = ", ".join(_truncate_names(sorted(skills[cat]), budget=60))
            right.append(p(f"{cat}:", DIM) + " " + p(packed, TEXT))
    right.append("")
    summary = [f"{len(tools)} tools", f"{total_skills} skills", "/help for commands"]
    if profile and profile != "default":
        right.append(p("Profile: ", ACCENT, bold=True) + p(profile, TEXT))
    right.append(p(" · ".join(summary), DIM))
    return left, right


def print_banner(model: str, cwd: str, tools: list[str], skills: dict[str, list[str]],
                 *, session_id: str | None = None, context_length: int | None = None,
                 toolset_of=None, profile: str | None = None, out=print, no_color: bool = False) -> None:
    left, right = banner_lines(model, cwd, tools, skills, session_id=session_id,
                               context_length=context_length, toolset_of=toolset_of,
                               profile=profile, no_color=no_color)
    p = (lambda t, c=None, **kw: t) if no_color else paint
    cols = shutil.get_terminal_size().columns
    if cols >= 95:
        out(render_markup(HERMES_AGENT_LOGO) if not no_color else "HERMES AGENT (Noesek)")
        out("")
    left_w = max((visible_len(l) for l in left), default=0)
    body = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        pad = " " * (left_w - visible_len(l) + 2)
        body.append(f"  {l}{pad}{r}")
    title = f" Hermes Agent (Noesek) v{__version__} "
    width = min(max((visible_len(b) for b in body), default=40) + 2, max(cols - 2, 44))
    out(p("╭" + "─" * 2 + title + "─" * max(0, width - visible_len(title) - 2) + "╮", BORDER))
    for b in body:
        out(p("│", BORDER) + b + " " * max(0, width - visible_len(b) - 1) + p("│", BORDER))
    out(p("╰" + "─" * width + "╯", BORDER))


# ---------------------------------------------------------------------------
# `!` shell mode (zero model turns; dangerous commands still gated)
# ---------------------------------------------------------------------------

# Same spirit as the approval-gated terminal tool: these never run from `!`
# without an explicit operator decision outside the chat loop.
_DANGEROUS_RE = re.compile(
    r"\brm\s+-[rf]|\brmdir\s+/s|\bformat\b|\bdel\s+/[fsq]|\bmkfs|\bdd\s+if=|:\(\)\s*\{|"
    r"\b(shutdown|reboot|poweroff)\b|\breg\s+(add|delete)\b|\bSet-ExecutionPolicy\b",
    re.I,
)


def shell_command_kind(text: str) -> str:
    if not text.strip():
        return "usage"
    if _DANGEROUS_RE.search(text):
        return "dangerous"
    return "ok"


def run_shell(text: str, *, cwd: Path, out=print) -> int:
    kind = shell_command_kind(text)
    if kind == "usage":
        out(paint("! <command> - run a shell command locally without spending a model turn", DIM))
        return 0
    if kind == "dangerous":
        out(paint("! refused: this matches the dangerous-command pattern. Run it yourself in a real "
                  "shell, or ask the agent so the approval gate can decide.", "#FF4500"))
        return 2
    proc = subprocess.run(text, shell=True, cwd=str(cwd), capture_output=True, text=True,
                          errors="replace", timeout=120)
    if proc.stdout:
        out(proc.stdout.rstrip("\n"))
    if proc.stderr:
        out(paint(proc.stderr.rstrip("\n"), "#FF8C00"))
    if proc.returncode:
        out(paint(f"! exited {proc.returncode}", "#FF4500"))
    return proc.returncode


# ---------------------------------------------------------------------------
# Interactive session: slash dispatch + chat loop
# ---------------------------------------------------------------------------


def _home() -> Path:
    return Path(os.environ.get("NOESEK_HOME", "~/.noesek")).expanduser()


class ChatSession:
    """State for one interactive run: controller conversation + status fields."""

    def __init__(self, user: str = "cli-user", *, model: str | None = None):
        self.user = user
        self.model = model or os.environ.get("NOESEK_MODEL", "unknown")
        self.context_length = int(os.environ.get("NOESEK_CONTEXT_LENGTH", "0")) or None
        self.started_at = time.monotonic()
        self.tokens_used = 0
        self.title: str | None = None
        self.compressions = 0
        self.background_tasks = 0
        self.conversation_id: int | None = None
        self.controller: Controller | None = None
        self.last_user: str | None = None
        self.last_assistant: str | None = None
        self.history: list[tuple[str, str]] = []

    async def open(self) -> None:
        from .cli import _conversation

        self.conversation_id = await _conversation(self.user)
        self.controller = Controller()

    def tool_names(self) -> list[str]:
        if self.controller is None or self.conversation_id is None:
            return []
        try:
            schemas = self.controller.registry(self.conversation_id).schemas()
        except Exception:
            return []
        return sorted(s.get("function", {}).get("name", "") for s in schemas if s.get("function"))

    def note_exchange(self, user_text: str, assistant_text: str) -> None:
        self.last_user, self.last_assistant = user_text, assistant_text
        self.history.append((user_text, assistant_text))
        # Local estimate, same convention as upstream's `~` marker: ~4 chars/token.
        self.tokens_used += (len(user_text) + len(assistant_text)) // 4

    def snapshot(self) -> StatusSnapshot:
        return StatusSnapshot(
            self.model, self.tokens_used, self.context_length or 200_000, self.started_at,
            cost=None, estimated=True, compressions=self.compressions,
            background_tasks=self.background_tasks,
            yolo=bool(os.environ.get("NOESEK_YOLO_MODE")), title=self.title)


HELP_NOTES = {
    "help": "Show command help",
    "new": "Start a fresh session (alias: /reset)",
    "clear": "Clear the screen and start a new session",
    "history": "Show this session's exchanges",
    "save": "Export this session to JSON under ~/.noesek/exports",
    "title": "Set a session title shown in the status bar",
    "status": "Session info and a local recap (no LLM call)",
    "context": "Context-usage breakdown for this session",
    "model": "Show the current model",
    "tools": "List the tools the agent can use right now",
    "skills": "List installed skills",
    "sessions": "List recent sessions",
    "undo": "Forget the last exchange in this session",
    "retry": "Resend your last message",
    "usage": "Token/cost breakdown for this session",
    "compress": "Note a compression boundary (controller compacts deterministically)",
    "pending": "List pending approvals (Noesek gate)",
    "approve": "Approve a pending action: /approve ID",
    "reject": "Reject a pending action: /reject ID",
    "quit": "Exit (alias: /exit)",
}


class SlashDispatcher:
    """Executes practical slash commands against Noesek state.

    Registry-driven: every upstream slash command resolves; the ones without a
    safe local implementation say so explicitly instead of being silently
    dropped (mirrors the hermes_cli exit-3 contract, in-session).
    """

    def __init__(self, session: ChatSession, out=print):
        self.session = session
        self.out = out
        self.registry = load_slash_registry()
        self._by_name = {}
        for row in self.registry:
            for n in row["names"]:
                self._by_name.setdefault(n.lower(), row)

    def known(self, name: str) -> dict | None:
        return self._by_name.get(name.lower())

    def help_text(self) -> str:
        lines = ["Slash commands (case-insensitive). * = runs locally in Noesek:"]
        done, todo = [], []
        for row in sorted(self.registry, key=lambda r: r["name"]):
            mark = "*" if row["name"] in IMPLEMENTED_SLASH else " "
            hint = f" {row['args_hint']}" if row.get("args_hint") else ""
            entry = f"  {mark} /{row['name']}{hint} - {row['description']}"
            (done if mark == "*" else todo).append(entry)
        lines += done
        if todo:
            lines.append("")
            lines.append("Parsed but not executed yet (explicit notice when used):")
            lines += todo
        lines.append("")
        lines.append("Noesek extras: /pending, /approve ID, /reject ID. Prefix with ! for shell mode.")
        return "\n".join(lines)

    async def dispatch(self, raw: str) -> bool:
        """Handle one `/...` line. Returns False only for /quit."""
        s = self.session
        out = self.out
        parts = raw[1:].split(maxsplit=1)
        name = parts[0].lower() if parts and parts[0] else "help"
        arg = parts[1] if len(parts) > 1 else ""
        row = self.known(name)
        if row:
            name = row["name"]
        if name in {"quit", "exit"}:
            return False
        if name == "help":
            out(self.help_text())
        elif name in {"new", "reset", "clear"}:
            if name == "clear":
                out("\x1b[2J\x1b[H")
            await s.open()
            s.history.clear()
            s.tokens_used = 0
            if arg:
                s.title = arg.split(" --", 1)[0].strip() or s.title
            out(paint(f"New session started (conversation {s.conversation_id}).", DIM))
        elif name == "history":
            if not s.history:
                out(paint("No exchanges yet.", DIM))
            for i, (u, a) in enumerate(s.history, 1):
                out(paint(f"[{i}] you> ", ACCENT) + u)
                out(paint("    agent> ", DIM) + a)
        elif name == "save":
            from . import cli_ops
            exports = _home() / "exports"
            exports.mkdir(parents=True, exist_ok=True)
            dest = exports / f"session-{s.conversation_id}.json"
            count = await cli_ops.session_export(s.conversation_id, dest)
            out(paint(f"Saved {count} messages to {dest}", DIM))
        elif name == "title":
            if not arg.strip():
                out(paint(f"Current title: {s.title or '(none)'}", DIM))
            else:
                s.title = arg.strip()
                out(paint(f"Session title set: {s.title}", DIM))
        elif name == "status":
            snap = s.snapshot()
            out(format_status_bar(snap, width=10_000))
            out(f"model: {s.model}")
            out(f"conversation: {s.conversation_id}   user: {s.user}")
            out(f"exchanges: {len(s.history)}   duration: {_fmt_duration(time.monotonic() - s.started_at)}")
            if s.last_user:
                out(paint("Session recap", ACCENT, bold=True))
                out(f"  last you> {s.last_user[:120]}")
                out(f"  last agent> {(s.last_assistant or '')[:120]}")
        elif name == "context":
            snap = s.snapshot()
            pct = snap.tokens_used / snap.tokens_max if snap.tokens_max else 0
            out(f"context: ~{_fmt_tokens(snap.tokens_used)}/{_fmt_tokens(snap.tokens_max)} "
                f"{_context_bar(pct)} ~{pct:.0%} (local estimate)")
            out(f"  conversation ~{_fmt_tokens(snap.tokens_used)}  system/tools/skills: see `noesek prompt-size`")
        elif name == "usage":
            out(f"tokens (est): ~{s.tokens_used}  cost: n/a (local estimate, provider usage not wired)")
        elif name == "model":
            out(f"{s.model}" + (f" ({_fmt_context_length(s.context_length)} context)" if s.context_length else ""))
        elif name == "tools":
            names = s.tool_names()
            out("\n".join(names) if names else "(no tools registered)")
        elif name == "skills":
            from .compat.skills import discover_skills
            rows = discover_skills([_home() / "skills", Path.cwd() / "skills"])
            out("\n".join(f"  {r.get('name', '?')} - {r.get('description', '')}" for r in rows)
                if rows else "(no skills installed)")
        elif name == "sessions":
            from . import cli_ops
            rows = await cli_ops.sessions_list(20)
            for r in rows:
                out(f"  {r.get('id')}: {r.get('title') or r.get('updated_at', '')}")
            if not rows:
                out("(no sessions)")
        elif name == "undo":
            if s.history:
                s.history.pop()
                out(paint("Last exchange forgotten (this session view).", DIM))
            else:
                out(paint("Nothing to undo.", DIM))
        elif name == "retry":
            if s.last_user:
                await self._ask(s.last_user)
            else:
                out(paint("Nothing to retry.", DIM))
        elif name == "compress":
            s.compressions += 1
            out(paint("Compression boundary noted; Noesek's controller compacts deterministically.", DIM))
        elif name == "pending":
            result = await s.controller.pending_approvals(s.conversation_id)
            out(result.text)
        elif name in {"approve", "reject"}:
            try:
                approval_id = int(arg.strip())
            except ValueError:
                out(paint(f"usage: /{name} ID", "#FF8C00"))
                return True
            result = await s.controller.decide_approval(s.conversation_id, approval_id, name == "approve")
            out(result.text)
        elif name == "version":
            out(f"hermes (Noesek compatibility) {__version__}")
        elif row is not None:
            out(paint(f"/{name} is recognized from the Hermes registry but has no safe Noesek "
                      f"execution yet - nothing ran. See docs/HERMES_CLI_COMPATIBILITY.md.", "#FF8C00"))
        else:
            out(paint(f"Unknown command /{name}. /help lists everything.", "#FF8C00"))
        return True

    async def _ask(self, text: str) -> None:
        s = self.session
        result = await s.controller.handle(s.conversation_id, text)
        reply = strip_markdown(result.text)
        s.note_exchange(text, reply)
        self.out(reply)

    async def handle_line(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return True
        if text.startswith("!"):
            run_shell(text[1:], cwd=Path.cwd(), out=self.out)
            return True
        if text.startswith("/"):
            return await self.dispatch(text)
        await self._ask(text)
        return True


def discover_skills_grouped() -> dict[str, list[str]]:
    from .compat.skills import discover_skills
    try:
        rows = discover_skills([_home() / "skills", Path.cwd() / "skills"])
    except Exception:
        return {}
    grouped: dict[str, list[str]] = {}
    for r in rows:
        grouped.setdefault(r.get("category") or "other", []).append(r.get("name", "?"))
    return grouped


# ---------------------------------------------------------------------------
# Interactive loop (prompt_toolkit when available; plain input fallback)
# ---------------------------------------------------------------------------


def _ptk_available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401
    except ImportError:
        return False
    return True


async def _loop_plain(disp: SlashDispatcher, session: ChatSession, out=print) -> None:
    out(paint("prompt_toolkit not installed - plain mode (pip install prompt-toolkit for the full UI).", DIM))
    while True:
        out(format_status_bar(session.snapshot(), width=shutil.get_terminal_size().columns))
        try:
            text = input(paint("> ", ACCENT, bold=True))
        except (EOFError, KeyboardInterrupt):
            out("")
            break
        if not await disp.handle_line(text):
            break


async def _loop_ptk(disp: SlashDispatcher, session: ChatSession, out=print) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style

    registry = disp.registry

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith("/") and " " not in text:
                word = text[1:].lower()
                for row in registry:
                    for n in row["names"]:
                        if n.startswith(word):
                            yield Completion("/" + n, start_position=-len(text),
                                             display_meta=row["description"])
            elif text.startswith("!"):
                return

    kb = KeyBindings()

    @kb.add("escape", "enter")  # multiline: Alt+Enter inserts a newline
    @kb.add("c-j")
    def _newline(event):
        event.current_buffer.insert_text("\n")

    style = Style.from_dict({"bottom-toolbar": "noreverse", "prompt": "bold"})
    hist = _home() / "cli_history"
    hist.parent.mkdir(parents=True, exist_ok=True)
    pt = PromptSession(history=FileHistory(str(hist)), completer=SlashCompleter(),
                       key_bindings=kb, style=style, multiline=False)

    def toolbar():
        return [("class:bottom-toolbar", format_status_bar(session.snapshot(), color=False))]

    interrupts = 0
    while True:
        try:
            text = await pt.prompt_async([("class:prompt", "> ")], bottom_toolbar=toolbar)
            interrupts = 0
        except KeyboardInterrupt:
            interrupts += 1
            if interrupts >= 2:
                break
            out(paint("(interrupt - press Ctrl+C again to exit)", DIM))
            continue
        except EOFError:
            break
        if not await disp.handle_line(text):
            break


async def run_interactive(user: str = "cli-user", *, model: str | None = None, out=print,
                          force_plain: bool = False) -> int:
    """Open an interactive Hermes-look session against the Noesek controller."""
    session = ChatSession(user, model=model)
    await session.open()
    print_banner(session.model, str(Path.cwd()), session.tool_names(), discover_skills_grouped(),
                 session_id=str(session.conversation_id), context_length=session.context_length,
                 out=out)
    disp = SlashDispatcher(session, out=out)
    if force_plain or not _ptk_available() or not sys.stdin.isatty():
        await _loop_plain(disp, session, out=out)
    else:
        await _loop_ptk(disp, session, out=out)
    return 0


def main(user: str = "cli-user", model: str | None = None) -> int:
    return asyncio.run(run_interactive(user, model=model))
