"""Conversation condensers (skills batch 3: OpenHands condenser patterns,
own-words implementation - nothing copied).

Two complementary mechanisms over what already existed (per-compaction
one-shot auto-distill, item 58):

1. Rolling condensation (OpenHands rolling-summary pattern): ONE evolving
   condensation memory per conversation. Each new compaction chains the
   PRIOR summary plus the newly dropped span through the summarizer, the
   old memory is superseded, and assemble() always pins the active
   condensation - so the context block reflects the whole omitted past,
   not only the latest compaction's slice.

2. Observation masking (OpenHands observation-masking pattern): within a
   turn's tool loop, tool results older than the last `keep_full` are
   replaced by a compact placeholder before the next model call. The
   recent results the model is composing over stay verbatim; bulk from
   early rounds stops compounding. Masking only affects what is sent to
   the model - persisted history is untouched.
"""
from __future__ import annotations

import re

from sqlalchemy import select

from ..db import Compaction, Memory, Message, Session

CONDENSATION_KIND = "condensation"
CONDENSATION_SOURCE = "condenser"

_MASK = "[earlier tool result omitted by the condenser - {chars} chars]"


def mask_tool_results(messages: list[dict], keep_full: int = 6) -> list[dict]:
    """Replace all but the last keep_full tool-role messages with a
    placeholder. Idempotent; never mutates the caller's dicts."""
    idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    stale = idx[:-keep_full] if len(idx) > keep_full else []
    if not stale:
        return messages
    out = list(messages)
    for i in stale:
        m = out[i]
        content = m.get("content") or ""
        if content.startswith("[earlier tool result omitted"):
            continue
        out[i] = {**m, "content": _MASK.format(chars=len(content))}
    return out


def _through_id(content: str) -> int | None:
    m = re.search(r"through compaction #(\d+)", content or "")
    return int(m.group(1)) if m else None


async def update_condensation(conversation_id: int, summarize) -> int | None:
    """Advance the rolling condensation over any new compactions.
    `summarize` is an async callable transcript -> summary text supplied by
    the caller (the controller wires its chat model; tests wire a fake).
    Idempotent per compaction; None when there is nothing new or the
    summarizer fails (the previous condensation stays authoritative)."""
    async with Session() as s:
        prior = (await s.execute(select(Memory).where(
            Memory.conversation_id == conversation_id,
            Memory.kind == CONDENSATION_KIND,
            Memory.active == True,
        ).order_by(Memory.created_at.desc()).limit(1))).scalar_one_or_none()
        covered = _through_id(prior.content) if prior else None
        comp_q = select(Compaction).where(
            Compaction.conversation_id == conversation_id,
            Compaction.oldest_dropped_id.isnot(None))
        if covered is not None:
            comp_q = comp_q.where(Compaction.id > covered)
        comps = (await s.execute(comp_q.order_by(Compaction.id))).scalars().all()
        if not comps:
            return None
        lo = min(c.oldest_dropped_id for c in comps)
        hi = max(c.newest_dropped_id for c in comps)
        through = max(c.id for c in comps)
        span = (await s.execute(select(Message).where(
            Message.conversation_id == conversation_id,
            Message.id >= lo, Message.id <= hi).order_by(Message.id))).scalars().all()
        prior_id = prior.id if prior else None
        prior_content = prior.content if prior else None
    transcript = ""
    if prior_content:
        transcript += f"Prior condensation (carry forward what still matters):\n{prior_content}\n\n"
    transcript += "Newly omitted messages:\n" + "\n".join(
        f"{m.role}: {(m.content or '')[:300]}" for m in span[-60:])
    transcript = transcript[:8000]
    try:
        summary = (await summarize(transcript) or "").strip()
    except Exception:
        return None
    if not summary:
        return None
    content = f"Rolling condensation (through compaction #{through}): {summary[:1800]}"
    async with Session() as s:
        mem = Memory(conversation_id=conversation_id, kind=CONDENSATION_KIND,
                     content=content, source=CONDENSATION_SOURCE)
        s.add(mem)
        await s.commit()
        await s.refresh(mem)
        if prior_id is not None:
            old = await s.get(Memory, prior_id)
            if old is not None:
                old.active = False
                old.superseded_by = mem.id
            await s.commit()
    try:
        from .memory_v2 import index_memory
        await index_memory(mem.id, content)
    except Exception:
        pass
    return mem.id
