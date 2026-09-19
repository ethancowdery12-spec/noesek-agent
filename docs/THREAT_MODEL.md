# Threat model

## Protected assets

WhatsApp and model credentials, private conversation content, durable memory, approval integrity, host filesystem, network, and external accounts reached by tools.

## Main threats and controls

- Forged webhooks: verify Meta's `X-Hub-Signature-256` with the app secret; empty secret is an explicit dev mode.
- Replay/duplicate delivery: unique external message IDs; redelivery is a no-op (tested).
- Floods and abuse: per-sender fixed-window rate limiting before processing; one notice per window.
- Prompt injection via web content: retrieved content only ever enters the prompt as tool data; risk enforcement is outside the model; a golden evaluation proves a model that obeys an injection still cannot execute a money tool without approval.
- Unapproved effects: write/external/money/destructive tools persist exact arguments and pause; approvals are one-shot, expire after a TTL, and are scoped to the originating conversation (tested).
- Privilege creep by background workers: workers receive only read-only tools; consequential work must return through the approval gate.
- Arbitrary code: disposable Docker container, no network, read-only root, CPU/memory/PID limits and timeout.
- Runaway loops and cost blowouts: bounded tool steps, per-tool timeouts and concurrency caps, LLM retries with backoff, context character budgets.
- Secret leakage: environment/secret manager only; `.env` ignored; no secrets in prompts by default.
- Silent failures: append-only trace table, structured task errors with dead-letter state, Prometheus counters.

## Production hardening

Do not expose the Docker socket directly to an internet-facing service. Run sandbox execution in a separate service/VM, allow-list images, pin image digests, use seccomp/AppArmor, disable privilege escalation, impose disk quotas, and log every execution. Encrypt database backups, add retention controls, redact logs, terminate TLS at a reverse proxy, and add tenant-aware authentication before serving multiple users. The in-memory rate limiter is per-process; front multiple replicas with a shared limiter or proxy-level limiting.
