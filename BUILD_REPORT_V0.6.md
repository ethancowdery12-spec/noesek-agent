# Noesek Agent v0.6 Stage 2B build report

Baseline remains `NousResearch/hermes-agent@228022ef5b209cb0a3d739394edddf887e1db0f6`, MIT. No Hermes source, prompts, assets, tests, dependencies or credentials were copied.

Stage 2B adds an injected-client Bedrock Converse adapter so AWS credential resolution stays outside Noesek; normalized token usage across OpenAI, Anthropic, Gemini and Bedrock; strict size-capped SSE event parsing; and shell-free MCP stdio framing with executable allowlists, clean environment, frame caps, timeouts and response validation. It also includes deterministic context compaction and literal conversation-scoped session search as adjacent session foundations.

Verification: CPython 3.12.13; 96 tests passed in 3.78s; 2 existing non-failing FastAPI/Starlette deprecation warnings. Compile/package/clean-wheel checks recorded below.

No live provider, OAuth, AWS or MCP service was contacted. OAuth/device flows remain blocked on vault-backed credential storage rather than accepting secrets in chat. End-to-end streaming, MCP SSE and ACP remain. This is progress, not parity.

Packaging: compileall passed; sdist and wheel built; clean-wheel version/import/Bedrock/MCP-stdio/compaction smoke passed.
