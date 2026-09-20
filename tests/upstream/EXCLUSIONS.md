# Upstream suite exclusions (v3 S6)

The upstream-suite workflow runs the vendored upstream hermes-agent test suite
(vendor/hermes-agent/tests at pinned commit d7b836ab, MIT (c) 2025 Nous
Research) in place, in tranches. No vendored file is ever edited; exclusions
are expressed as tranche selection and `-k` filters, recorded here.

## Tranches run (10 legs)

- `tests/cron`, `tests/gateway`, `tests/plugins`, `tests/agent`,
  `tests/hermes_cli`, `tests/tui_gateway`, `tests/acp_adapter`, `tests/skills`
- `tests/tools` split in two: `not browser and not camofox` (core) and
  `browser or camofox` (needs Playwright Chromium / camofox browser infra;
  the workflow installs Chromium for this leg, camofox-dependent tests may
  still fail and are recorded as infra exclusions)

## Excluded top-level dirs (with reason)

- `tests/docker` - requires a Docker daemon and image builds
- `tests/e2e`, `tests/integration` - require live external services / network
- `tests/manual` - human-driven, not automated
- `tests/perf_guards` - timing-sensitive perf gates, flaky under shared CI
- `tests/desktop`, `tests/computer_use`, `tests/dashboard` - require a display
  server / GUI stack
- `tests/website`, `tests/verify`, `tests/ci` - repo-maintenance helpers, not
  runtime tests
- `tests/install` - exercises the upstream installer end to end (Noesek ships
  its own installer; vendored one is intentionally not run)
- `tests/evals`, `tests/conformance` - require live model API access
- `tests/providers`, `tests/monitoring`, `tests/honcho_plugin`,
  `tests/openviking_plugin`, `tests/hermes_state`, `tests/scripts`,
  `tests/fakes`, `tests/fixtures` - pending triage; most need external
  services or fixture harnesses (candidates for later tranches)
- root-level `tests/test_*.py` - pending triage (candidates for a later
  tranche)

Individual failing tests inside a run tranche are NOT edited or skipped in
source; they are reported in TRANCHE_RESULTS.json / CI artifacts. If a failure
is traced to non-vendored infrastructure, it is added to this file with the
reason.
