# Noesek Agent v0.2.0 - build and delivery report

Date: 2026-09-17
Artifact: noesek-agent-v0.2.0.tar.gz (source repository; see SHA-256 in the accompanying email)

## What changed since v0.1

v0.1 was a verified skeleton (402 lines, 3 tests). v0.2 is a production-shaped runtime (about 2,000 lines, 63 tests):

- Background queue that actually executes: skip-locked claiming, exponential backoff, dead-lettering, results posted back to the chat
- Four specialized workers (researcher, coder, operator, evaluator) with scoped read-only tool sets and injection guardrails, reachable through a new delegate_task tool
- Approvals upgraded: 24h expiry, pending listing, one-shot execution, decision timestamps, cross-conversation isolation
- Memory retrieval: keyword-ranked recall plus recall/forget tools; context assembly enforces a character budget
- Channel hardening: per-sender rate limiting, 4,096-char outbound chunking, media acknowledgements, help/pending commands
- New tools: fetch_url (readable page text), list_tasks, cancel_task
- Reliability: per-tool timeouts and concurrency caps, LLM retries with backoff, structured errors
- Observability: append-only per-turn trace table, Prometheus /metrics, /healthz and /readyz
- Operations: noesek CLI (chat/serve/worker/migrate), idempotent schema migration for v0.1 databases
- Docs: architecture, threat model, and an honest comparison against LangGraph, CrewAI, AutoGen, and the OpenAI Agents SDK in the README

## Verification (CPython 3.12.13)

- pytest: 63 passed in ~3s, including 6 named golden end-to-end evaluations:
  1. research turns carry source URLs into citations
  2. consequential tools never execute without approval (handler call count zero)
  3. approvals are meaningless outside their conversation
  4. injected web content stays tool data; the approval gate holds even if the model obeys it
  5. replayed webhook deliveries are no-ops
  6. prompt context stays within budget under long histories
- python -m compileall src tests: clean
- uv pip check: all packages compatible
- sdist + wheel: both build successfully
- clean-wheel install into a fresh environment: imports, app metadata, CLI (--version), and full tool registry all verified

## Honest caveats

- Live WhatsApp, LLM-provider, Brave Search, and real Docker sandbox calls need credentials/services and were not exercised; they are covered by dry-run paths and mocks only.
- The comparison table in the README is a positioning statement for one job (self-hosted, safety-first WhatsApp agent), not a universal superiority claim. LangGraph, CrewAI, AutoGen, and the OpenAI Agents SDK each remain ahead in areas the README names.
- The rate limiter is per-process; multi-replica deployments need proxy-level limiting.
- Media understanding (audio/image transcription) is acknowledged but not implemented.
- Python 3.11 or 3.12 required; 3.10 unsupported.

## Setup decisions still needed (through a secure path, never chat)

Hosting target + HTTPS domain; Meta WhatsApp Cloud API token, phone-number ID, verify token, app secret; LLM base URL/model/API key; optional Brave Search key; SQLite vs PostgreSQL; sandbox isolation choice.
