# Noesek Agent v0.10 Stage 4B build report

Pinned Hermes baseline and MIT provenance remain unchanged. No Hermes code, prompts, assets, tests or dependencies were copied.

Stage 4B adds JSON-only plugin invocation through an injected isolation backend with no-network/read-only policy and request/response caps; trusted signed catalog ingestion requiring publisher trust, HTTPS and package SHA-256 pins; evidence-backed learned-skill proposals requiring a named review decision; bounded five-field cron parsing with lists, ranges, steps and deduped dispatch; and idempotent source-adapter start/stop with durable cursor contracts.

Verification: CPython 3.12.13; 116 tests passed in 3.53s; two existing non-failing warnings. Packaging checks follow.

No plugin was executed on a host, no remote catalog or account was contacted, and no live subscription was created. A production container backend, publisher key distribution, concrete live-source adapters and distributed scheduling remain, along with the broader channel/media/browser/desktop/team gaps. This is progress, not parity.

Packaging: compileall passed; sdist/wheel built; clean-wheel plugin/cron/source import smoke passed.
