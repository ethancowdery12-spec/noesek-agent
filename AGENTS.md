# AGENTS.md

Guidance for coding agents working in this repo.

## What this is

noesek: a messaging-native personal agent (WhatsApp/Slack/Telegram/local chat) built as a thin layer over a vendored upstream runtime. Python 3.11+, FastAPI, SQLite (SQLAlchemy async), zero added runtime dependencies by default.

## Repo layout

- `src/noesek/` - our layer. All changes go here.
  - `core/` - controller, orchestration, context, memory, policy, providers
  - `tools/` - agent tools (research, humanize, prompt_opt, security_audit, ...)
  - `channels/`, `computer/`, `workers/`, `connectors/`
- `vendor/` - vendored upstream tree. BYTE-IDENTICAL with upstream. Never edit.
- `tests/` - pytest suite; hermetic and fresh-DB safe
- `docs/` - architecture, research roadmap, audits
- `evals/` - eval-gate fixtures

## Build and test

- No build step; install with `pip install -e .`
- Test: `python -m pytest tests/ -q --ignore=tests/test_acp_real.py`

## Rules

- Never commit to `main` directly: branch + squash-merged PR.
- Never edit `vendor/` - it stays byte-identical with upstream.
- Zero new runtime dependencies unless the owner explicitly approves.
- Tests must be hermetic and pass on a fresh database (guard Session use before init_db).
- No secrets in code, tests, docs, logs, screenshots, or commit messages.
- The user-facing name is `noesek`; the upstream name appears only in attribution files.
- Smallest change that solves the problem; no speculative features.

## PR etiquette

- Squash merge only after CI is green; delete the branch after merging.
- Keep `docs/RESEARCH_ROADMAP.md` status current when closing a study item.
