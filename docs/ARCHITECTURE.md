# Architecture

```text
WhatsApp Cloud API
        |
 webhook HMAC verification, rate limiting, dedupe, media acknowledgement
        |
 conversation controller <----> context assembler
        |                           | ranked durable memories
        |                           | bounded recent history (char budget)
        v
 OpenAI-compatible model (retries + timeout)
        |
 typed tool registry ---- risk policy ---- approval record (TTL, one-shot)
   |          |                                 |
 read tools  write/external/money/destructive   approve/reject/pending
   |          |                                 |
 citations   sandbox / state / delegate <-------+
        |
 trace table (audit)      background queue (claim, retry, dead-letter)
                                   |
                    scoped workers: researcher / coder / operator / evaluator
                                   |
                     result notification back to the conversation
```

The design is hybrid: the model chooses among well-typed capabilities, while deterministic code owns validation, risk classification, authorization pauses, persistence, replay protection, and resource limits. Workers receive only read-only tools; anything consequential returns through the conversation approval gate.

## State model

- `conversations`: channel-scoped user identity
- `messages`: immutable turn history and external-ID deduplication
- `memories`: active durable notes, ranked by keyword overlap at assembly time
- `tasks`: durable background work with status, attempts, backoff schedule, result, and last error
- `approvals`: pending/decided consequential calls with expiry and decision time
- `traces`: append-only per-turn audit events

## Request flow

1. Meta verifies and posts a webhook; the adapter checks the HMAC signature.
2. A per-sender fixed-window rate limiter sheds floods before any work happens.
3. Non-text messages get a polite capability acknowledgement.
4. Commands (`approve/reject/pending/help`) are handled deterministically.
5. Otherwise the controller assembles context (ranked memories + bounded history), then runs the tool loop.
6. Read tools execute with per-tool timeouts and concurrency caps; risky tools persist an approval and the turn pauses.
7. Approved calls execute exactly once; expired approvals cannot execute.
8. `delegate_task` enqueues a worker job; the queue claims it skip-locked, retries with exponential backoff, dead-letters after `max_attempts`, and posts the result back to the chat.

## Extension points

- Add a tool: declare a Pydantic input model and register a `ToolSpec` with an explicit `Risk`.
- Add a channel adapter without changing the controller; register its sender in `channels/outbound.py`.
- Replace the OpenAI-compatible adapter behind the same `complete()` contract.
- Add worker roles in `workers/base.py` with scoped tool sets.
- Swap the DB queue for Redis/NATS/Kafka when throughput requires it.
- Add embedding retrieval behind `assemble()` while preserving provenance.

## Observability

- `/healthz` liveness, `/readyz` database readiness, `/metrics` Prometheus counters.
- The `traces` table records user messages, tool calls, approvals, and task outcomes per conversation.
