# Build report v1.7.0 - channel routers + Hermes eval compatibility harness

Tranche continuation (Sep 17, 2026): wire Slack and Telegram transports into
channel routers behind the authorization gate; integrate the pinned Hermes eval
suite as an external compatibility harness. No live accounts, no new runtime
dependencies.

## What landed

### Channel routers (all traffic through the gate)

- `channels/authorization.py`: shared gate singleton `get_gate()`; whatsapp.py
  now uses the same instance (single policy decision point across channels).
- `channels/core_controller.py`: shared `Controller` for channel requests; the
  thin controller still delegates all substantive work to scoped workers.
- `channels/slack_router.py`: `POST /webhooks/slack` - signature verification
  via the pinned slack-sdk transport (fail-closed on missing headers),
  `url_verification` challenge, authorization gate, controller, send.
- `channels/telegram_router.py`: `POST /webhooks/telegram` - secret-token
  verification, same gate/controller/send flow. Telegram transport remains the
  aiogram sidecar (pydantic <2.13 cap conflicts with the exact 2.13.5 pin).
- Both routers mounted in `main.py`.
- tests/test_channel_routers.py: 4 tests (challenge, signature rejection,
  gate deny, allowed flow).

### Hermes eval compatibility harness

- `compat/acp_server.py` + `noesek acp-serve` CLI: serve the Noesek ACP agent
  over stdio so any ACP client (including upstream wire probes and the acp
  SDK's `spawn_agent_process`) can attach. Initializes the DB schema on start.
  `NOESEK_ACP_ECHO=1` test seam: echoes the prompt without network or keys.
- tests/test_acp_stdio.py: SDK client speaks to the Noesek agent subprocess
  over real OS pipes - initialize, new_session, prompt roundtrip.
- scripts/build_eval_compat_manifest.py: mechanically classifies all 68 probes
  in the pinned Hermes eval suite (commit c712f06d...) by static import scan:
  - run: 0
  - needs-adapter: 15 (protocol exists in Noesek but the probe launches
    Hermes's own entrypoint - e.g. acp_empty_session_wire spawns
    `python -m acp_adapter` from the Hermes checkout; slack/telegram wire
    probes target Hermes's own adapters)
  - incompatible: 53 (import Hermes-internal modules gateway.*, hermes_cli.*,
    tools.*, agent.*, ... that are not part of Noesek's wire surface)
- evals/hermes-compat-manifest.json: per-probe verdict, reason, detected
  internal imports, source SHA-256. tests/test_eval_compat_manifest.py asserts
  the manifest matches a fresh rebuild (drift check).

## Verification

- Full suite: 479 passed / 43 skipped (2 new tests).
- No new runtime dependencies; requirements-lock.txt unchanged in shape.
- No live accounts connected; routers verified with synthetic webhook payloads.

## Next-stage ledger

- needs-adapter probes are the roadmap: building Noesek-targeted adapters for
  the ACP/slack/telegram/webhook wire probes would convert them to `run`.
- browser-use stays deferred (forces websockets downgrade vs exact pins).
- Sidecar Telegram process supervision in production topology remains open.
