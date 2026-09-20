# Upstream suite results (v3 S6, superseded)

Source: vendored upstream commit `d7b836ab` (MIT, copyright Nous Research).  
Workflow: [upstream-suite run 35494355700](https://github.com/ethancowdery12-spec/noesek-agent/actions/runs/35494355700), Ubuntu/Python 3.12, commit `9586a0d1c781e2dc2bef057d4d41cab95b325f0d`.  
Superseded methodology: all **23 CI legs completed**, but this run grouped many files in one pytest process rather than using upstream CI's per-file process isolation. Its failure totals are retained for traceability and must not be treated as defect counts. A file-isolated rerun supersedes this table. Original result as an informational compatibility inventory. The runner recorded **49,338 passed, 658 failed, 109 errors, 443 skipped, and 2 xfailed** across 5,901 test-seconds.

The upstream suite is intentionally informational: it runs the unchanged vendored tests against the Noesek integration boundary and preserves failures in artifacts rather than concealing them with source edits or skips. Noesek's release gate remains the native `eval-gate` suite. This run also caught and fixed a real dependency drift before release: ACP is pinned to the upstream-compatible `agent-client-protocol==0.9.0`.

| Tranche | Passed | Failed | Errors | Skipped | Xfailed | Deselected | Seconds | Exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `tests/acp_adapter` | 193 | 0 | 0 | 0 | 0 | 0 | 20.4 | 0 |
| `tests/agent/lsp` | 99 | 0 | 0 | 2 | 0 | 0 | 21.1 | 0 |
| `tests/agent/test_[a-f]*.py` | 4069 | 22 | 0 | 15 | 0 | 2 | 706.8 | 1 |
| `tests/agent/test_[g-m]*.py` | 1570 | 1 | 0 | 4 | 0 | 0 | 145.7 | 1 |
| `tests/agent/test_[n-z]*.py` | 4104 | 5 | 0 | 22 | 0 | 0 | 723.1 | 1 |
| `tests/agent/transports` | 393 | 0 | 0 | 0 | 0 | 0 | 18.8 | 0 |
| `tests/cron` | 1496 | 0 | 0 | 1 | 0 | 0 | 165 | 0 |
| `tests/gateway/platforms` | 6 | 0 | 0 | 0 | 0 | 0 | 3.3 | 0 |
| `tests/gateway/relay` | 402 | 0 | 0 | 0 | 0 | 0 | 12.7 | 0 |
| `tests/gateway/test_[a-f]*.py` | 2886 | 9 | 100 | 22 | 0 | 0 | 282.1 | 1 |
| `tests/gateway/test_[g-m]*.py` | 1440 | 3 | 0 | 2 | 0 | 0 | 143.7 | 1 |
| `tests/gateway/test_[n-z]*.py` | 4648 | 7 | 0 | 21 | 2 | 0 | 511.4 | 1 |
| `tests/hermes_cli/test_[a-m]*.py` | 6749 | 187 | 0 | 123 | 0 | 0 | 1091.8 | 1 |
| `tests/hermes_cli/test_[n-z]*.py` | 5144 | 368 | 9 | 99 | 0 | 0 | 557.8 | 1 |
| `tests/plugins` | 2042 | 11 | 0 | 5 | 0 | 18 | 88.8 | 1 |
| `tests/skills` | 1922 | 0 | 0 | 0 | 0 | 0 | 21.9 | 0 |
| `tests/tools/environments` | 2 | 0 | 0 | 0 | 0 | 0 | 2.5 | 0 |
| `tests/tools/test_[a-e]*.py::not browser and not camofox` | 2629 | 9 | 0 | 11 | 0 | 772 | 230.8 | 1 |
| `tests/tools/test_[f-j]*.py::not browser and not camofox` | 1087 | 0 | 0 | 12 | 0 | 1 | 71.3 | 0 |
| `tests/tools/test_[k-m]*.py::not browser and not camofox` | 1317 | 10 | 0 | 22 | 0 | 16 | 352.1 | 1 |
| `tests/tools/test_[n-z]*.py::not browser and not camofox` | 4264 | 11 | 0 | 80 | 0 | 14 | 338.8 | 1 |
| `tests/tools::browser or camofox` | 792 | 4 | 0 | 2 | 0 | 9459 | 117.3 | 1 |
| `tests/tui_gateway` | 2084 | 11 | 0 | 0 | 0 | 0 | 273.8 | 1 |
| **Total** | **49338** | **658** | **109** | **443** | **2** | **10282** | **5901** | |

## Interpretation

- 10 tranches are clean (exit 0); 13 preserve upstream-compatibility failures for follow-up.
- Collection now succeeds in every tranche, including ACP and plugins. The remaining 109 recorded errors are runtime/setup outcomes inside collected tests, not collection failures.
- Browser/camofox coverage ran with Playwright Chromium; four tests failed and 792 passed.
- Every tranche's full streamed log and machine-readable `TRANCHE_RESULTS.json` is retained as a CI artifact.
- Vendored test sources were not modified. Selection boundaries and environment-dependent omissions are documented in [EXCLUSIONS.md](EXCLUSIONS.md).
