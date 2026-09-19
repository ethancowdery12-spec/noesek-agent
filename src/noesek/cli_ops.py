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
from datetime import datetime, timezone
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
                    Conversation.created_at, func.count(Message.id).label("messages"),
                    func.max(Message.created_at).label("updated_at"))
             .outerjoin(Message, Message.conversation_id == Conversation.id)
             .group_by(Conversation.id).order_by(func.max(Message.created_at).desc()).limit(limit))
        rows = (await s.execute(q)).all()
    return [{"id": r.id, "channel": r.channel, "external_user_id": r.external_user_id,
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
