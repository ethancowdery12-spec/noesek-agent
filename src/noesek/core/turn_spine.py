"""Durable turn spine: typed, ordered event log for every agent turn.

Design (v2, stage A):

- One ``turn_id`` per controller turn; every event carries a monotonically
  increasing ``seq`` so a postmortem replays deterministically.
- Write-ahead: events that announce a side effect (``tool_call_requested``)
  flush STRICTLY before the effect runs. If the spine write fails, the side
  effect does not run. Informational events are best-effort and never break
  a user turn (same contract as ``db.record_trace``).
- Model events carry OpenTelemetry GenAI semantic-convention attributes
  (``gen_ai.system``, ``gen_ai.request.model``, ``gen_ai.usage.input_tokens``,
  ``gen_ai.usage.output_tokens``, ``gen_ai.response.finish_reasons``).
  See docs/turn_spine.md for provenance.
- Event data passes through the telemetry redactor so secret-looking keys
  are never persisted.
"""
import json
import uuid

from sqlalchemy import select

from ..db import Session, TurnEvent
from .telemetry import _SECRET


def redact_event(data: dict) -> dict:
    """Redact secret-looking keys, exempting the gen_ai.* namespace (OTel GenAI
    semantic-convention names are spec constants, e.g. gen_ai.usage.input_tokens,
    never credentials)."""
    return {k: ("[REDACTED]" if _SECRET.search(k) and not k.startswith("gen_ai.") else v)
            for k, v in data.items()}


TURN_STARTED = "turn_started"
MODEL_REQUEST = "model_request"
MODEL_RESPONSE = "model_response"
TOOL_CALL_REQUESTED = "tool_call_requested"
TOOL_CALL_RESULT = "tool_call_result"
APPROVAL_REQUIRED = "approval_required"
APPROVAL_DECIDED = "approval_decided"
POLICY_BLOCKED = "policy_blocked"
LOOP_GUARD = "loop_guard"
COMPACTION = "compaction"
TURN_COMPLETED = "turn_completed"
TURN_STOPPED = "turn_stopped"
TURN_FAILED = "turn_failed"

# Kinds that must land before the action they describes; a failed write
# aborts the action (fail closed).
_WRITE_AHEAD = {TOOL_CALL_REQUESTED}


def canonical(data: dict) -> str:
    """Deterministic JSON for canonical arguments and postmortem diffs."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)


class SpineWriteError(RuntimeError):
    """A write-ahead spine event could not be persisted; the side effect was not run."""


class TurnSpine:
    """Ordered event emitter for one turn. Cheap to construct; one per turn."""

    def __init__(self, conversation_id: int, turn_id: str | None = None):
        self.conversation_id = conversation_id
        self.turn_id = turn_id or uuid.uuid4().hex
        self._seq = 0

    async def emit(self, kind: str, data: dict | None = None, *, strict: bool | None = None) -> None:
        if strict is None:
            strict = kind in _WRITE_AHEAD
        self._seq += 1
        row = TurnEvent(turn_id=self.turn_id, conversation_id=self.conversation_id,
                        seq=self._seq, kind=kind, data=redact_event(data or {}))
        try:
            async with Session() as s:
                s.add(row)
                await s.commit()
        except Exception as e:
            if strict:
                raise SpineWriteError(f"turn spine write failed for {kind}: {type(e).__name__}") from e


async def get_turn_events(turn_id: str) -> list[TurnEvent]:
    async with Session() as s:
        return (await s.execute(
            select(TurnEvent).where(TurnEvent.turn_id == turn_id).order_by(TurnEvent.seq)
        )).scalars().all()


def render_turn(events: list[TurnEvent]) -> str:
    """Deterministic plain-text postmortem of one turn."""
    lines = []
    for e in events:
        created = e.created_at.isoformat() if e.created_at else "?"
        lines.append(f"{e.seq:03d} {created} {e.kind} {canonical(e.data)}")
    return "\n".join(lines)
