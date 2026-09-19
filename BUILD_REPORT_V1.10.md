# Build report v1.10.0 - ledgered subsystem foundations

Tranche 10 (Sep 17, 2026): grounded recommendations for the six ledgered
subsystems (docs/ledger-recommendations.md) with the non-load-bearing
foundations implemented; consequential choices reserved for Ethan.

## Implemented (all opt-in or behavior-identical by default)

- Provider fallback: FallbackLLM (core/llm.py) - ordered chain over
  OpenAI-compatible endpoints via NOESEK_LLM_FALLBACKS; failover only on
  transport/429/5xx after bounded retries, never mid-stream (no double-bill).
  Empty config = unchanged single-provider behavior.
- Postmortem: `noesek incidents list|postmortem <id>` - offline markdown from
  the vendored incident store; no model calls.
- Memory depth: core/memory_search.py + `noesek memories search` - local
  keyword search over active memories; embedding-backed semantic memory
  reserved as Ethan's choice (privacy/cost).
- Tool layer: read_file (tools/local_read.py) confined to an allowlisted
  root via vendored path-security; traversal blocked, non-UTF-8 and >200KB
  refused; registered for workers as READ risk.
- Resource pool: core/llm_pool.py bounds simultaneous LLM calls via
  NOESEK_LLM_MAX_CONCURRENT (default 0 = unbounded = today's behavior).
- Heartbeat: core/heartbeat.py - internal worker liveness surfaced in
  `noesek status`; user-facing progress pings reserved as Ethan's choice.

## Verification

- Full suite: 491 passed / 43 skipped (7 new tests).
- No new runtime dependencies; pins unchanged (pydantic==2.13.5).

## Reserved for Ethan (docs/ledger-recommendations.md)

Semantic memory (embeddings privacy/cost), user-facing progress pings,
which fallback providers to configure, LLM-drafted postmortems.
