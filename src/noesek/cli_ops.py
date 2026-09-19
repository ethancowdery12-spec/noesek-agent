"""Operational CLI helpers.

The command surface is independently implemented for Noesek. Its design was
informed by the public Hermes Agent CLI documentation; no Hermes source is
vendored or imported here.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

_SECRET_PARTS = ("key", "token", "secret", "password")


def _redact(name: str, value: Any) -> Any:
    return "***configured***" if value and any(p in name.lower() for p in _SECRET_PARTS) else value


def config_snapshot() -> dict[str, Any]:
    from .config import settings
    return {name: _redact(name, getattr(settings, name)) for name in type(settings).model_fields}


def config_get(name: str) -> Any:
    data = config_snapshot()
    if name not in data:
        raise KeyError(name)
    return data[name]


def doctor_report() -> dict[str, Any]:
    from .config import settings
    py_ok = sys.version_info >= (3, 11)
    checks = {
        "python": {"ok": py_ok, "detail": platform.python_version() + " (requires >=3.11)"},
        "database_url": {"ok": bool(settings.database_url), "detail": "configured" if settings.database_url else "missing"},
        "llm": {"ok": bool(settings.llm_api_key and settings.llm_model), "detail": "configured" if settings.llm_api_key and settings.llm_model else "missing key/model"},
        "whatsapp": {"ok": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id and settings.meta_app_secret), "detail": "configured" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id and settings.meta_app_secret else "missing credentials"},
        "docker": {"ok": shutil.which("docker") is not None, "detail": shutil.which("docker") or "not found"},
    }
    return {"ok": all(v["ok"] for v in checks.values()), "checks": checks}


async def status_report() -> dict[str, Any]:
    from .core.heartbeat import heartbeat_status
    from .db import Approval, Conversation, Message, Session, Task, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        async def count(model, *where):
            return int((await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one())
        return {
            "conversations": await count(Conversation),
            "messages": await count(Message),
            "tasks_pending": await count(Task, Task.status.in_(("pending", "running"))),
            "approvals_pending": await count(Approval, Approval.status == "pending"),
            "heartbeats": heartbeat_status(),
        }


async def sessions_list(limit: int = 20) -> list[dict[str, Any]]:
    from .db import Conversation, Message, Session, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        q = (select(Conversation.id, Conversation.channel, Conversation.external_user_id,
                    Conversation.created_at, Conversation.title, func.count(Message.id).label("messages"),
                    func.max(Message.created_at).label("updated_at"))
             .outerjoin(Message, Message.conversation_id == Conversation.id)
             .group_by(Conversation.id).order_by(func.max(Message.created_at).desc()).limit(limit))
        rows = (await s.execute(q)).all()
    return [{"id": r.id, "channel": r.channel, "external_user_id": r.external_user_id, "title": r.title,
             "messages": r.messages, "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at)} for r in rows]


async def session_export(session_id: int, output: Path) -> int:
    from .db import Conversation, Message, Session, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        conv = (await s.execute(select(Conversation).where(Conversation.id == session_id))).scalar_one_or_none()
        if conv is None: raise LookupError(session_id)
        messages = (await s.execute(select(Message).where(Message.conversation_id == session_id).order_by(Message.created_at, Message.id))).scalars().all()
    payload = {"schema": "noesek.session.v1", "exported_at": datetime.now(timezone.utc).isoformat(),
               "session": {"id": conv.id, "channel": conv.channel, "external_user_id": conv.external_user_id,
                           "created_at": _iso(conv.created_at)},
               "messages": [{"id": m.id, "role": m.role, "content": m.content,
                             "external_id": m.external_id, "created_at": _iso(m.created_at)} for m in messages]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(messages)


async def session_delete(session_id: int) -> None:
    from .db import Approval, Conversation, Memory, Message, Session, Task, Trace, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        conv = (await s.execute(select(Conversation).where(Conversation.id == session_id))).scalar_one_or_none()
        if conv is None: raise LookupError(session_id)
        for model in (Message, Memory, Task, Approval, Trace):
            await s.execute(delete(model).where(model.conversation_id == session_id))
        await s.delete(conv); await s.commit()


def prompt_size_report() -> dict[str, int]:
    from .core.context import SYSTEM
    from .core.controller import Controller
    schemas = json.dumps(Controller().registry(0).schemas(), ensure_ascii=False)
    return {"system_prompt_bytes": len(SYSTEM.encode()), "tool_schemas_bytes": len(schemas.encode()),
            "total_bytes": len(SYSTEM.encode()) + len(schemas.encode())}


def backup(destination: Path) -> list[str]:
    from .config import settings
    files: list[Path] = []
    if settings.database_url.startswith("sqlite"):
        raw = settings.database_url.rsplit("///", 1)[-1]
        db = Path(raw)
        if db.exists(): files.append(db)
    for name in (".env", "README.md", "THIRD_PARTY_NOTICES.md"):
        p = Path(name)
        if p.exists(): files.append(p)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files: z.write(p, arcname=p.name)
    return [p.name for p in files]


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def postmortem(incident_id: str) -> str:
    """Local markdown postmortem from the vendored incident store - no model calls."""
    from .vendor.hermes.cron import incidents
    inc = incidents.get_incident(incident_id)
    if not inc:
        raise KeyError(incident_id)
    lines = [
        f"# Postmortem: {inc['job_id']}",
        "",
        f"- Incident: {inc['id']}",
        f"- State: {inc['state']}",
        f"- Failure type: {inc.get('failure_type') or 'unclassified'}",
        f"- First seen: {inc.get('first_seen_at')}",
        f"- Last seen: {inc.get('last_seen_at')}",
        "",
        "## Error signature",
        "",
        "```",
        (inc.get("error") or "")[:2000],
        "```",
        "",
        "## Timeline",
        "",
        "(fill in from the execution ledger)",
        "",
        "## Root cause",
        "",
        "(operator analysis)",
        "",
        "## Follow-ups",
        "",
        "- [ ] ",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# v2.1: sessions analysis, insights, dump, logs, pause (hermes adapters)
# ---------------------------------------------------------------------------


def noesek_home() -> Path:
    return Path(os.environ.get("NOESEK_HOME", "~/.noesek")).expanduser()


def pause_file() -> Path:
    return noesek_home() / "PAUSED"


def is_paused() -> dict[str, Any]:
    f = pause_file()
    if not f.exists():
        return {"paused": False}
    try:
        meta = json.loads(f.read_text())
    except Exception:
        meta = {}
    return {"paused": True, "reason": meta.get("reason"), "since": meta.get("since")}


def set_paused(paused: bool, reason: str | None = None) -> dict[str, Any]:
    f = pause_file()
    if paused:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"reason": reason, "since": datetime.now(timezone.utc).isoformat()}))
    else:
        f.unlink(missing_ok=True)
    return is_paused()


async def session_rename(session_id: int, title: str) -> dict[str, Any]:
    from .db import Conversation, Session, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        conv = (await s.execute(select(Conversation).where(Conversation.id == session_id))).scalar_one_or_none()
        if conv is None: raise LookupError(session_id)
        conv.title = title; await s.commit()
    return {"id": session_id, "title": title}


async def sessions_prune(older_than_days: int, *, yes: bool = False, keep_min: int = 5) -> dict[str, Any]:
    """Delete sessions whose last message is older than the cutoff. Keeps at least keep_min."""
    from .db import Conversation, Message, Session, init_db, migrate
    await init_db(); await migrate()
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    async with Session() as s:
        q = (select(Conversation.id, func.max(Message.created_at).label("updated_at"))
             .outerjoin(Message, Message.conversation_id == Conversation.id)
             .group_by(Conversation.id).order_by(func.max(Message.created_at).desc().nullslast()))
        rows = (await s.execute(q)).all()
    stale = [r.id for r in rows[keep_min:] if r.updated_at is None or r.updated_at.replace(tzinfo=timezone.utc) < cutoff]
    if not yes:
        return {"would_prune": stale, "count": len(stale), "confirm": "rerun with --yes to delete"}
    for sid in stale:
        await session_delete(sid)
    return {"pruned": stale, "count": len(stale)}


async def session_stats(session_id: int) -> dict[str, Any]:
    """Per-session analysis: turns, tools, tokens, duration from the turn spine."""
    from .db import Message, Session, TurnEvent, init_db, migrate
    await init_db(); await migrate()
    async with Session() as s:
        roles = (await s.execute(select(Message.role, func.count()).where(Message.conversation_id == session_id)
                                 .group_by(Message.role))).all()
        events = (await s.execute(select(TurnEvent).where(TurnEvent.conversation_id == session_id)
                                  .order_by(TurnEvent.created_at, TurnEvent.id))).scalars().all()
    turns = {e.turn_id for e in events if e.kind == "turn_started"}
    tools: dict[str, int] = {}
    input_tokens = output_tokens = 0
    blocked = 0
    for e in events:
        if e.kind == "tool_call_result":
            name = (e.data or {}).get("tool", "?")
            tools[name] = tools.get(name, 0) + 1
        elif e.kind == "model_response":
            input_tokens += (e.data or {}).get("gen_ai.usage.input_tokens") or 0
            output_tokens += (e.data or {}).get("gen_ai.usage.output_tokens") or 0
        elif e.kind == "policy_blocked":
            blocked += 1
    duration = None
    if events:
        duration = (events[-1].created_at - events[0].created_at).total_seconds()
    return {"id": session_id, "messages": {r: c for r, c in roles}, "turns": len(turns),
            "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "policy_blocked": blocked, "active_seconds": duration}


async def insights_report(days: int = 7) -> dict[str, Any]:
    """Token/tool/activity analytics across all sessions (turn spine, offline)."""
    from .db import Conversation, Message, Session, TurnEvent, init_db, migrate
    await init_db(); await migrate()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with Session() as s:
        events = (await s.execute(select(TurnEvent).where(TurnEvent.created_at >= since))).scalars().all()
        conv_count = (await s.execute(select(func.count(Conversation.id)))).scalar() or 0
        msg_count = (await s.execute(select(func.count(Message.id)))).scalar() or 0
    per_day: dict[str, int] = {}
    tools: dict[str, int] = {}
    input_tokens = output_tokens = 0
    for e in events:
        day = e.created_at.date().isoformat()
        if e.kind == "turn_started":
            per_day[day] = per_day.get(day, 0) + 1
        elif e.kind == "tool_call_result":
            name = (e.data or {}).get("tool", "?")
            tools[name] = tools.get(name, 0) + 1
        elif e.kind == "model_response":
            input_tokens += (e.data or {}).get("gen_ai.usage.input_tokens") or 0
            output_tokens += (e.data or {}).get("gen_ai.usage.output_tokens") or 0
    return {"window_days": days, "turns_per_day": dict(sorted(per_day.items())),
            "total_turns": sum(per_day.values()),
            "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1])[:20]),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "sessions_total": conv_count, "messages_total": msg_count,
            "cost": "n/a (no provider pricing configured)"}


async def dump_report() -> dict[str, Any]:
    """Copy-pasteable support summary; secrets redacted by config_snapshot."""
    from . import __version__ as version
    doc = doctor_report()
    return {"noesek_version": version, "python": platform.python_version(),
            "platform": platform.platform(), "home": str(noesek_home()),
            "paused": is_paused(), "config": config_snapshot(),
            "doctor": {"ok": doc["ok"], "issues": doc.get("issues", [])},
            "prompt_size": prompt_size_report()}


def logs_list() -> list[dict[str, Any]]:
    root = noesek_home() / "logs"
    if not root.is_dir():
        return []
    return [{"file": str(p), "bytes": p.stat().st_size,
             "modified": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
            for p in sorted(root.glob("*.log"))]


def logs_tail(name: str | None = None, lines: int = 50) -> dict[str, Any]:
    root = noesek_home() / "logs"
    files = sorted(root.glob("*.log")) if root.is_dir() else []
    if name:
        target = root / Path(name).name  # confine to the logs dir
        if not target.is_file():
            raise LookupError(name)
    elif files:
        target = files[-1]
    else:
        return {"file": None, "lines": [], "note": "no log files under ~/.noesek/logs; see `hermes cron incidents` for failure records"}
    content = target.read_text(errors="replace").splitlines()[-lines:]
    return {"file": str(target), "lines": content}


async def sessions_store_stats() -> dict[str, Any]:
    """Store-wide session statistics (hermes sessions stats)."""
    from .db import Conversation, Message, Session, TurnEvent, init_db, migrate
    from .config import settings
    await init_db(); await migrate()
    async with Session() as s:
        convs = (await s.execute(select(func.count(Conversation.id)))).scalar() or 0
        msgs = (await s.execute(select(func.count(Message.id)))).scalar() or 0
        turns = (await s.execute(select(func.count(TurnEvent.id.distinct()))
                                 .where(TurnEvent.kind == "turn_started"))).scalar() or 0
        first = (await s.execute(select(func.min(Message.created_at)))).scalar()
        last = (await s.execute(select(func.max(Message.created_at)))).scalar()
    db_url = settings.database_url
    db_bytes = None
    if db_url.startswith("sqlite"):
        path = Path(db_url.split("///")[-1]).expanduser()
        if path.is_file():
            db_bytes = path.stat().st_size
    return {"sessions": convs, "messages": msgs, "turns": turns,
            "first_message_at": _iso(first), "last_message_at": _iso(last),
            "database_bytes": db_bytes}
