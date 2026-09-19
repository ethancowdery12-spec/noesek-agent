# Noesek v1.5.0 - reuse tranche 5: browser backend, sandbox backends, evals, thin-controller orchestration

## What landed

1. **Browser backend** (`core/browser_backend.py`): pinned `playwright==1.56.0`
   (Apache-2.0) executes approval-bound ComputerPlans in headless Chromium
   (browser process boundary owned by Playwright). Noesek's origin/action
   allowlists and plan digest gate wrap every run; unapproved digests and
   off-allowlist origins/actions are refused before any browser launches.
   Verified against a local HTTP server with real Chromium.
2. **Sandbox backends** (`tools/sandbox_backends.py`): docker-cli (unchanged
   default), docker-py (pinned `docker==7.1.0`, Apache-2.0, same isolation
   flags), E2B (pinned `e2b==2.9.0`, Apache-2.0, remote microVM, explicit
   selection only, operator's own E2B_API_KEY, always torn down). Selected via
   NOESEK_SANDBOX_BACKEND.
3. **promptfoo evaluation** (`tools/evals.py`): process-boundary runner -
   Noesek generates the config (local endpoints only; external targets refused)
   and parses results; promptfoo runs as a subprocess. Not a Python dependency.
4. **Thin-controller / scoped-worker orchestration** (`core/orchestration.py`,
   owner-approved 2026-09-17): the chat Controller's registry holds only
   conversation/state/coordination tools (remember/recall/forget, task
   create/list/cancel, delegate_task) - no work tools. Approved work tools
   execute inside the operator worker's scoped registry, never in the
   controller. Workers cannot spawn children by default; the only exception is
   an explicit reasoned SpawnGrant naming allowed children, bound to the
   issuing worker. WorkBudget caps steps and wall-clock time. Cancellation
   propagates from cancel_task through the durable queue watcher into running
   workers (cooperative token) and settles the task cancelled without retry.
   Worker handoffs are typed WorkerResults with citations/evidence; the
   controller owns final synthesis.

## Verification

- 461 passed, 43 skipped (255 unchanged upstream Hermes tests among the passes).
- Real-browser test executes an approved plan in Chromium; refusal paths tested.
- Orchestration proofs: controller has no work tools; workers spawn nothing by
  default; grants are scoped and reasoned; step/time budgets hold; cancellation
  reaches a running worker through the queue; typed handoffs returned.

## Next-stage ledger

- Channel SDKs (slack-sdk MIT, aiogram MIT) behind service boundaries.
- Broader upstream eval suites (deepeval) as a further tranche.
- browser-use (MIT) agentic loop layer over the Playwright backend if wanted.
- Team runs: migrate teams.py onto WorkerResult/SpawnGrant types.
