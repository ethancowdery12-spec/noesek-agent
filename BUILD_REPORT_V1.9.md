# Build report v1.9.0 - RFC 8628 device flow + incompatible-probe classification

Tranche 9 (Sep 17, 2026): RFC 8628 device authorization in the MCP client;
all 15 adapted probes now pass; the 53 incompatible probes classified by
subsystem and user value; highest-value coherent subset implemented.

## RFC 8628 device authorization (compat/mcp_device_flow.py)

- DeviceFlowClient: begin() returns only user-safe fields (user_code,
  verification_uri); the device code stays private, never logged.
- complete() polls per RFC 8628 section 3.5: authorization_pending keeps the
  interval, slow_down adds 5s, expired_token/access_denied terminate cleanly
  (error messages carry no secret material).
- FileTokenStore: 0600 JSON token files under NOESEK_HOME/tokens; the
  interface is injectable so an operator can swap in a vault-backed store.
- status() is redacted: sha256 prefix references, never token values.
- attach_device_flow() arms an MCPClient with a stored bearer token.
- Adapter mcp_device_flow now drives the real implementation against a local
  fixture covering pending, slow_down, success, expiry, redaction, and file
  permissions. ALL 15 ADAPTED PROBES PASS (0 feature-absent).

## Classification of the 53 incompatible probes

evals/incompatible-probe-classification.md groups them by subsystem with user
value, verdict, and dependency notes. License for every probe: MIT,
(c) 2025 Nous Research (pinned checkout c712f06d). Verdicts:
- Adopted this tranche (2 subsystems): output caps with local capture
  (core/output_caps.py, wired into the worker runner; captures 0600, receipts
  reference the capture file, nothing silently dropped) and tool search
  (ToolRegistry.search ranked keyword lookup).
- Already covered (7 subsystems): token accounting, compaction, session
  search, prompt footprint, approval deny dispatch, cron store/health,
  botmode DM matrix.
- Deliberate exclusions (7 subsystems): desktop app, kanban, self-update
  machinery, vendor-specific provider wires, subagent process handoff,
  browser vault fill/browser-use, Hermes TUI/CLI presentation, Hermes gateway
  HTTP API - each conflicts with the WhatsApp-first thin-controller
  architecture or pinned-release policy.
- Ledgered (6 subsystems): provider fallback chains, postmortem, memory
  depth, tool-layer specifics, auxiliary resource pool, heartbeat idle wire.

## Verification

- Full suite: 484 passed / 43 skipped (4 new tests incl. runner cap wiring).
- Adapter runner: 15/15 pass.
- No new runtime dependencies.

## Next-stage ledger

- Ledgered subsystems above, gated on product decisions.
- browser-use remains deferred (websockets downgrade).
