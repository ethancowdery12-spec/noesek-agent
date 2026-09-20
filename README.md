# Noesek Agent

Noesek Agent is a self-hostable, WhatsApp-first hybrid agent runtime: a conversational controller with typed tools, risk-classified approval gates, durable memory and tasks, specialized background workers, a database-backed job queue with retries, Docker-isolated Python execution, cited web research, an evaluation suite, and a terminal CLI. It is deliberately dependency-light: eight runtime packages, no framework lock-in, one process to run.

## Safety status

This repository does **not** contain credentials, deploy anything, connect a WhatsApp account, or send a real message by default. With missing WhatsApp credentials, outbound delivery is a dry run. Write, external, money, and destructive tool classes pause for explicit approval, approvals expire, and every turn is written to an audit trace.

## Quick start

```bash
cp .env.example .env
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
pytest                 # 605 tests
noesek                 # interactive terminal UI - try the agent locally with no WhatsApp setup
uvicorn noesek.main:app --reload
curl localhost:8000/healthz
```

`noesek` is the product's single CLI: bare `noesek` opens the interactive terminal UI, and the full command surface is documented in `docs/CLI_SURFACE.md`.

For Docker: `docker compose up --build`. For multi-instance Postgres, install `.[postgres]` and set `NOESEK_DATABASE_URL` (see `.env.example`). Upgrading a v0.1 database: `noesek migrate` adds the new columns in place.

## WhatsApp setup

Use Meta's WhatsApp Cloud API. In the Meta app dashboard:

1. Set the callback URL to `https://YOUR_HOST/webhooks/whatsapp`.
2. Set the verify token to `NOESEK_VERIFY_TOKEN`.
3. Subscribe to `messages`.
4. Store the permanent access token, phone-number ID, and app secret in `.env` or a secret manager, never in source control or chat.
5. Set `NOESEK_PUBLIC_BASE_URL` to the HTTPS origin.

In-chat commands: `approve ID`, `reject ID`, `pending`, `help`.

## What's in the box

| Area | Capability |
| --- | --- |
| Channel | WhatsApp Cloud API webhook (HMAC-verified, deduplicated, rate-limited), chunked outbound, media acknowledgements |
| Controller | OpenAI-compatible model adapter (any compatible endpoint), bounded tool loop, retries with backoff, citation capture |
| Tools | Typed Pydantic registry with per-tool timeouts, concurrency caps, and five risk classes; built-ins: web search, page fetch, sandboxed Python, memory (remember/recall/forget), tasks (create/list/cancel), worker delegation |
| Approvals | Persisted approve/reject in-conversation, 24h expiry, pending listing, cross-conversation isolation, one-shot execution |
| Workers | Four scoped roles (researcher, coder, operator, evaluator) with read-only tool sets and injection guardrails; delegated via `delegate_task` and executed by the queue |
| Queue | Durable DB-backed worker: skip-locked claiming, exponential backoff retries, dead-lettering, result notifications back to the chat |
| Context | Ranked memory retrieval, history window, character-budget trimming with omission notices |
| Observability | Append-only trace table per turn, Prometheus `/metrics`, `/healthz` and `/readyz` |
| Operations | CLI (`noesek chat/serve/worker/migrate`), idempotent schema migrations, env-based config |
| Evaluation | 63-test suite including 6 golden end-to-end scenarios (see below) |

## How it compares

An honest positioning against the frameworks studied before this build. "Better" here means better for a specific job: a self-hosted, safety-first personal agent on WhatsApp. It is not a universal claim.

| Capability | Noesek 0.2 | LangGraph | CrewAI | AutoGen | OpenAI Agents SDK |
| --- | --- | --- | --- | --- | --- |
| WhatsApp-native channel with signed webhooks | built in | DIY | DIY | DIY | DIY |
| Durable human-approval gates with expiry and audit | built in, DB-persisted | interrupts (you build persistence) | basic human input flag | via user-proxy agent | hosted or DIY |
| Risk classification enforced outside the model | five classes, deterministic | DIY | limited | limited | guardrails API |
| Sandboxed code execution defaults | Docker: no network, read-only root, CPU/mem/PID caps | DIY | optional container | Docker/Jupyter options | DIY |
| Background durable task queue with retries/dead-letter | built in | via checkpointer + DIY | limited | DIY | DIY |
| Zero hosted-service requirement | yes (SQLite default) | yes | yes | yes | no (platform-tied features) |
| Runtime dependency footprint | 8 packages | large graph stack | large | large | medium |
| Graph/state-machine orchestration depth | simple loop by design | best in class | role crews | conversational multi-agent | handoffs |
| Ecosystem, examples, community | new | large | large | large | growing |
| Hosted eval/observability platform | self-hosted traces/metrics | LangSmith | basic | basic | built-in tracing |

