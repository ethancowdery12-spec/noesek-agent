# Noesek v1.1 - open-source reuse tranche 1

September 17, 2026. Implements the approved reuse matrix's highest-value
tranche: real Hermes Agent subsystems and pinned production SDKs replace
interface-level implementations, inside Noesek's own approval/policy gates.

## What landed

### Vendored Hermes Agent subsystems (MIT, Nous Research, pinned commit c712f06d)

22 upstream files (8,772 lines incl. headers) under `src/noesek/vendor/hermes/`,
verbatim except mechanical import rewrites, with per-file provenance headers,
SHA-256 manifest (VENDORING.md), and the MIT license text (LICENSE.hermes):

- **Approval stack** (tools/approval*.py, tools/interrupt.py, tools/ansi_strip.py):
  hardline blocklist, sudo -S stdin guard, dangerous-pattern tables,
  quote/prose-aware detection, user deny rules, smart/session prompt logic.
- **Cron persistence core** (cron/occurrences, executions, incidents,
  delivery_queue + hermes_constants, hermes_time, hermes_state_wal,
  hermes_cli/sqlite_util, sqlite_runtime, agent/retry_utils): exact occurrence
  identity and dedup, a WAL-backed sqlite execution ledger (claim -> running ->
  terminal), recurring-failure incidents with secret redaction, and an
  idempotent result-delivery queue.

Eleven Noesek-authored bridge modules (clearly marked NOT upstream source) adapt
config, redaction, pid liveness, and session env so the vendored code runs
under Noesek's settings. VENDORING.md lists both sets.

### Real SDK backends behind existing interfaces

- `noesek.core.otel_real`: the pinned opentelemetry-sdk (Apache-2.0) backs the
  telemetry layer - real W3C trace/span IDs, span processors, in-memory or
  OTLP/HTTPS export. Noesek redaction runs before attributes reach the SDK.
- `noesek.compat.mcp_real`: the pinned official MCP Python SDK (MIT) gives a
  real stdio MCP client; Noesek's ExternalServer policy (enabled flag, explicit
  tool allowlist) gates every connection and call.

### Wiring (not just vendored files on disk)

- Controller: every approval-required tool call now passes the vendored
  command gate. Hardline/sudo-stdin commands are refused outright - no approval
  can run them, before creation and again before execution (stored arguments
  are re-checked in decide_approval). Dangerous matches are annotated on the
  approval rationale.
- Task runner: every task attempt is recorded in the vendored execution ledger
  (claim/running/finish), dead tasks open incidents, and completion
  notifications go through the idempotent delivery queue.
- Capability contract (compat/hermes_contract.py) now labels each family's
  backend: `cron` and approval internals are `vendored`; `telemetry` and `mcp`
  are `sdk`; the rest remain `interface` (honest labels, no inflated claims).

### Supply chain

All runtime dependencies are exact-pinned (Hermes's post-Shai-Hulud policy);
the full transitive lock is requirements-lock.txt. New direct deps: pyyaml
(MIT), opentelemetry-sdk (Apache-2.0), mcp (MIT). tests/test_provenance.py
fails the build if pins become ranges, if vendored files lose provenance
headers, or if bridge modules masquerade as upstream source.

## Verification

- Clean sdist extraction on CPython 3.12.13: install OK, 155 tests pass
  (131 carried + 24 new), compileall OK, sdist + wheel build OK.
- New coverage: hardline/sudo/dangerous classification incl. quoted-prose
  cases; controller refuses hardline commands end to end; ledger lifecycle,
  occurrence dedup, incident redaction, delivery idempotency; task-runner
  ledger integration; real OTel SDK IDs/redaction/status; real MCP stdio
  roundtrip against a live server with allowlist enforcement; provenance and
  pinning guards.

## Size

10,717 code lines of Python total (tokei): 7,242 vendored/bridge under
vendor/hermes, ~3,475 Noesek's own (up from 2,793 at v1.0). 155 tests.

## Next-stage ledger (not landed in this tranche)

1. Hermes cron/jobs.py full job store + scheduler_tick (its lazy imports pull
   in gateway status, notepad, unreachable_retry, lifecycle_guard; needs
   croniter pin and a deliberate boundary decision).
2. Hermes skills/ self-improving skill system and plugins/ families
   (memory, observability, platforms) - each needs its own bridge review.
3. Hermes gateway/ channel directory + authz mixin (86k lines; vendor the
   channel directory first, not the whole gateway).
4. acp_adapter/ against the pinned `acp` SDK, giving editor/IDE interop.
5. tui_gateway/ event machinery to replace the minimal TUI.
6. Channel SDKs behind the existing channel interfaces: neonize (WhatsApp,
   Apache-2.0), slack-sdk, aiogram (both MIT).
7. Process-boundary integrations: browser-use/Playwright browser backend,
   E2B/docker-py sandbox backend, OpenCode as an ACP coding sub-agent,
   promptfoo as an external eval service.
8. Run Hermes's own evals/ suite against Noesek as the compatibility harness.

Nothing in this tranche contacts live accounts or services; the MCP test uses
a local subprocess server and OTel tests use the in-memory exporter.
