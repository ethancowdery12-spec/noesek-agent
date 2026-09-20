# Vendored upstream source

Since v3.0.0 Stage 1, Noesek vendors the COMPLETE upstream tree of
NousResearch/hermes-agent (MIT, (c) 2025 Nous Research) at pinned commit
`d7b836ab1c0cddaafc109ed24c9a83b6191cdc88` (2026-09-19) under
`vendor/hermes-agent/` - 14,189 files, byte-identical to upstream, all
license/copyright notices intact. The upstream license is
`vendor/hermes-agent/LICENSE`.

Per-file SHA-256 provenance manifest: `vendor/VENDOR_PROVENANCE.sha256`
(header records repo, pinned commit, import time, file count; one
`sha256  path` row per file, paths relative to `vendor/hermes-agent/`).

The noesek distribution packages the upstream runtime (agent, hermes_cli,
tools, gateway, tui_gateway, cron, acp_adapter, plugins, providers + root
py-modules) as importable top-level packages, mirroring upstream's own
packaging; see `[tool.hatch.build.targets.wheel]` in `pyproject.toml`.

History: v2.x vendored a selective 50-file subset under
`src/noesek/vendor/hermes/` (pinned c712f06d) with import rewrites into the
`noesek.vendor.hermes` namespace. That subset was removed in v3.0.0 Stage 2
in favor of the full tree; the old regenerator `scripts/vendor_hermes.py`
was deleted with it.

Update procedure: re-copy the tree at a new pinned commit, regenerate
`vendor/VENDOR_PROVENANCE.sha256`, update the commit strings in this file,
`tests/upstream/MANIFEST.json`, `evals/compat-manifest.json`,
`scripts/build_eval_compat_manifest.py`, and
`tests/test_eval_compat_manifest.py`, then re-adopt any changed upstream
test files under `tests/upstream/`.
