# Noesek Agent v0.5 Stage 2A build report

Baseline remains `NousResearch/hermes-agent@228022ef5b209cb0a3d739394edddf887e1db0f6`, MIT. This clean-room stage adds native Anthropic Messages and Gemini generateContent wire adapters, normalized text/tool-call results, configured provider selection, bounded failover that does not rotate past ordinary 4xx/auth failures, and an HTTP MCP JSON-RPC client with ID/error validation and tool allowlist checks before network calls. No Hermes code, prompts, assets, tests, dependencies or credentials were copied.

Verification: CPython 3.12.13; 89 tests passing; compileall, sdist/wheel and clean-wheel smoke to be recorded after packaging. No live provider or MCP call was made. Two existing non-failing FastAPI/Starlette test-client deprecation warnings remain.

This is Stage 2A, not parity. OAuth/device login needs a vault-backed design and was not faked or made to accept secrets in chat. Bedrock, streaming, usage accounting, stdio/SSE MCP and ACP remain, along with later matrix gaps.

Packaging: compileall passed; sdist and wheel built; clean-wheel import/version/native-adapter/MCP smoke passed.
