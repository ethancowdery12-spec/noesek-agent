# Noesek Agent v0.7 Stage 3A build report

Baseline remains `NousResearch/hermes-agent@228022ef5b209cb0a3d739394edddf887e1db0f6`, MIT. No Hermes source, prompts, assets, tests, dependencies, private prompts or credentials were copied.

Stage 3A adds an injected secret-store protocol; OAuth device-flow polling with pending, slow-down, expiry and error handling; redacted connection status that never returns token values; normalized OpenAI, Anthropic and Gemini stream events; bounded MCP SSE JSON-RPC decoding; and a bounded ACP JSON-lines codec with explicit method allowlists. These are protocol foundations, not claims that a live account is connected.

Verification: CPython 3.12.13; 100 tests passed in 3.59s; 2 existing non-failing FastAPI/Starlette warnings. Compile, package and clean-wheel checks are recorded below.

No live OAuth, provider, MCP or ACP service was contacted. Concrete vault/browser/device connectors, full duplex provider streaming, complete ACP sessions/server behavior, container terminal, and later matrix gaps remain. This is progress, not parity.

Packaging: compileall passed; sdist and wheel built; clean-wheel version/import/auth/MCP-SSE/ACP smoke passed.
