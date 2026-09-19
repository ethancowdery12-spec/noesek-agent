# Noesek Agent v0.8 Stage 3B build report

Pinned Hermes baseline and MIT provenance remain unchanged. This is an independent implementation; no Hermes code, prompts, assets, tests, dependencies or secrets were copied.

Stage 3B adds connector records that accept `vault://` references instead of credential values; injected full-duplex provider streaming with event-size limits; ACP session lifecycle with explicit methods and filesystem roots; immutable command batches whose digest binds image, argv, workspace and network-disabled policy to approval; injected container execution; and validated, bounded, non-overwriting session import/resume.

Verification: CPython 3.12.13, 106 tests passed in 3.94s, plus packaging checks below. Two existing non-failing FastAPI/Starlette warnings remain. No live account, provider, ACP/MCP service or container was contacted.

A production platform vault/browser connector, production container backend and PTY, ACP interoperability suite, session branching, and later compatibility gaps remain. This is progress, not parity.

Packaging: compileall passed; sdist/wheel built; clean-wheel connector/ACP/terminal-batch import smoke passed.
