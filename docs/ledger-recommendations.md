# Ledgered subsystem recommendations (tranche 10)

Grounded recommendations for the six ledgered subsystems, for Noesek's
WhatsApp-first thin-controller design. Implemented foundations are marked;
consequential choices are reserved for Ethan at the end.

## 1. Provider fallback chains (adopted: mechanism)

- User value: when the LLM provider is down or rate-limited, the assistant
  goes totally silent on WhatsApp. A fallback chain keeps replies flowing.
- Options: (a) status quo single provider; (b) ordered fallback with bounded
  retries per provider; (c) full circuit-breaker with health scoring.
- Tradeoffs: (b) adds config surface and one failure mode (falling over to a
  slower/more expensive model silently). (c) is premature at one user.
- Security/cost: failover happens only on transport errors, 429, and 5xx
  after the primary's retries - never mid-stream and never on a completed
  response, so a fallback cannot double-bill a finished generation. Each
  configured provider needs its own key (operator-managed env, redacted in
  `noesek config`).
- IMPLEMENTED: `FallbackLLM` (core/llm.py), configured via
  NOESEK_LLM_FALLBACKS (JSON list). Empty = identical single-provider
  behavior.

## 2. Postmortem (adopted: local template)

- User value: after a cron incident, a structured record beats re-reading
  raw tracebacks.
- Options: (a) local template from the vendored incident store; (b)
  LLM-drafted postmortems; (c) nothing.
- Tradeoffs: (b) sends incident data (which may embed user content) to the
  model and costs tokens for marginal polish. (a) is free, offline, honest.
- IMPLEMENTED: `noesek incidents list` and `noesek incidents postmortem <id>`
  (cli_ops.postmortem) - offline markdown from the incident row.

## 3. Memory depth (adopted: local search; semantic search reserved)

- User value: the assistant should find what it remembers. Keyword search
  covers most recall; embeddings would cover fuzzy recall.
- Options: (a) flat notes (status quo); (b) local LIKE search over active
  memories; (c) embedding-backed semantic memory.
- Tradeoffs: (c) needs an embeddings provider (new dep, per-call cost) and
  ships memory content to a third party - a real privacy decision.
- IMPLEMENTED: core/memory_search.py + `noesek memories search` - offline,
  no new deps. (c) stays with Ethan.

## 4. Tool-layer specifics (adopted: confined read_file)

- User value: workers that can read workspace files can summarize documents,
  inspect exports, and ground answers in local artifacts.
- Options: (a) no file access; (b) read_file confined to an allowlisted root
  via the vendored Hermes path-security helpers; (c) arbitrary filesystem
  reads.
- Security: (c) would let prompt-injected tool output steer reads at secrets.
  (b) confines reads to NOESEK_LOCAL_READ_ROOT (default
  NOESEK_HOME/workspace), blocks traversal, refuses non-UTF-8 and >200KB.
- Cost: none. Deferral of rarely-used tools out of the eager schema set stays
  ledgered - with four tools it saves nothing.
- IMPLEMENTED: tools/local_read.py, registered for workers as READ risk.

## 5. Auxiliary resource pool (adopted: bounded concurrency gate)

- User value: a burst of background tasks must not starve the interactive
  WhatsApp reply path.
- Options: (a) nothing; (b) a semaphore-bounded gate around LLM calls; (c)
  separate pools per priority class.
- Tradeoffs: (c) adds queueing complexity for one user; (b) is a single knob.
- Security/cost: none; pure resource governance. Default 0 = unbounded =
  today's behavior.
- IMPLEMENTED: core/llm_pool.py (LLMPool, metrics), wired into both LLM
  adapters; opt-in via NOESEK_LLM_MAX_CONCURRENT.

## 6. Heartbeat idle (adopted: internal liveness only)

- User value: an operator can see a stuck worker. Whether the assistant
  should proactively tell the USER "still working" on WhatsApp is a product
  call (annoyance vs reassurance, and every ping is the user's voice).
- Options: (a) internal heartbeat timestamps surfaced in `noesek status`;
  (b) user-facing progress pings on a cadence; (c) nothing.
- IMPLEMENTED: core/heartbeat.py; the task worker beats each loop; `noesek
  status` reports heartbeat age/liveness. (b) stays with Ethan.

## Choices reserved for Ethan

| Choice | Options | Recommendation |
|---|---|---|
| Semantic memory | local keyword (now) vs embedding-backed | Keep local until recall complaints appear; embeddings send memory content to a third party |
| User-facing progress pings | silent (now) vs cadence pings | Stay silent by default; opt-in per task ("keep me posted") fits WhatsApp norms |
| Which fallback providers | none (now) vs ordered list | Add a second OpenAI-compatible endpoint only if outages actually bite; each adds a key to manage |
| LLM-drafted postmortems | local template (now) vs model-drafted | Keep local; revisit if incident volume makes hand-writing painful |
