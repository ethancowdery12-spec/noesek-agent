"""Team runs on the orchestration primitives: one outcome owner, bounded
workers/steps/time, typed WorkerResult handoffs, cancellation propagation, and
controller-owned final synthesis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .orchestration import (CancellationToken, WorkerResult, WorkBudget)


class TeamError(RuntimeError):
    pass


@dataclass
class TeamRun:
    outcome: str
    owner: str
    members: tuple[str, ...]
    max_steps: int = 20
    step: int = 0
    state: str = "running"
    reports: list = field(default_factory=list)
    budget: WorkBudget = field(default=None)
    token: CancellationToken = field(default_factory=CancellationToken)
    synthesis: dict | None = None

    def __post_init__(self):
        if not self.outcome or not self.owner or self.owner not in self.members \
                or len(set(self.members)) != len(self.members) or len(self.members) > 8:
            raise TeamError("invalid team ownership or membership")
        if self.budget is None:
            self.budget = WorkBudget(max_steps=self.max_steps)

    def report(self, member: str, result: dict | WorkerResult):
        """A typed handoff from a member. Only members report; the run must be live."""
        if self.state != "running" or member not in self.members:
            raise TeamError("report is not accepted")
        if self.token.cancelled:
            self.terminate("cancelled")
            raise TeamError("team run is cancelled")
        if isinstance(result, WorkerResult):
            result = result.to_dict()
        self.step += 1
        self.reports.append({"member": member, "result": result})
        if self.step >= self.max_steps:
            self.terminate("step_limit")

    def cancel(self):
        """Controller-initiated cancellation; propagates to the shared token."""
        self.token.cancel()
        if self.state == "running":
            self.terminate("cancelled")

    def complete(self, member: str, result: dict | WorkerResult):
        """Only the outcome owner completes; the controller then synthesizes."""
        if member != self.owner:
            raise PermissionError("only the outcome owner may complete")
        self.report(member, result)
        self.state = "completed"

    def synthesize(self, final: dict) -> dict:
        """Controller-owned final synthesis over member handoffs. Only after completion."""
        if self.state != "completed":
            raise TeamError("cannot synthesize before the outcome owner completes the run")
        self.synthesis = {"outcome": self.outcome, "owner": self.owner,
                          "steps": self.step, "final": final,
                          "evidence": [r["result"] for r in self.reports]}
        return self.synthesis

    def terminate(self, reason: str):
        self.state = "terminated"
        self.termination_reason = reason
