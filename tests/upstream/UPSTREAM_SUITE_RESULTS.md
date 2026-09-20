# Upstream suite results (v3 S6)

Source: vendored upstream commit `d7b836ab` (MIT, copyright Nous Research).  
Authoritative workflow: [run 35499259531](https://github.com/ethancowdery12-spec/noesek-agent/actions/runs/35499259531), commit `d0c7a73f`.  
Native Noesek release gate: [run 35499259538](https://github.com/ethancowdery12-spec/noesek-agent/actions/runs/35499259538), **618 passed / 44 skipped**, injection suite clean, all 15 adapter probes passed.

## Verified result

Across 23 legs and 4,894 isolated upstream test files, the runner recorded **49,947 passed, 3 failed, 0 errors, 429 skipped, and 2 expected failures**. Three files failed once and passed on the one clean-process retry that upstream CI itself uses.

**Classification of non-pass outcomes:**

- **0 genuine fork defects verified.**
- **3 failures are upstream test-fixture drift, verified by both attempts:** `test_update_command.py` (2) and `test_update_streaming.py` (1) patch `gateway.run.__file__`, but the unchanged upstream handler now resolves `Path(__file__)` in `gateway.slash_commands`; the tests therefore return “not a git repository” before their mocked spawn path. This is self-inconsistency inside the pinned unchanged upstream snapshot, not changed fork code.
- **3 transient files passed upstream's mandatory one-retry policy:** `test_cli_interrupt_drain_regression.py`, `test_finite_delegation_outcomes.py`, and `test_process_registry_list_exit.py`. These are recorded as flaky, not hidden.
- **429 skips, 2 xfails, and 10,233 deselections are selection/environment-bound.** The deselections come from the explicit browser/camofox and non-browser `-k` partition plus excluded top-level suites; reasons are in [EXCLUSIONS.md](EXCLUSIONS.md).

The runner reproduces upstream's release-test conditions: Python 3.11, the pinned `uv.lock`, all upstream CI extras, a fresh subprocess for every file, clean environment, and one retry. Vendored test or product sources are never edited. Earlier exploratory totals from shared-process or partial-dependency runs are superseded because those conditions did not match upstream CI.

| Tranche | Files | Passed | Failed | Errors | Skipped | Xfailed | Retry-pass files | Deselected | Exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `tests/acp_adapter` | 23 | 193 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/agent/lsp` | 24 | 99 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `tests/agent/test_[a-f]*.py` | 364 | 4091 | 0 | 0 | 15 | 0 | 0 | 2 | 0 |
| `tests/agent/test_[g-m]*.py` | 132 | 1571 | 0 | 0 | 4 | 0 | 0 | 0 | 0 |
| `tests/agent/test_[n-z]*.py` | 316 | 4109 | 0 | 0 | 22 | 0 | 0 | 0 | 0 |
| `tests/agent/transports` | 16 | 393 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/cron` | 128 | 1496 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| `tests/gateway/platforms` | 2 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/gateway/relay` | 47 | 402 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/gateway/test_[a-f]*.py` | 273 | 2895 | 0 | 0 | 22 | 0 | 0 | 0 | 0 |
| `tests/gateway/test_[g-m]*.py` | 173 | 1443 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `tests/gateway/test_[n-z]*.py` | 448 | 4631 | 3 | 0 | 27 | 2 | 0 | 0 | 1 |
| `tests/hermes_cli/test_[a-m]*.py` | 649 | 6936 | 0 | 0 | 123 | 0 | 1 | 0 | 0 |
| `tests/hermes_cli/test_[n-z]*.py` | 550 | 5512 | 0 | 0 | 99 | 0 | 0 | 0 | 0 |
| `tests/plugins` | 147 | 2047 | 0 | 0 | 6 | 0 | 0 | 18 | 0 |
| `tests/skills` | 51 | 1922 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/tools/environments` | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `tests/tools/test_[a-e]*.py::not browser and not camofox` | 220 | 2639 | 0 | 0 | 10 | 0 | 0 | 772 | 0 |
| `tests/tools/test_[f-j]*.py::not browser and not camofox` | 52 | 1087 | 0 | 0 | 12 | 0 | 1 | 1 | 0 |
| `tests/tools/test_[k-m]*.py::not browser and not camofox` | 122 | 1327 | 0 | 0 | 22 | 0 | 0 | 16 | 0 |
| `tests/tools/test_[n-z]*.py::not browser and not camofox` | 286 | 4255 | 0 | 0 | 59 | 0 | 1 | 14 | 0 |
| `tests/tools::browser or camofox` | 681 | 796 | 0 | 0 | 3 | 0 | 0 | 9410 | 0 |
| `tests/tui_gateway` | 189 | 2095 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **4894** | **49947** | **3** | **0** | **429** | **2** | **3** | **10233** | |

Every leg completed and uploaded its full log plus machine-readable `TRANCHE_RESULTS.json`. The workflow remains informational because the vendored snapshot's own three stale assertions cannot be corrected without violating the unchanged-vendor rule; Noesek's native release gate is blocking and fully green.
