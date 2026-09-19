# Noesek Agent v0.9 Stage 4A build report

Pinned Hermes baseline and MIT provenance remain unchanged. No Hermes code, prompts, assets, tests or dependencies were copied.

Stage 4A adds a trusted plugin lifecycle requiring a trusted publisher, injected signature verification, declared-capability allowlists, canonical file digest, and digest-bound enable/disable/remove. Scanning imports no plugin code. Skills now support validated install, enable, disable and removal with name/traversal/symlink controls. Cron and event subscriptions have serializable lifecycle state, durable cursors, pause/resume and idempotent cleanup.

Verification: CPython 3.12.13; 111 tests passed in 3.51s; two existing non-failing deprecation warnings. Packaging checks follow below.

No plugin code executed, no remote catalog was trusted, no external subscription was created, and no account was connected. Isolated plugin loading, signed remote catalog ingestion, learned-skill review, full cron parsing/dispatch and live source adapters remain. This is progress, not parity.

Packaging: compileall passed; sdist/wheel built; clean-wheel plugin/skill/schedule lifecycle smoke passed.
