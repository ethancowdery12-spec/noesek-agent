# Noesek v1.2 - open-source reuse tranche 2

September 17, 2026. Continues the approved reuse matrix: the full Hermes cron
job store with a Noesek-owned tick, and the Hermes skill system.

## What landed (on top of v1.1)

### Vendored (same pin: hermes-agent @ c712f06d, MIT)

- **cron/jobs.py** (3,445 lines) - the real durable job store: cron, interval,
  and one-shot schedules (including natural forms like "in 5 minutes"), pause/
  resume, trigger, update with schedule re-derivation, terminal-state machine,
  and multi-process claim fencing with TTL and dead-owner release. Plus
  cron/env_settings.py, cron/notepad.py, cron/unreachable_retry.py.
- **Skill system** - tools/skills_tool.py + dedup/plugin/setup modules,
  skill_ledger, skill_provenance, skill_usage, skills_guard, skill_linter,
  agent/skill_utils, tools/path_security, tools/registry: SKILL.md discovery,
  viewing, linting, safety scanning, provenance, and usage tracking.
- Vendored total: 38 upstream files (~14,000 lines), manifest in VENDORING.md.

### Noesek-owned execution boundary (adapter, not port)

Hermes's scheduler tick runs jobs through Hermes's agent loop; Noesek keeps its
own controller. `noesek.core.cron_dispatch.dispatch_due` claims due jobs from
the vendored store (fire fencing and occurrence dedup intact) and enqueues
durable Noesek tasks; the task runner settles each job (mark_job_run, ledger
finish) on completion or terminal failure. `noesek.compat.skills_real.
SkillStore` exposes list/view/check behind the Noesek home policy.

New bridges (all marked NOT upstream source): scheduler running-set,
preflight transient-error classifier (verbatim port), lifecycle guard (inert -
no Hermes gateway daemon), terminal scope/env, delegation context, kanban,
skill preprocessing passthrough, budget constant, secret-scope extensions,
gateway platform constant.

### Dependency

- croniter==6.2.4 (MIT) added, exact-pinned, in requirements-lock.txt.

## Verification

- 163 tests pass on CPython 3.12.13 (155 carried + 8 new): job CRUD cycle,
  one-shot schedules, claim fencing, invalid-schedule rejection, end-to-end
  tick -> task queue -> settlement with idempotent re-tick, skill list/view/
  check/missing-skill errors, plus all v1.1 coverage.
- compileall OK; sdist + wheel build OK; clean-sdist install + full suite pass.

## Next-stage ledger

1. Hermes scheduler_tick/delivery/preflight prompt-script machinery IF Noesek
   ever wants Hermes's own per-job agent sessions; the Noesek tick covers the
   practical contract today.
2. plugins/ families (memory, observability, platforms): each needs a bridge
   review against Noesek's existing memory/telemetry/channel layers.
3. skills preprocessing (template vars, inline shell) - currently passthrough;
   deliberate, since it executes skill content and needs a policy review.
4. gateway/ channel directory + authz mixin; acp_adapter/ against pinned acp
   SDK; tui_gateway/ event machinery.
5. Channel SDKs (neonize/slack-sdk/aiogram) behind channel interfaces.
6. Process-boundary integrations: browser-use/Playwright, E2B/docker-py,
   OpenCode over ACP, promptfoo eval service; Hermes evals as compat harness.

No live account or service was contacted.
