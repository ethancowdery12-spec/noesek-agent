# Noesek Agent v0.11 Stage 5A build report

Pinned Hermes baseline and MIT provenance remain unchanged. No Hermes code, prompts, assets, tests or dependencies were copied.

Stage 5A adds transport-neutral channel envelopes and non-live Slack Events/Telegram webhook normalization; media type/size/hash controls with injected malware scanner and processor/transcriber; computer plans bound to allowed origins/actions and approval digests; team runs with explicit outcome owner, bounded unique membership, step limits, owner-only completion and termination; and redacted portable spans with bounded JSON export.

Verification: CPython 3.12.13; 121 tests passed in 3.05s; two existing non-failing warnings. Packaging follows.

No account was connected and no message was sent. No media engine, browser or desktop was driven. Authenticated/live channel adapters, concrete media/browser engines, gateway interoperability, OpenTelemetry wire export, TUI/desktop and peer/MoA transport remain. This is progress, not parity.

Packaging: compileall passed; sdist/wheel built; clean-wheel gateway/media/team/telemetry smoke passed.
