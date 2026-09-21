"""Adversarial multi-review audit.

Pattern from Ethan's roadmap (item 7, verified from a post he relayed):
agent A audits, agent B independently re-reviews each finding, a third
pass reconciles - a large share of the original "problems" get rejected.
Guards against "keep asking what to improve and it will keep finding
things."

This tool is the reconciliation pass, made deterministic. The agent runs
the audit (pass A) and the independent re-review (pass B) in
conversation; this tool enforces the discipline: a finding survives only
if it carries concrete, falsifiable evidence. Duplicates collapse to the
highest severity. Vague speculation is rejected with a reason. No model
call, no dependencies.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

SEVERITIES = ("low", "medium", "high")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

# What a complete audit covers, per task type. Returned with every run so
# the auditor can check coverage before submitting findings.
CHECKLISTS = {
    "code": [
        "correctness: does it do what the spec/ask says",
        "edge cases: empty input, huge input, None, unicode",
        "error handling: failures surfaced, not swallowed",
        "security: injection surfaces, secrets, unsafe eval/exec",
        "regressions: what existing behavior could this break",
    ],
    "writing": [
        "facts: every claim/number/name verified against the source",
        "audience: right register, no assumed knowledge",
        "tone: no filler, no AI tells (run humanize)",
        "completeness: was the whole ask answered",
    ],
    "research": [
        "sources: every claim tied to a named source",
        "recency: is the source current enough for the claim",
        "conflicts: do sources disagree; was that surfaced",
        "gaps: what was NOT found that the ask needs",
    ],
    "general": [
        "correctness: is the core claim/output right",
        "completeness: was the whole ask answered",
        "risks: what could go wrong acting on this",
    ],
}


class Finding(BaseModel):
    claim: str
    evidence: str = ""
    severity: str = "medium"


class AdversarialReviewInput(BaseModel):
    task_type: str = "general"
    subject_summary: str
    findings: list[Finding] = []


_EVIDENCE_HINT = re.compile(
    r"line \d+|col(?:umn)? \d+|\d{4}-\d{2}|\$[\d,.]+|[\"'].{3,}[\"']|"
    r"`[^`]{2,}`|\b\d+(\.\d+)?%|\bstep \d+|\bpage \d+", re.IGNORECASE)
_SPECULATION = re.compile(
    r"^(maybe|perhaps|might|could it be|what if|i wonder|not sure)\b|"
    r"\?$", re.IGNORECASE)


_STOPWORDS = {"a", "an", "the", "on", "of", "to", "in", "is", "has",
              "no", "not", "it", "its", "and", "or", "be", "been"}


def _norm(claim: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", "", claim.lower()).split()
    return " ".join(sorted({w for w in words if w not in _STOPWORDS}))


def _similar(a: str, b: str) -> bool:
    wa, wb = set(_norm(a).split()), set(_norm(b).split())
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / max(len(wa), len(wb))
    return overlap >= 0.6


def review_findings(inp: AdversarialReviewInput) -> dict:
    survivors: list[dict] = []
    rejected: list[dict] = []

    for f in inp.findings:
        claim, evidence = f.claim.strip(), f.evidence.strip()
        severity = f.severity.lower()
        if severity not in SEVERITY_RANK:
            rejected.append({"claim": claim, "reason":
                             f"severity '{f.severity}' not one of {list(SEVERITIES)}"})
            continue
        if not claim:
            rejected.append({"claim": "", "reason": "empty claim"})
            continue
        if _SPECULATION.search(claim):
            rejected.append({"claim": claim, "reason":
                             "speculation or question, not a falsifiable finding"})
            continue
        if len(evidence) < 10 or not _EVIDENCE_HINT.search(evidence):
            rejected.append({"claim": claim, "reason":
                             "no concrete evidence (needs a quote, line ref, number, or code span)"})
            continue
        # Dedupe against existing survivors; keep the higher severity.
        dupe = next((s for s in survivors if _similar(s["claim"], claim)), None)
        if dupe:
            if SEVERITY_RANK[severity] > SEVERITY_RANK[dupe["severity"]]:
                dupe["severity"] = severity
                rejected.append({"claim": claim, "reason":
                                 "duplicate of a surviving finding; severity raised on the survivor"})
            else:
                rejected.append({"claim": claim, "reason": "duplicate of a surviving finding"})
            continue
        survivors.append({"claim": claim, "evidence": evidence, "severity": severity})

    order = {"high": 0, "medium": 1, "low": 2}
    survivors.sort(key=lambda s: order[s["severity"]])
    task_type = inp.task_type.lower()
    checklist = CHECKLISTS.get(task_type, CHECKLISTS["general"])
    return {
        "subject": inp.subject_summary,
        "task_type": task_type,
        "checklist": checklist,
        "survivors": survivors,
        "rejected": rejected,
        "verdict": (f"{len(survivors)} finding(s) survived independent "
                    f"re-review; {len(rejected)} rejected. Only survivors "
                    "become work."),
    }


async def adversarial_review(inp: AdversarialReviewInput) -> dict:
    return review_findings(inp)
