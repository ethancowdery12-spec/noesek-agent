# Noesek Agent v1.0 consolidated code-side parity build

Source baseline: verified Noesek v0.3 archive SHA-256 `5abb1180e2efc9c10f12a0d91d3f61eba59afd118a2cc14074b68f01d6d20ffb`.
Hermes reference: https://github.com/NousResearch/hermes-agent at `228022ef5b209cb0a3d739394edddf887e1db0f6`; MIT notice: https://github.com/NousResearch/hermes-agent/blob/228022ef5b209cb0a3d739394edddf887e1db0f6/LICENSE.

No Hermes source, private prompts, assets, tests, dependency lockfiles or vendored dependencies were copied. Noesek contains independent implementations of the practical capability families and the upstream MIT notice/attribution.

Final stage adds a pinned capability contract, safe WAV metadata and offline HTML backends, authenticated peer envelopes with freshness/signature/recipient/replay checks, SDK-shaped trace/span IDs/events/status and a dependency-free TUI.

Verification before clean extraction: CPython 3.12.13, 131 tests passed in 3.62s, two non-failing upstream FastAPI/Starlette test-client warnings.

The compatibility matrix distinguishes code-complete families from live certification. v1.0 does not claim live-service parity; see `docs/LIVE_CERTIFICATION_LEDGER.md`.

Clean extraction: editable install succeeded; 131 tests passed; compileall passed; version and pinned-contract smoke passed; sdist and wheel were built before archive creation.
