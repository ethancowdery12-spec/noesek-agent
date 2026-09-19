# Noesek v1.4.0 - reuse tranche 4: ACP shim + gateway authorization chain + upstream test adoption

Hermes pin: c712f06dcdd24053a4118f38d2090ac53137ecfc (v0.21.3, MIT).

## What landed

1. **ACP server shim** (`compat/acp_real.py`, SDK-pinned `agent-client-protocol==0.12.1`):
   ACP sessions map 1:1 to Noesek conversations; prompts run through the Noesek
   Controller, so approvals, risk classes, and audit apply unchanged. Pending
   approvals surface as ACP permission requests (allow_once/reject_once) when the
   client supports them, else in-chat approve/reject text.
2. **Gateway authorization/pairing/identity chain** (vendored verbatim):
   `gateway/whatsapp_identity.py`, `gateway/bot_loop_guard.py`, `gateway/pairing.py`,
   `gateway/authz_mixin.py`. New Noesek-authored bridges: `gateway/session.py`
   (verbatim `SessionSource` port, upstream lines 60-161), `gateway/run.py` (logger +
   always-None runner ref), `hermes_cli/config.py` env-mirror write refusals.
   `gateway/platforms/_shared.py` bridge upgraded to documented single-profile
   behavior (Noesek is single-profile; multiplex rungs collapse to os.environ).
3. **`channels/authorization.py` - NoesekAuthorizationGate**: hosts the vendored
   mixin without a GatewayRunner. Noesek settings are the configuration owner,
   projected into the platform env allowlist keys the vendored chain reads;
   operator-set env always wins (upstream env-over-config contract). Pairing store
   under NOESEK_HOME. Wired into WhatsApp ingress: deny-by-default, pairing-code
   handshake for unknown DMs ("pair"/"ignore"/"decline" behaviors), bot loop guard.
4. **CLI**: `noesek pairing approve|revoke|list|pending`.
5. **Selective upstream test adoption** (`tests/upstream/`): 12 Hermes test files,
   byte-identical, run unchanged against the vendored namespace via an import-alias
   conftest. 255 upstream tests pass. 43 test IDs skipped with recorded reasons
   (non-vendored infrastructure); 1 file rejected (GatewayRunner fixture).
   `tests/upstream/MANIFEST.json` maps each file to upstream path/commit/SHA-256;
   `tests/test_upstream_drift.py` enforces byte-identity and pin agreement.
6. **Clean-room boundary**: `PROVENANCE_POLICY.md` records that Claude Code-like
   features are specified only from official Anthropic docs, licensed SDKs,
   changelogs, and observable public behavior; Gitlawb/openclaude and all leaked
   Claude Code material are barred (no reading, copying, porting, paraphrasing,
   test derivation, or layout guidance).

## Verification

- 438 passed, 43 skipped (255 of the passes are unchanged upstream Hermes tests).
- Provenance guards: 50 vendored files hash/header-checked; 30 bridges marked
  not-upstream; upstream-test drift check green.
- Contract labels: approvals/cron/skills/plugins/gateway-authz = vendored;
  telemetry/mcp/acp = pinned SDK; gateway runner = not vendored (Noesek owns orchestration).

## Next-stage ledger

- SessionStore mixins (persistence/recovery/lifecycle/transcript) - deep chain
  (~3.4k lines) around SQLite session routing; evaluate per need, Noesek SQL store
  currently owns sessions.
- Remaining approved reuse list, later tranches: browser-use/Playwright tool backend,
  E2B/docker-py sandbox backend, promptfoo eval harness, channel SDKs (Telegram/Slack),
  relevant upstream eval suites; OpenCode/OpenClaw patterns clean-room from docs only.
- ACP: load_session/resume_session/fork_session, ext methods, terminal passthrough.
- Gateway: media policy/fetch, delivery ledger, hosted rooms (deferred; service
  boundaries for live-service plugin families per plan).
