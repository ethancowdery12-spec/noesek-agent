"""Async gate between the controller and the scorer: settings, verdict
mapping, timeout, and fail-open/closed behavior. No laya import at module
level - safe to import anywhere."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..config import settings
from . import policy as _policy
from . import scorer as _scorer

log = logging.getLogger(__name__)


@dataclass
class GateVerdict:
    verdict: str  # "allow" | "escalate" | "deny"
    deny_score: float
    esc_prob: float
    top_risk: str | None
    state: str
    error: str | None = None  # set only when the verdict came from a scoring failure


def classify(deny_score: float, esc_prob: float,
             deny_threshold: float, escalate_floor: float,
             esc_prob_threshold: float) -> str:
    if deny_score >= deny_threshold:
        return "deny"
    if deny_score >= escalate_floor or esc_prob >= esc_prob_threshold:
        return "escalate"
    return "allow"


async def gate_tool_call(tool_name: str, arguments: dict, reasoning: str, context: str) -> GateVerdict | None:
    """Score one proposed call. None = gate not engaged (disabled, or fail-open
    after a scoring error); the caller then proceeds as if no guardian exists."""
    if not settings.guardian_enabled:
        return None
    state = _scorer.build_state(tool_name, arguments, reasoning, context)
    if settings.guardian_remote:
        # Kaggle relay path (docs/GUARDIAN_SERVING.md): the internal timeout
        # sits 1s under the outer wait_for so the relay's own expiry wins.
        scoring = asyncio.to_thread(
            _scorer.score_state_via_relay, state,
            max(1.0, settings.guardian_score_timeout_seconds - 1.0))
    else:
        scoring = asyncio.to_thread(_scorer.score_state, settings.guardian_model_dir, state)
    try:
        s = await asyncio.wait_for(scoring, timeout=settings.guardian_score_timeout_seconds)
    except Exception as e:  # noqa: BLE001 - any scorer/timeout failure lands here
        log.warning("guardian scoring failed for %s: %s", tool_name, e)
        if settings.guardian_fail_mode == "closed":
            return GateVerdict("deny", -1.0, -1.0, None, state,
                               error=f"guardian unavailable ({type(e).__name__}) and fail mode is closed")
        return None
    model_verdict = classify(s["deny_score"], s["esc_prob"],
                             settings.guardian_deny_threshold, settings.guardian_escalate_floor,
                             settings.guardian_esc_prob_threshold)
    try:
        verdict, rule = await _policy.apply_async(tool_name, s["deny_score"], s["esc_prob"],
                                                  s.get("top_risk"), model_verdict)
    except _policy.PolicyError as e:
        log.warning("guardian policy store invalid for %s: %s - failing closed", tool_name, e)
        return GateVerdict("deny", s["deny_score"], s["esc_prob"], s["top_risk"], state,
                           error=f"guardian policy store invalid ({e}); failing closed")
    if rule and rule != "floor":
        log.info("guardian policy rule %s applied for %s: %s -> %s", rule, tool_name, model_verdict, verdict)
    return GateVerdict(verdict, s["deny_score"], s["esc_prob"], s["top_risk"], state)
