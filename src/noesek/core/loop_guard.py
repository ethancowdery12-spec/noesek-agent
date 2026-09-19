"""Loop guardrails (v2, stage C): identical-retry, doom-loop, and
no-progress detection for the controller's tool loop.

The guard watches (tool, canonical-arguments) signatures within one turn:

- Identical retry: the same signature repeated. First repeat returns a
  warning hint (a synthetic tool result, so the model can correct); the
  next repeat stops the turn.
- Doom loop: the last `cycle_window` signatures repeat exactly
  (A,B,C,A,B,C). Stops the turn.
- No progress: `max_consecutive_errors` failed calls in a row. Stops the
  turn with the error class so the user gets an actionable summary instead
  of a silent max-steps stop.

Thresholds: NOESEK_LOOP_MAX_IDENTICAL, NOESEK_LOOP_MAX_ERRORS,
NOESEK_LOOP_CYCLE_WINDOW.
"""
from __future__ import annotations

from pydantic import ValidationError

from .tools import ToolTimeoutError
from .turn_spine import canonical


def classify_exception(e: Exception) -> str:
    """Stable error classes for spine events, guardrails, and requery hints."""
    if isinstance(e, ToolTimeoutError) or isinstance(e, TimeoutError):
        return "timeout"
    if isinstance(e, ValidationError):
        return "validation"
    return type(e).__name__


class LoopGuard:
    """Per-turn loop detector. Cheap to construct; one per controller turn."""

    def __init__(self, max_identical: int = 3, max_consecutive_errors: int = 3, cycle_window: int = 3):
        if max_identical < 2: raise ValueError("max_identical must be >= 2")
        self.max_identical = max_identical
        self.max_consecutive_errors = max_consecutive_errors
        self.cycle_window = cycle_window
        self._history: list[tuple[str, str]] = []
        self._identical_streak = 0
        self._last_sig: tuple[str, str] | None = None
        self.error_streak = 0

    def before_call(self, tool: str, arguments: dict) -> tuple[str, str] | None:
        """Inspect the next call. Returns (action, reason): action is
        'warn' (inject a hint, skip execution) or 'stop' (end the turn)."""
        sig = (tool, canonical(arguments or {}))
        if sig == self._last_sig:
            self._identical_streak += 1
        else:
            self._identical_streak = 1
        self._last_sig = sig
        self._history.append(sig)
        if self._identical_streak >= self.max_identical:
            return ("stop", f"identical call to {tool} repeated {self._identical_streak} times")
        if self._identical_streak >= self.max_identical - 1:
            return ("warn", f"identical call to {tool} repeated; change the arguments or explain why retrying helps")
        w = self.cycle_window
        if len(self._history) >= 2 * w and self._history[-w:] == self._history[-2 * w:-w]:
            return ("stop", f"tool call cycle of length {w} repeated (doom loop)")
        return None

    def record_outcome(self, ok: bool) -> None:
        self.error_streak = 0 if ok else self.error_streak + 1

    def error_streak_tripped(self) -> bool:
        return self.error_streak >= self.max_consecutive_errors