Where others remain ahead: LangGraph's graph orchestration and LangSmith observability, CrewAI's role-play ergonomics and examples, AutoGen's multi-agent research depth, and the OpenAI SDK's managed tracing. Where Noesek is deliberately ahead: opinionated safety defaults (approvals, risk classes, sandboxing, injection-tested boundaries), a complete WhatsApp product loop out of the box, and a runtime small enough to read in an afternoon.

## Evaluation

`pytest` runs 605 tests in about 3 seconds on Python 3.12, including these named golden scenarios (`tests/test_golden_evals.py`):

1. Research turns must carry source URLs into citations.
2. Consequential tools never execute without approval - handler call count stays zero.
3. An approval id from one conversation is meaningless in another.
4. Hostile fetched content reaches the model only as tool data, and even a model that obeys the injection still hits the deterministic approval gate.
5. Replayed webhook deliveries are no-ops.
6. Prompt context stays within its character budget under long histories.

The rest of the suite covers typed validation, tool timeouts, duplicate registration, HMAC verification, chunking, rate limiting, retrieval ranking, budget trimming, task retries/backoff/dead-letter, worker scoping, migrations, CLI, and webhook behavior. Recommended next suites: live-provider smoke tests, citation-quality grading, sandbox escape attempts, and cost/latency regression runs against a fixed model.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Build verification

CI and deployment must use Python 3.11 or 3.12, matching `requires-python`; Python 3.10 is unsupported. This release was verified on CPython 3.12: compileall, full pytest suite, sdist/wheel builds, and clean-wheel import.

## v0.3 operational CLI

v0.3 adds a focused operational command set while keeping Noesek small and
WhatsApp-first:

```bash
noesek chat --oneshot -q "Summarize this" --format json
noesek status --json
noesek doctor --json
noesek config llm_model
noesek sessions list --limit 20
noesek sessions export 1 --output session.json
noesek sessions delete 1 --yes
noesek prompt-size --json
noesek backup noesek-backup.zip
noesek completion bash
```

Machine formats keep scripted use stable. Configuration output redacts secrets;
session deletion needs an explicit `--yes`; backup remains local and never
uploads data. See `THIRD_PARTY_NOTICES.md` and `VENDORING.md` for the
upstream attribution and license review.

---

## Windows install - v3.1.0

Requires Python 3.11 or newer. The installer verifies pinned SHA-256 hashes, uses a non-admin isolated environment, preserves existing configuration, uses atomic activation, adds its command directory to the user PATH, and exposes the `noesek` command. Open a new terminal after installation, then run `noesek`.

### PowerShell

```powershell
$ErrorActionPreference='Stop'; $u='https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v3.1.0/7-install.ps1'; $p=Join-Path $env:TEMP ('noesek-'+[guid]::NewGuid()+'.ps1'); curl.exe -fL --proto '=https' --tlsv1.2 $u -o $p; if($LASTEXITCODE -ne 0){throw 'installer download failed'}; if((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -ne 'fbdc438c766098141993fa62ce039b92dcea51d66f7e7a77670e2c4bb8744734'){throw 'installer checksum mismatch'}; & $p -ReleaseUrl 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v3.1.0/8-noesek-agent-v3.1.0.tar.gz' -ExpectedSha256 '311ec12aeba007508fc71faa4a7a7575ab7571c6951240f9b857bab14f1871c5'; $c=$LASTEXITCODE; Remove-Item $p -Force; exit $c
```

### Command Prompt (CMD)

```bat
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $u='https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v3.1.0/7-install.ps1'; $p=Join-Path $env:TEMP ('noesek-'+[guid]::NewGuid()+'.ps1'); curl.exe -fL --proto '=https' --tlsv1.2 $u -o $p; if($LASTEXITCODE -ne 0){throw 'installer download failed'}; if((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -ne 'fbdc438c766098141993fa62ce039b92dcea51d66f7e7a77670e2c4bb8744734'){throw 'installer checksum mismatch'}; & $p -ReleaseUrl 'https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v3.1.0/8-noesek-agent-v3.1.0.tar.gz' -ExpectedSha256 '311ec12aeba007508fc71faa4a7a7575ab7571c6951240f9b857bab14f1871c5'; $c=$LASTEXITCODE; Remove-Item $p -Force; exit $c"
```

Release: https://github.com/ethancowdery12-spec/noesek-agent/releases/tag/v3.1.0

## Release hashes

- PowerShell installer SHA-256: `fbdc438c766098141993fa62ce039b92dcea51d66f7e7a77670e2c4bb8744734`
- Source archive SHA-256: `311ec12aeba007508fc71faa4a7a7575ab7571c6951240f9b857bab14f1871c5`
