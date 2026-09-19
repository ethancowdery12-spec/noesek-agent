"""Ordered allow/ask/deny policy engine (v2, stage B).

Rules evaluate in order; first match wins. The hardline content gate
(vendored upstream detection tables, MIT) always runs first and cannot be
overridden: no configured rule, approval, or mode may execute a hardline
or sudo-stdin match. Noesek's approval flow stays authoritative for "ask".

Configured rules come from NOESEK_POLICY_RULES (JSON list), evaluated after
the hardline gate and before the built-in defaults. Default behavior is
unchanged from v1.11.3: write/external/money/destructive risks ask,
everything else allows.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass

from .approval_engine import assess_tool_arguments
from .turn_spine import canonical
from .types import Risk

ALLOW, ASK, DENY = "allow", "ask", "deny"
_ASK_RISKS = (Risk.WRITE.value, Risk.EXTERNAL.value, Risk.MONEY.value, Risk.DESTRUCTIVE.value)


@dataclass(frozen=True)
class PolicyRule:
    effect: str                      # allow | ask | deny
    tools: tuple[str, ...] = ("*",)  # fnmatch patterns on the tool name
    risks: tuple[str, ...] = ("*",)  # risk values or "*"
    contains: str | None = None      # substring match over canonical arguments JSON
    reason: str = ""
    rule: str = "default"

    def matches(self, tool: str, risk: Risk, arguments_json: str) -> bool:
        if not any(fnmatch.fnmatchcase(tool, pat) for pat in self.tools):
            return False
        if self.risks != ("*",) and risk.value not in self.risks:
            return False
        if self.contains is not None and self.contains not in arguments_json:
            return False
        return True


@dataclass(frozen=True)
class PolicyDecision:
    effect: str
    reason: str = ""
    rule: str = "default"
    content_flag: str | None = None  # dangerous-content finding worth surfacing in rationale

    @property
    def allowed(self) -> bool: return self.effect == ALLOW
    @property
    def needs_approval(self) -> bool: return self.effect == ASK
    @property
    def denied(self) -> bool: return self.effect == DENY


_DEFAULT_RULES = (
    PolicyRule(ASK, risks=_ASK_RISKS, reason="risk class requires approval", rule="default:risk"),
    PolicyRule(ALLOW, reason="default allow", rule="default:allow"),
)


def parse_rules(raw: str) -> tuple[PolicyRule, ...]:
    """Parse NOESEK_POLICY_RULES: JSON list of {effect, tools?, risks?, contains?, reason?}."""
    if not raw or not raw.strip():
        return ()
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("NOESEK_POLICY_RULES must be a JSON list of rule objects")
    rules = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or item.get("effect") not in {ALLOW, ASK, DENY}:
            raise ValueError(f"policy rule {i}: need effect of allow|ask|deny")
        rules.append(PolicyRule(
            effect=item["effect"],
            tools=tuple(item.get("tools", ["*"])),
            risks=tuple(item.get("risks", ["*"])),
            contains=item.get("contains"),
            reason=item.get("reason", ""),
            rule=f"configured:{i}",
        ))
    return tuple(rules)


def evaluate_policy(tool: str, risk: Risk, arguments: dict | None,
                    *, extra_rules: tuple[PolicyRule, ...] = ()) -> PolicyDecision:
    """First-match-wins evaluation. The hardline content gate is always rule 0."""
    args_json = canonical(arguments or {})
    gate = assess_tool_arguments(arguments)
    if gate.blocked:
        return PolicyDecision(DENY, gate.reason, "hardline")
    flag = gate.reason if gate.verdict == "approval" else None
    for rule in (*extra_rules, *_DEFAULT_RULES):
        if rule.matches(tool, risk, args_json):
            return PolicyDecision(rule.effect, rule.reason or rule.rule, rule.rule, flag)
    return PolicyDecision(ALLOW, "no rule matched", "default:allow", flag)  # unreachable with defaults
