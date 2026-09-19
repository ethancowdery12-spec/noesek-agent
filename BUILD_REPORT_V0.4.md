# Noesek Agent v0.4 Stage 1 build report

- Baseline archive SHA-256: `5abb1180e2efc9c10f12a0d91d3f61eba59afd118a2cc14074b68f01d6d20ffb`
- Hermes baseline: `NousResearch/hermes-agent@228022ef5b209cb0a3d739394edddf887e1db0f6`
- Upstream: https://github.com/NousResearch/hermes-agent
- License: https://github.com/NousResearch/hermes-agent/blob/228022ef5b209cb0a3d739394edddf887e1db0f6/LICENSE
- Provenance verified by a pinned Git checkout. License is MIT, Copyright 2025 Nous Research.
- Implementation: independent compatibility modules; no Hermes source, prompts, assets, tests or dependencies copied.

## Verification

- CPython 3.12.13
- `pytest -q`: 81 passed in 3.30s, 2 non-failing FastAPI/Starlette test-client deprecation warnings
- `compileall`: passed
- provider CLI smoke test: passed
- sdist/wheel and clean-wheel smoke test: recorded below after packaging

## Scope

This is Stage 1, not full parity. It adds an explicit matrix and tested foundations for providers, skills, plugin manifests, MCP policy, terminal execution policy, interval scheduling, and CLI inspection. See `docs/HERMES_COMPATIBILITY_MATRIX.md` and `docs/HERMES_FULL_PORT_PLAN.md` for exact gaps.
- sdist and wheel: passed
- clean-wheel smoke: version 0.4.0, 9 providers
