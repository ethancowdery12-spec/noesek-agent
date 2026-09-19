# Tool scaling (v2, stage F)

## Deferred schema exposure (search-then-activate)

When a registry holds more than `NOESEK_TOOL_DEFER_THRESHOLD` tools (default
0 = disabled), every non-core tool is DEFERRED: it stays registered and
searchable, but its schema stays out of the prompt. A `search_tools`
meta-tool (read-only, on the controller surface) takes a keyword query,
activates the matches, and their full schemas appear from the next step.
Core tools (`remember`, `recall`, `delegate_task`, `search_tools`) are
always visible. Registries are built per turn, so deferral state resets
cleanly each turn.

## MCP through the policy engine

`compat.mcp_real.mcp_tool_spec` adapts an allowlisted MCP tool into a normal
`ToolSpec` (named `mcp_<tool>`). Default risk is EXTERNAL, so calls pause
for a stage-B approval lease exactly like any other external tool; the MCP
server allowlist (compat.mcp policy) still applies underneath. Operators
relax specific MCP tools with `NOESEK_POLICY_RULES`.

## Provenance

Search-then-activate and deferred schemas re-implement patterns studied in
the MIT-licensed harness deep-dives (opencode, Claude Code-style tool
search; Composio tool discovery). No code copied.
