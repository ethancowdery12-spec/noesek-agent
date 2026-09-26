# Third-party notices

No third-party source code was copied into this repository. It depends on these separately distributed packages under permissive licenses; their own distributions carry authoritative license texts and notices:

- FastAPI - MIT - https://github.com/fastapi/fastapi
- Uvicorn - BSD-3-Clause - https://github.com/encode/uvicorn
- HTTPX - BSD-3-Clause - https://github.com/encode/httpx
- Pydantic and pydantic-settings - MIT - https://github.com/pydantic/pydantic and https://github.com/pydantic/pydantic-settings
- SQLAlchemy - MIT - https://github.com/sqlalchemy/sqlalchemy
- aiosqlite - MIT - https://github.com/omnilib/aiosqlite
- asyncpg (optional) - Apache-2.0 - https://github.com/MagicStack/asyncpg
- ofxparse (optional, [finance] extra) - MIT, (c) 2009 Jerry Seutter - https://github.com/jseutter/ofxparse (runtime: ofx_import tool)
- fitparse (optional, [fitness] extra) - MIT, (c) 2011-2020 David Cooper, (c) 2017-2020 Carey Metcalfe - https://github.com/dtcooper/python-fitparse (runtime: fit_import tool)
- pytest - MIT - https://github.com/pytest-dev/pytest (runtime: test_verifier tool)
- coverage - Apache-2.0 - https://github.com/coveragepy/coveragepy (runtime: test_verifier tool)
- pytest-asyncio (development) - Apache-2.0 - https://github.com/pytest-dev/pytest-asyncio
- pytesseract (optional, [ocr] extra) - Apache-2.0, (c) Samuel Hoffstaetter and contributors - https://github.com/madmaze/pytesseract (runtime: receipt_import tool; drives the tesseract OCR engine, Apache-2.0, installed as an image binary, never vendored)

Container images are separate works with their own package/license inventories. Review and pin approved digests before production use.

Public protocol documentation used to implement the adapters:
- WhatsApp Cloud API webhooks: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
- WhatsApp Cloud API messages: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages
- Brave Search API: https://api-dashboard.search.brave.com/app/documentation/web-search/get-started
- OpenAI-compatible chat/tool schema: https://platform.openai.com/docs/guides/function-calling

“Noesek Agent” architecture and code in this repository are original for this deliverable. No closed-source code, private prompts, or leaked prompt text is included.

## Hermes Agent (vendored source)

Noesek v1.1 vendors selected Hermes Agent subsystems (approval stack, cron
persistence core, utility modules) under the MIT License, (c) 2025 Nous
Research. See VENDORING.md for the pinned commit, per-file manifest, and the
list of Noesek-authored bridge modules; the license text ships at
src/noesek/vendor/hermes/LICENSE.hermes. Noesek's approval persistence,
risk classes, and policy gates wrap the vendored code; adopted modules run
inside Noesek's gates, not beside them.

Earlier versions' operational CLI was independently implemented after studying
Hermes Agent's public command documentation.

## Additional dependencies (v1.1)

- PyYAML - MIT - https://github.com/yaml/pyyaml
- opentelemetry-sdk - Apache-2.0 - https://github.com/open-telemetry/opentelemetry-python
- MCP Python SDK (mcp) - MIT - https://github.com/modelcontextprotocol/python-sdk
- croniter - MIT - https://github.com/pallets-eco/croniter
- duckdb - MIT - https://github.com/duckdb/duckdb (SQL-over-files chat tool; pinned 1.4.3)
- detect-secrets - Apache-2.0 - https://github.com/Yelp/detect-secrets (secret-scan gate scripts/secret_scan.py; pinned 1.5.0, test extra)

Hermes Agent, Copyright (c) 2025 Nous Research, is licensed under the MIT
License. Canonical source and license audited at commit
`228022ef5b209cb0a3d739394edddf887e1db0f6`:
https://github.com/NousResearch/hermes-agent

The full Hermes MIT license is reproduced in `docs/licenses/HERMES-AGENT-MIT.txt`.

## agent-client-protocol (ACP SDK)
Pinned: agent-client-protocol==0.12.1 (MIT License).
Used by `noesek.compat.acp_real` for the ACP server shim. No code vendored;
consumed as a pinned dependency. License:
https://github.com/agentclientprotocol/agent-client-protocol/blob/main/LICENSE

## Playwright (browser backend)
Pinned: playwright==1.56.0 (Apache-2.0). Used by `noesek.core.browser_backend`
to execute approval-bound computer-use plans in headless Chromium. No code
vendored; consumed as a pinned dependency. License:
https://github.com/microsoft/playwright-python/blob/main/LICENSE

## docker-py (sandbox backend)
Pinned: docker==7.1.0 (Apache-2.0). Optional sandbox backend
(`noesek.tools.sandbox_backends.DockerPyBackend`). License:
https://github.com/docker/docker-py/blob/main/LICENSE

## E2B (sandbox backend)
Pinned: e2b==2.9.0 (Apache-2.0). Optional remote-microVM sandbox backend
(`noesek.tools.sandbox_backends.E2BBackend`); selected only explicitly and uses
the operator's own E2B_API_KEY from the environment. License:
https://github.com/e2b-dev/E2B/blob/main/LICENSE

## promptfoo (eval runner)
Consumed as a subprocess via npx/global install (MIT); Noesek generates configs
and parses results in `noesek.tools.evals`. Not a Python dependency. License:
https://github.com/promptfoo/promptfoo/blob/main/LICENSE

