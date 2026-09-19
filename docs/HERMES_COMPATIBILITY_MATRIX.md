# Hermes compatibility matrix - v1.0

Pinned public baseline: `NousResearch/hermes-agent@228022ef5b209cb0a3d739394edddf887e1db0f6`, MIT. "Code-complete" means Noesek now has a tested implementation for the practical capability family while retaining stricter gates. It does not mean a live third-party service was contacted or every Hermes UI/detail was cloned.

| Family | Code status | Live certification status |
|---|---|---|
| Agent loop, tools, approvals | Code-complete core | LLM-specific long-run behavior needs live providers |
| Providers/auth/streaming | Code-complete pluggable OpenAI, Anthropic, Gemini, Bedrock, device-flow and stream contracts | OAuth, rate/failover and provider wire behavior need credentials |
| Plugins/catalog | Code-complete trust, lifecycle and isolated-runner contracts | Publisher keys, remote catalog and production container backend need deployment |
| MCP/ACP | Code-complete bounded HTTP, stdio, SSE and ACP session/framing contracts | Server-specific interoperability needs live servers |
| Terminal/runtime | Code-complete approval-bound container backend contract | Production Docker/PTY backend needs host certification |
| Sessions/memory/context | Code-complete practical storage, search, import/resume, compaction and scoped memory | Large-scale database and migration performance need deployment testing |
| Skills | Code-complete discovery/install/review/enable/disable/remove | Remote distribution and user review UX need deployment |
| Cron/subscriptions | Code-complete parsing, dispatch, state, cursor and cleanup contracts | Source adapters and clock/failure behavior need live integration tests |
| Channels/gateway | Code-complete envelopes, WhatsApp, Slack/Telegram normalization, live-send and gateway contracts | Only WhatsApp has existing implementation; authenticated Slack/Telegram/other sends and Hermes gateway need credentials/servers |
| Media/browser/computer | Code-complete gated backend contracts plus offline text/WAV/HTML implementations | Real transcription, synthesis, image/video and browser engines need services/runtime |
| Teams/peer/MoA | Code-complete ownership, limits, authenticated envelopes and replay protection | Cross-user transport needs keys and peer service |
| Telemetry | Code-complete redacted spans, SDK-shaped IDs/events/status and HTTPS OTLP export | Collector compatibility and dashboards need a live collector |
| CLI/TUI | Code-complete practical operations CLI and dependency-free TUI | Visual desktop app is presentation-only and intentionally deferred |

## Claim boundary

v1.0 reaches **code-side practical capability coverage** for every family in the pinned contract. It does **not** claim certified live parity. The remaining ledger is dominated by credentials, external services, production backends, wire certification, scale and presentation. Noesek's stricter authorization, vault references, allowlists, network-off defaults, digest-bound approvals and replay protection are intentional differences.
