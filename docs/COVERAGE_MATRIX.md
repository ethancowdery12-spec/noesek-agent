# Coverage matrix (lane A: end-to-end pass over everything built)

Generated Sep 23, 2026 from the live registry dump (35 tools), the playbook
table (12), the computer surface, and a full-text scan of tests/. Statuses:
- UNIT: exercised by the pytest suite (test files listed)
- E2E: exercised end-to-end through a running app (local unless marked LIVE)
- VERDICT: works / broken (with evidence)

## Subsystems

| Subsystem | Surface | Unit coverage | E2E | Verdict |
|---|---|---|---|---|
| Chat core | POST /chat | extensive (orchestration, stage3/4) | LIVE daily | works (13-14s warm) |
| Cron / scheduled tasks | create_task + jobs.py task_worker + CronLedger (croniter) | test_cron_dispatch, test_vendor_cron, test_stage4_lifecycle, test_adapters_admin, test_tranche10_foundations | pending | pending live check |
| Computer / VM | /computer/browse, /computer/screenshot, browser-state import | test_computer_server, test_browser_state, test_browser_backend | pending | pending |
| Connector framework | /connectors/* endpoints + core/connectors.py + connectors/google.py + connector_reads.py | test_connector_tools | pending | framework EXISTS (lane B extends) |
| MCP client | library_docs via Context7 + NOESEK_MCP_EXTRA_SERVERS | test_mcp, test_mcp_live (manual) | pending | pending |
| Memory: FTS+keyword | recall/memory_get | test_memory_v2, test_progressive_memory | LIVE daily | works |
| Memory: vector | core/memory_vector.py | test_vector_memory | pending | pending |
| Memory: graph | core/memory_graph.py | test_graph_memory, test_memory_frontier | pending | pending |
| Multi-model | switch_model, model catalog | test_multimodel | LIVE (deepseek-chat/reasoner) | works |
| Approvals | approval_engine + intercepts | test_chat_approve_intercept, upstream/tools/test_approval | LIVE | works |
| Browser session persistence | browser_cookies + encrypted store | test_browser_state | pending | pending |
| Needle router | needle_router.py (currently OFF) | test_needle_router | OFF by owner call | parked |
| Voice | speak | test_voice | pending | pending |
| Sandbox backends | docker / local-subprocess / e2b | test_sandbox_backends | pending | pending |

## Registry tools (35)

| Tool | Risk | Unit test files | E2E | Verdict |
|---|---|---|---|---|
| adversarial_review | READ | test_adversarial | pending | pending |
| browser_cookies | WRITE | test_browser_state | pending | pending |
| calendar_read | READ | test_connector_tools | pending | pending |
| cancel_task | WRITE | test_orchestration, test_tools_state | pending | pending |
| code_graph | READ | test_code_graph | pending | pending |
| create_file | WRITE | test_delivery, test_filestore | pending | pending |
| create_task | WRITE | test_orchestration, test_chat_approve_intercept | pending | pending |
| delegate_task | WRITE | test_orchestration, test_chat_approve_intercept | pending | pending |
| design_system | WRITE | test_design_system, test_sync_tools | pending | pending |
| exact_solve | WRITE | test_exact_solve | pending | pending |
| forget | WRITE | test_memory_v2, test_tools_state (+2) | pending | pending |
| generate_variants | READ | test_variants | pending | pending |
| geo_audit | READ | test_geo_audit | pending | pending |
| github_notifications | READ | test_connector_tools | pending | pending |
| gmail_read | READ | test_connector_tools | pending | pending |
| gmail_send | EXTERNAL | test_connector_tools (+2) | approval-gated | pending |
| handoff | WRITE | test_memory_handoff, test_progressive_memory (+1) | pending | pending |
| humanize | READ | test_humanize (+1) | pending | pending |
| library_docs | READ | test_mcp | pending | pending |
| linkedin | WRITE | test_linkedin | pending | pending |
| list_tasks | READ | test_tools_state (+1) | pending | pending |
| memory_get | READ | test_progressive_memory | pending | pending |
| office_doc | WRITE | test_office_doc, test_sync_tools (+1) | pending | pending |
| optimize_prompt | READ | test_prompt_opt | pending | pending |
| playbook | READ | test_playbook (+3) | pending | pending |
| recall | READ | 10 test files | LIVE daily | works |
| remember | WRITE | 6 test files | LIVE daily | works |
| rewrite_natural | READ | test_scrub | pending | pending |
| scrub | WRITE | test_scrub | pending | pending |
| security_audit | READ | test_security_audit | pending | pending |
| seo_audit | READ | test_seo_audit | pending | pending |
| speak | WRITE | test_voice (+1) | pending | pending |
| story_critique | READ | test_storyscope | pending | pending |
| supersede_memory | WRITE | test_memory_v2 | pending | pending |
| switch_model | WRITE | test_multimodel (+2) | LIVE | works |

## Playbooks (12)

interview_coach, debate, writing_tutor, teacher, terse, spec_first, tdd_flow,
verify_done, storyscope, reason_route, seo_web, critic - all unit-covered in
test_playbook.py (+ per-feature suites); E2E pending.

## Method notes

- "LIVE daily" = used in ordinary production traffic continuously.
- E2E pass: exercise each row through a running local app with side-effecting
  backends mocked/stubbed where writes would leave the deployment (gmail_send,
  linkedin, browser_cookies); READ tools get real calls where a connected
  account exists. Mark LIVE only when run against the Render deployment.
- Every broken row gets a fix PR before the matrix closes.
