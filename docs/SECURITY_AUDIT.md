# Security Audit - noesek-agent

Generated 2026-09-21 by the `security_audit` tool (P8, roadmap item 33; own bounded implementation of the `usestrix/strix` idea, Apache-2.0). Scope: our own source layer (`src/noesek/`); the vendored upstream tree (`vendor/`) is byte-identical to upstream and out of scope for fixes.

## Summary

2 finding(s): 1 high, 0 medium, 1 low; 7 route(s), 5 without declared dependencies.

## Findings

| Severity | Probe | Location | Disposition |
|---|---|---|---|
| high | shell-true | `ui.py:368` | ACCEPTED - the TUI `! <command>` escape runs the local user's own typed command on their own machine; a dangerous-command guard (`shell_command_kind`) already refuses destructive patterns. The user is the principal; there is no privilege boundary crossed. |
| low | bind-all | `main.py:48` | ACCEPTED - uvicorn binds 0.0.0.0 inside the container/VM; Render terminates TLS and routes only its own traffic. |

## Route inventory

| Path | Methods | Declared dependencies |
|---|---|---|
| `/docs` | GET, HEAD | none |
| `/docs/oauth2-redirect` | GET, HEAD | none |
| `/healthz` | GET | none |
| `/metrics` | GET | none |
| `/openapi.json` | GET, HEAD | none |
| `/readyz` | GET | none |
| `/redoc` | GET, HEAD | none |

Routes without declared dependencies are the FastAPI defaults (`/docs`, `/redoc`, `/openapi.json`), `/healthz`, `/readyz`, and `/metrics`. Channel webhooks verify provider signatures at the handler level (checked during P1), so they carry no FastAPI-level dependency entry.

## Probes

dynamic-exec, shell-true, os-system, pickle-loads, yaml-unsafe, tls-noverify, cors-wildcard, hardcoded-secret (placeholder-aware), sql-fstring, bind-all. Re-run any time: ask the agent to "run a security audit".
