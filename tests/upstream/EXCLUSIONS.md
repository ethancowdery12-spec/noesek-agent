# Upstream suite exclusions (v3 S6)

The upstream-suite workflow inventories the unchanged vendored upstream test
suite (`vendor/hermes-agent/tests` at pinned commit `d7b836ab`, MIT, copyright
Nous Research) in 23 parallel tranches. No vendored test is edited or silently
skipped. Path/glob selection, `-k` expressions, and every outcome are preserved
in CI artifacts and summarized in `UPSTREAM_SUITE_RESULTS.md`.

## Tranches run (23 legs)

- `tests/cron`, `tests/skills`, `tests/plugins`, `tests/tui_gateway`, and
  `tests/acp_adapter`
- `tests/agent/lsp`, `tests/agent/transports`, and root agent tests split into
  `a-f`, `g-m`, and `n-z`
- `tests/gateway/platforms`, `tests/gateway/relay`, and root gateway tests split
  into `a-f`, `g-m`, and `n-z`
- root `tests/hermes_cli` tests split into `a-m` and `n-z`
- `tests/tools/environments`; non-browser root tool tests split into `a-e`,
  `f-j`, `k-m`, and `n-z`; browser/camofox tests run separately with Playwright
  Chromium

## Top-level paths not selected

These paths require infrastructure or a mode that is outside this deterministic
fork compatibility inventory:

- `tests/docker` - Docker daemon and image builds
- `tests/e2e`, `tests/integration` - live external services or network
- `tests/manual` - human-driven
- `tests/perf_guards` - timing-sensitive performance gates on shared CI
- `tests/desktop`, `tests/computer_use`, `tests/dashboard` - display/GUI stack
- `tests/website`, `tests/verify`, `tests/ci` - upstream repository-maintenance
  helpers, not runtime behavior
- `tests/install` - upstream end-to-end installer; Noesek has its own installer
- `tests/evals`, `tests/conformance` - live model API access
- `tests/providers`, `tests/monitoring`, `tests/honcho_plugin`,
  `tests/openviking_plugin`, `tests/hermes_state`, `tests/scripts`,
  `tests/fakes`, `tests/fixtures` - external-service or dedicated fixture
  harnesses not provisioned by this workflow
- root-level `tests/test_*.py` - repository-level harness tests, outside the
  package-focused tranche inventory

Individual failures inside selected tranches are not exclusions. They remain
visible in `TRANCHE_RESULTS.json`, full CI logs, and the aggregate report so
future parity work starts from a reproducible baseline.
