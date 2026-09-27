"""Laya guardian scorer: lazy checkpoint load + risk-score computation.

The checkpoint directory must contain model.safetensors, the encoder config,
the tokenizer, and rl_agent_config.json (with the calibration temperatures
fitted on held-out traces at train time). laya is pip-installed on the host,
never a repo dependency.
"""
from __future__ import annotations

import json
import threading

from .questions import RISK_QUESTION, RISKY_CLASSES

MAX_FIELD_CHARS = 500


class GuardianUnavailable(Exception):
    """The checkpoint or laya itself cannot be loaded in this process."""


_lock = threading.Lock()
_agent = None
_load_error: str | None = None


def _load_agent(model_dir: str):
    global _agent, _load_error
    with _lock:
        if _agent is not None:
            return _agent
        if _load_error is not None:
            raise GuardianUnavailable(_load_error)
        try:
            import laya
            _agent = laya.Agent(model_dir, device="cpu")
        except Exception as e:  # noqa: BLE001 - cache ANY load failure as unavailable
            _load_error = f"{type(e).__name__}: {e}"
            raise GuardianUnavailable(_load_error)
        return _agent


def build_state(tool_name: str, arguments: dict, reasoning: str, context: str) -> str:
    """ACTION-FIRST state string, the exact shape the frozen gate trains/evals on:
    'tool: action\\nreasoning: ...\\ncontext: ...'."""
    action = json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True)
    if len(action) > MAX_FIELD_CHARS:
        action = action[: MAX_FIELD_CHARS - 3] + "..."
    reasoning = (reasoning or "").strip() or "no reasoning supplied"
    if len(reasoning) > MAX_FIELD_CHARS:
        reasoning = reasoning[: MAX_FIELD_CHARS - 3] + "..."
    context = (context or "").strip() or "live controller turn"
    if len(context) > MAX_FIELD_CHARS:
        context = context[: MAX_FIELD_CHARS - 3] + "..."
    return f"{tool_name}: {action}\nreasoning: {reasoning}\ncontext: {context}"


def score_state(model_dir: str, state: str) -> dict:
    """One risk-shape prediction. deny_score = summed probability of the risky
    classes (the approved gate design); esc_prob = external_communication."""
    agent = _load_agent(model_dir)
    ans = agent.predict(state, RISK_QUESTION)["answers"]["action_class"]
    probs = ans.get("probabilities", {}) or {}
    return {
        "deny_score": sum(float(probs.get(k, 0.0)) for k in RISKY_CLASSES),
        "esc_prob": float(probs.get("external_communication", 0.0)),
        "top_risk": ans.get("choice"),
    }


def _reset_for_tests():
    global _agent, _load_error
    with _lock:
        _agent = None
        _load_error = None
