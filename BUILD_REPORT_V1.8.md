# Build report v1.8.0 - Hermes eval probe adapters + Telegram sidecar topology

Tranche 8 (Sep 17, 2026): Noesek-targeted adapters for all 15 Hermes eval
probes previously classified needs-adapter, preserving behavioral intent and
upstream provenance without patching or running Hermes entrypoints. Telegram
sidecar supervision topology documented as an operator-owned process boundary.

## What landed

### Eval adapters (evals/adapters/, run by evals/run_adapters.py)

All 15 needs-adapter probes now have adapters; verdicts: 14 pass, 1
feature-absent (mcp_device_flow - Noesek's MCP client has no RFC 8628
device-flow support; the local wire fixture is validated independently and the
gap is recorded, not hidden).

- acp_wire (acp_empty_session_wire.py): raw NDJSON JSON-RPC against the real
  acp-serve subprocess; wire transcript + empty-session DB measurements.
- auth_controls (auth_pool_controls.py): full pairing lifecycle through the
  production CLI and vendored PairingStore in an isolated home; approvals
  survive fresh processes; revoke works.
- config_atomicity (cli_fallback_add_picker_error.py): config tree
  byte-identical after read commands and a failing key lookup; failing lookup
  exits 2 with a clean message. REAL FIX: `noesek config <name>` previously
  crashed with a KeyError traceback on unknown keys.
- codebase_navigability: runs the pinned upstream static_metrics.py UNMODIFIED
  against the Noesek tree (codebase-agnostic offline tool) - a true run.
  Added radon==6.0.1 to the test extra for it.
- cron_errors (cron_error_diagnostics.py): failing execution persists the real
  traceback; repeat failures dedup to one incident; incident is listed.
- schema_footprint (delegation_group_schema): per-worker compact-JSON schema
  receipts; deterministic across runs. Deviation: byte counts, not tiktoken
  tokens (no tokenizer pinned).
- telegram_flood (delivery_flood_wire.py): 50 updates (45 unique + 5 duplicate
  update_ids) through the real router/gate/controller over ASGI; exactly one
  delivery attempt per unique update; duplicates deduped.
- session_persistence (gateway/session_time_persistence_*): timestamps stable
  across fresh processes on the same sqlite file.
- schema_arrays (gemini_type_array_probe.py): every array node in Noesek tool
  schemas declares items. Deviation: Noesek schemas, not the Gemini SDK.
- command_parity (goal_command_parity.py): pairing command sequence parity
  across fresh processes/homes modulo volatile timestamps (same presentation
  caveat as upstream). Deviation: pairing surface (Noesek has no /goal).
- process_receipt (process_result_receipt_probe.py): with no container backend
  available, verifies error-receipt fidelity (structured backend error through
  the production registry; host execution is out of bounds by design). Runs
  the live producer automatically where docker/e2b exists.
- slack_wire (slack_stream_wire_contract.py): local aiohttp receiver records
  every outbound call from the real slack-sdk client; signed inbound event
  flows through the router to an outbound chat.postMessage with the documented
  auth/body contract.
- orchestration_overhead (toolperf_abeval): three-task battery (plain, one
  tool call, unknown-tool recovery) with a scripted LLM fixture; turns/steps/
  bytes/wall recorded. Deviation: measures orchestration, not model quality.
- webhook_signatures (webhook_auth/standard_webhooks_ab.py): full
  accept/reject matrix over ASGI (valid/tampered/missing for Slack v0 HMAC and
  Telegram secret token). Deviation: provider-native schemes, not svix.

evals/run_adapters.py executes each adapter in its own subprocess and writes
evals/hermes-adapter-results.json mapping upstream probe content SHA-256 (from
the pinned compat manifest) to adapter path + verdict. The compat manifest now
classifies all 15 as "adapted" (0 needs-adapter remain; 53 Hermes-internal
probes stay incompatible). tests/test_eval_adapters.py runs the whole suite.

### Telegram sidecar topology (docs/telegram-sidecar.md)

Operator-owned process boundary: sidecar owns the bot token and Telegram API
interaction; core owns authz/policy and never holds the token; shared
webhook secret authenticates the sidecar; systemd supervision example with
restart/health/upgrade semantics. No user choice required.

## Verification

- Full suite: 480 passed / 43 skipped (new adapter-suite test runs all 15).
- Runner: 14 pass + 1 feature-absent in ~22s.
- Deps: radon==6.0.1 added to the test extra only; runtime pins unchanged
  (pydantic==2.13.5 re-verified).

## Next-stage ledger

- mcp_device_flow: implement RFC 8628 in the MCP client to close the gap.
- 53 incompatible probes measure Hermes-internal subsystems Noesek does not
  have (kanban, codex, desktop, moa, provider transports); any further
  conversion means porting those subsystems, which is out of scope.
- browser-use remains deferred (websockets downgrade).
