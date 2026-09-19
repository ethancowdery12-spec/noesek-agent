# Noesek v1.3 - open-source reuse tranche 3

September 17, 2026. Third tranche of the approved reuse matrix: the gateway's
channel directory + config stack, and the plugin loader core. ACP adapter was
assessed and deferred - see the ledger.

## What landed (on top of v1.2, same pin c712f06d)

- **gateway/config.py + config_loader.py** (1,261 lines): the gateway's typed
  platform configuration model and YAML layer merging, bridged to Noesek's
  settings (Hermes config writes are refused; Noesek owns configuration).
- **gateway/channel_directory.py** (473): the durable channel directory -
  name/type resolution across platforms from session history, alias support,
  display formatting. Wired as `noesek.channels.directory.ChannelDirectory`.
- **gateway/shutdown_watchdog.py** (380): shutdown diagnostics support used by
  the gateway config stack.
- **plugins/ loader core** (plugin_loader, plugin_storage, plugin_utils):
  plugin discovery, description, storage over the vendored sqlite layer. Wired
  as `noesek.compat.plugins_real.PluginRegistry`, rooted at the Noesek home's
  plugins/ dir. Discovery and description only - executing plugin code stays
  behind a future approval-gated step.
- New marked bridges: gateway restart constant, empty platform registry,
  profile routing (none), platforms/_shared helpers, hermes_cli plugins/auth/
  managed_scope.

Vendored total: 46 upstream files (~17,600 lines). Bridges: 28 marked modules.

## Verification

- 165 tests pass on CPython 3.12.13 (163 carried + 2 new: channel directory
  resilience/resolution, plugin discovery).
- Clean-sdist install + suite green; compileall OK; sdist + wheel built.
- No live account or service contacted.

## ACP adapter assessment (deferred)

acp_adapter/ (14 files, 4,163 lines) imports the `acp` Python SDK plus
agent.context_compressor and the Hermes session/agent machinery - adopting it
means either vendoring Hermes's session core (duplicating Noesek's controller,
which the matrix rejects) or writing a Noesek-backed SessionState shim behind
the pinned acp SDK. That shim is the right design but is its own tranche; the
boundary decision is recorded here rather than half-landed.

## Next-stage ledger

1. ACP adapter against pinned `acp` SDK with a Noesek-backed SessionState shim
   (editor/IDE interop).
2. gateway/authz_mixin + pairing + session + whatsapp_identity chain (the
   authorization boundary proper) - needs gateway/session.py's dependency web
   resolved through bridges; ~3,200 lines upstream plus deps.
3. plugins/ families with live services (memory/mem0, observability) behind
   process or service boundaries; plugin code execution gate.
4. Skill template/inline-shell preprocessing (executes skill content; needs
   policy review).
5. tui_gateway/ event machinery; channel SDKs (neonize/slack-sdk/aiogram);
   browser-use/Playwright; E2B/docker-py; OpenCode over ACP; promptfoo.
6. Hermes evals/ as the compatibility harness.
