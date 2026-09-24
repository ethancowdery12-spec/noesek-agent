"""Thin-controller / scoped-worker orchestration policy.

Architecture (owner-approved 2026-09-17):
- The chat-facing Controller handles conversation, clarification, approvals,
  routing, progress, cancellation, and final delivery. It does NOT register or
  execute work tools directly; substantive work is delegated to scoped workers.
- Workers cannot spawn child workers by default. The only exception is an
  explicit SpawnGrant issued by the controller's policy.
- One outcome owner per team run; bounded workers, steps, and wall-clock time;
  typed handoffs; cancellation propagates into running workers; workers return
  evidence; the controller owns final synthesis.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

# Tools that DO work. Never present in the chat controller's own registry.
WORK_TOOLS = frozenset({"search_web", "fetch_url", "run_python"})

# The thin controller's complete tool surface: conversation state, task
# coordination, and delegation. Anything else is work and must be delegated.
CONTROLLER_TOOLS = frozenset({
    "remember", "recall", "memory_get", "forget", "supersede_memory", "handoff", "switch_model", "library_docs", "search_tools",
    "create_task", "list_tasks", "cancel_task",
    "delegate_task",
    "gmail_read", "gmail_send", "calendar_read", "github_notifications",
    "create_file", "speak", "optimize_prompt", "humanize", "rewrite_natural", "scrub", "generate_variants", "story_critique", "exact_solve", "seo_audit", "geo_audit", "code_graph", "office_doc", "linkedin", "design_system", "playbook", "browser_cookies", "adversarial_review", "security_audit", "literature_search", "duckdb_query", "code_interpreter", "test_verifier", "code_act", "skill_library", "ofx_import", "fit_import", "date_math", "calc", "code_intel",
})


class OrchestrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpawnGrant:
    """Explicit, controller-issued exception to the no-child-spawn rule."""
    parent_worker: str
    allowed_children: tuple[str, ...]
    reason: str
    max_children: int = 2

    def __post_init__(self):
        if not self.reason.strip():
            raise OrchestrationError("a spawn grant requires a reason")
        if not self.allowed_children:
            raise OrchestrationError("a spawn grant must name allowed children")


DEFAULT_SPAWN_POLICY = None  # no grant: workers cannot spawn children


@dataclass(frozen=True)
class WorkBudget:
    max_steps: int = 6
    max_seconds: float = 120.0
    max_children: int = 0

    def check_step(self, step: int) -> None:
        if step >= self.max_steps:
            raise OrchestrationError(f"worker exceeded step budget ({self.max_steps})")


class CancellationToken:
    """Cooperative cancellation propagated from the controller into a worker."""

    def __init__(self, event: asyncio.Event | None = None):
        self._event = event or asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError()


@dataclass
class WorkerResult:
    """Typed handoff from a scoped worker back to the controller."""
    worker: str
    output: str
    citations: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    elapsed_seconds: float = 0.0
    incomplete: bool = False
    cancelled: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"worker": self.worker, "output": self.output, "citations": self.citations,
                "evidence": self.evidence, "steps": self.steps,
                "elapsed_seconds": round(self.elapsed_seconds, 3),
                "incomplete": self.incomplete, "cancelled": self.cancelled,
                **({"error": self.error} if self.error else {})}


async def run_scoped_worker(worker_name: str, instruction: str, *, llm=None,
                            budget: WorkBudget | None = None,
                            token: CancellationToken | None = None,
                            spawn_grant: SpawnGrant | None = None) -> WorkerResult:
    """Run one scoped worker under budget and cancellation. Workers receive only
    their read-only tools; delegation is available solely through a SpawnGrant."""
    from ..workers.runner import run_worker
    budget = budget or WorkBudget()
    token = token or CancellationToken()
    start = time.monotonic()
    raw = await run_worker(worker_name, instruction, llm=llm, max_steps=budget.max_steps,
                           budget=budget, token=token, spawn_grant=spawn_grant)
    return WorkerResult(
        worker=raw.get("worker", worker_name), output=raw.get("output", ""),
        citations=raw.get("citations", []), evidence=raw.get("evidence", []),
        steps=raw.get("steps", 0), elapsed_seconds=time.monotonic() - start,
        incomplete=bool(raw.get("incomplete")), cancelled=bool(raw.get("cancelled")),
        error=raw.get("error"))
