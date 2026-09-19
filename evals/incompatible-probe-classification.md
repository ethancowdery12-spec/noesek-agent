# Classification: 53 incompatible Hermes eval probes (pinned commit c712f06d)

License: all probes are part of the Hermes repository, MIT License,
(c) 2025 Nous Research (hermes-src/LICENSE). Provenance: pinned checkout
c712f06dcdd24053a4118f38d2090ac53137ecfc; per-probe content SHA-256 in
evals/hermes-compat-manifest.json. Dependency notes refer to what adopting
the SUBSYSTEM would require, not the probe.

## Adopted this tranche (2 subsystems, 4 probes)

| Subsystem | Probes | User value | Noesek landing |
|---|---|---|---|
| Output caps with local capture | output_caps_local_capture.py, output_caps_surfaces.py, output_caps_scope.md | Worker tool results can be huge; capping with full local capture prevents context floods without losing data | core/output_caps.py wired into workers/runner.py; capture files 0600 under NOESEK_HOME/captures |
| Tool search | tool_search | Discovering tools by keyword as the registry grows | ToolRegistry.search ranked lookup |

## Already covered by Noesek (no adoption needed)

| Subsystem | Probes | Existing Noesek surface |
|---|---|---|
| Token accounting | token_accounting | core/usage.py Usage dataclass |
| Compaction | compaction, native_compaction | core/compression.py compact() |
| Session search/schema | session_search_schema, session_snapshot_removal.py | core/sessions.py search_session + sessions CLI |
| Prompt footprint | prompt_footprint | `noesek prompt-size` CLI |
| Approval deny dispatch | approval_deny_dispatch.py | core/approval_engine.py (v1.1) |
| Cron store/health | botmode-dm-delivery, cron_timeout_fork_race.py | vendored hermes cron stack (v1.2) |
| Botmode DM matrix | botmode-dm-matrix | channel routers + gate (v1.7) |

## Deliberate exclusions (conflict with Noesek's architecture)

| Subsystem | Probes | Reason |
|---|---|---|
| Desktop app | desktop-pane-fixture, desktop-reap-clock-pressure.cjs, desktop_bug_campaign, desktop_mcp_oauth | Noesek is WhatsApp-first server/CLI; no desktop surface |
| Kanban board | kanban_graph_identity.py, kanban_pr_acceptance_live.py, kanban_scope_probe.py | Project-management subsystem; doesn't fit the thin controller |
| Self-update machinery | update_check_ssh_pty.py, update_obligation_identity.py, update_pipeline, update_streaming, update_unit_client_budget.py | Auto-update conflicts with pinned, verified, reproducible releases |
| Vendor-specific provider wires | anthropic_proxy_thinking_replay.py, codex_echo, codex_masked_replay_review.py, openrouter_pkce_ab, provider_wire, providers | Vendor replay/thinking/PKCE specifics; Noesek uses an OpenAI-compatible gateway |
| Subagent process handoff | subagent_process_handoff | Workers run in-process by design; the thin controller forbids recursive spawn |
| Browser vault fill / browser-use | vault_fill_live_e2e.py, browser_use | Deferred with browser-use (forces websockets downgrade vs exact pins) |
| Hermes TUI/CLI presentation | cli_deferred_notice.py, key_cmd_picker_live.py, dashboard_auth, liveness | Probes measure Hermes's own TUI; Noesek's tui.py is a different surface |
| Hermes gateway HTTP API | api_delegation_http_probe.py, api_delegation_sync_probe.py, gateway_completion, gateway_failure_ownership, gateway_status_render, completion_backlog_probe.py | Surface-specific to Hermes's gateway; Noesek's routers are the boundary |

## Ledgered (revisit if the subsystem lands later)

| Subsystem | Probes | Note |
|---|---|---|
| Provider fallback chains | provider_fallback | core/providers.py is single-gateway; a fallback chain would need its own probes |
| Postmortem machinery | postmortem | Builds on vendored incidents; low value until incident volume exists |
| Memory subsystem depth | memory | db.Memory model exists; deeper semantic memory is a design decision |
| Tool-layer specifics | readtool, core_tool_deferral | Implementation-specific to Hermes tool defs |
| Auxiliary resource exhaustion | auxiliary_resource_exhausted.py | Hermes auxiliary-client pool behavior |
| Heartbeat idle wire | heartbeat_idle_wire.py | jobs.py watcher covers cancellation; idle heartbeat needs a product decision |