## slack-sdk (Slack channel transport)
Pinned: slack-sdk==3.39.0 (MIT). Used by `noesek.channels.slack_sdk` for request
signature verification and Web API sends. License:
https://github.com/slackapi/python-slack-sdk/blob/main/LICENSE

## aiogram (Telegram channel sidecar, NOT a core dependency)
aiogram (MIT) caps pydantic below the project's exact 2.13.5 pin, so the
Telegram bot process runs as a sidecar with its own environment
(`sidecars/telegram_bot.py`), not as a Noesek dependency. The in-process
transport `noesek.channels.telegram_sdk` lazily imports aiogram only when a
token is configured. License: https://github.com/aiogram/aiogram/blob/dev-3.x/LICENSE

## deepeval (evaluation, process-isolated)
NOT a dependency: consumed only as an external runner against Noesek-generated
test-case JSON (`noesek.tools.evals.build_deepeval_cases`). License: Apache-2.0,
https://github.com/confident-ai/deepeval/blob/main/LICENSE.md

## browser-use (deferred)
Not integrated in v1.6.0: browser-use==0.9.5 (MIT) would force a downgrade of
the pinned websockets (17.1 -> 16.1.1), violating the exact-pin policy.
Deferred until a compatible release; recorded in BUILD_REPORT_V1.6.md.

## Hermes Agent CLI grammar

- Project: Hermes Agent
- Canonical source: https://github.com/NousResearch/hermes-agent
- Pinned commit: c712f06dcdd24053a4118f38d2090ac53137ecfc
- License: MIT
- Copyright (c) 2025 Nous Research

Noesek's generated CLI manifest records SHA-256 provenance for every inspected
upstream parser file. Noesek does not vendor or invoke Hermes' agent core.

## anthropics/knowledge-work-plugins (Apache-2.0)

Curated whole-category business workflow skills (customer-support, operations,
marketing) imported as the seeded skill backbone (item 86), converted by
scripts/build_kwp_seed.py into src/noesek/data/kwp_skills.py with per-skill
provenance headers. Copyright Anthropic PBC. License:
https://github.com/anthropics/knowledge-work-plugins/blob/main/LICENSE

## tree-sitter + grammar packages (MIT, item 89)

Optional [codeintel] extra: tree-sitter 0.25.2 (MIT, (c) 2018-2024 Max Brunsfeld
and contributors) and grammar packages tree-sitter-python, -javascript,
-typescript, -go, -rust, -java, -c, -cpp, -ruby, -c-sharp, -php, -bash, -json
(all MIT). Licenses verified against the on-disk LICENSE file shipped in each
wheel, Sep 24 2026. Used by core/code_intel.py for AST symbol/call indexing.

## iCodeCraft/anti-slop (MIT)

The diff-discipline section of the code_review checklist (scope creep, new
files that belong in existing modules, unrequested dependencies, drive-by
refactors, restating comments, single-use abstraction and invented layered
folder trees) is adapted own-words from the rule set published by the
kill-slop skill - no upstream skill files are copied or loaded. License
verified against the on-disk LICENSE, Sep 26 2026. Copyright iCodeCraft.
https://github.com/iCodeCraft/anti-slop/blob/main/LICENSE

## alibaba/open-code-review (Apache-2.0)

The code_review chat tool's pipeline architecture (group changed files, plan
risk points, review each group with a bounded context-tool loop, then a
fact-check filter that drops only comments the diff proves wrong) is adapted
from Open Code Review and re-implemented in Python in src/noesek/review/ -
no upstream Go code is copied or invoked. License verified against the
on-disk LICENSE, Sep 25 2026. Copyright Alibaba Group.
https://github.com/alibaba/open-code-review/blob/main/LICENSE

## wshobson/agents (MIT)

The AI-generation-debt section of the code_review checklist (failure modes,
orphaned resources, hallucinated dependencies, architectural drift - adapted
own-words from the ai-debt-detector skill) and the session-guard playbook
patterns (long-session health zones, rule recitation, compaction anchoring)
come from the wshobson/agents plugin marketplace, MIT license verified
on-disk Sep 25 2026. Copyright Seth Hobson.
https://github.com/wshobson/agents/blob/main/LICENSE

## G10DC/chisel (MIT)

The duplicate-tool-call suppression in the conversation condenser
(src/noesek/core/condenser.py, dedupe_repeated_tool_calls - repeated
identical calls masked, latest result verbatim, code/regex/literals never
re-compressed) is an own-words implementation of the chisel duplicate
detection idea; no upstream code is copied. MIT license verified against
the on-disk LICENSE, Sep 26 2026. Copyright Chisel contributors.
https://github.com/G10DC/chisel/blob/main/LICENSE
## Hermes Agent Bot Desktop (adapted implementation, computer screen)

The noesek computer screen (src/noesek/computer/screen_lease.py,
rfb_filter.py, screen_bridge.py; screen_runtime.py design) is adapted from
Nous Research hermes-agent's Bot Desktop subsystem (tools/bot_desktop/,
hermes_cli/web_routers/display.py, website/docs/user-guide/features/bot-screen.md)
under the MIT License, (c) 2025-2026 Nous Research -
https://github.com/NousResearch/hermes-agent. The RFB client-message frame
table and the takeover-lease semantics are carried over from upstream; the
state layout, token gate and single-profile lifecycle are noesek-authored.
Adapted files carry provenance headers; the upstream license text ships at
src/noesek/vendor/hermes/LICENSE.hermes.
