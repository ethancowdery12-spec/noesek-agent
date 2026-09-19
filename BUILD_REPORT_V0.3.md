# Noesek Agent v0.3.0 build report

Date: 2026-09-17

## Scope

Added a coherent operational CLI subset informed by Hermes Agent's public CLI:
one-shot chat, text/JSON/JSONL output, status, doctor, redacted config reads,
session list/export/explicit deletion, prompt-size reporting, local backup, and
bash/zsh/fish completion.

All code is an independent implementation on Noesek's existing controller,
database, and configuration APIs. No Hermes source, prompt, asset, dependency,
or closed-source material is included. The canonical Hermes repository was
audited at commit `228022ef5b209cb0a3d739394edddf887e1db0f6`. It is MIT licensed
by Nous Research. The full MIT notice and attribution ship with this release.

## Verification

- CPython 3.12.13
- 73 tests passed in 2.66 seconds, up from 63 in v0.2
- `compileall` clean across `src` and `tests`
- dependency compatibility check clean
- CLI smoke checks: version, doctor JSON, prompt-size JSON, completion
- dependency license inventory reviewed; no Hermes dependency added

## Caveats

- Live WhatsApp, LLM-provider, Brave Search, and Docker calls still need real
  credentials/services and were not exercised.
- `doctor` correctly reports those missing services in the clean build host.
- Backups cover a local SQLite database plus common project files. PostgreSQL
  requires an operator-managed database backup.
- Session export includes message content and must be handled as private data.
- This release incorporates a focused Hermes-inspired subset, not the entire
  Hermes CLI. Provider OAuth, plugins, ACP/MCP, desktop UI, terminal execution,
  multi-host peers, and marketplaces remain out of scope.
- Two upstream deprecation warnings appear in FastAPI/Starlette's test client;
  they do not fail tests but should be revisited when upgrading dependencies.
