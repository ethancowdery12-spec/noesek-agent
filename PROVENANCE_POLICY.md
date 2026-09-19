# Provenance and clean-room policy

Noesek's implementation provenance rules, binding on all contributors and
automation working in this repository.

## Licensed reuse

- Code is reused only under a verified, recorded license. Vendored third-party
  source lives under `src/noesek/vendor/`, carries a provenance header naming
  the upstream repo, path, and pinned commit, and is tracked with per-file
  upstream SHA-256 in `VENDORING.md`.
- Pinned external dependencies are recorded in `pyproject.toml`,
  `requirements-lock.txt`, and `THIRD_PARTY_NOTICES.md`.
- Adopted upstream tests live under `tests/upstream/`, are byte-identical to
  the upstream file at the pinned commit (drift-checked by
  `tests/test_upstream_drift.py`), and are mapped in
  `tests/upstream/MANIFEST.json`.

## Clean-room boundary: Claude Code

Noesek implements Claude Code-like behaviors (hooks around tool execution,
allow/ask/deny permissions, subagents with scoped tools, plan mode, layered
instructions, compaction, checkpoints, provider routing) strictly from:

- official Anthropic documentation,
- licensed Anthropic SDKs,
- official changelogs and release notes,
- independently observable public behavior.

Noesek must not read, copy, port, paraphrase, derive tests from, or use as
implementation guidance any leaked, decompiled, or unauthorized Claude Code
material, including the Gitlawb/openclaude repository and its forks, its
internal source layout, prompts, strings, tests, or fixtures. Public
availability of leaked material does not make it open source; a maintainer of a
leak downstream cannot grant rights to Anthropic code they never owned.

Design discussions for these features must cite the official source used, and
implementation review must be able to show the feature was specified from
permitted sources only.

(Recorded 2026-09-17 at the project owner's direction.)
