# Build report: v2.0.0

v2.0.0 is the harness deep-dive synthesis release: eight upgrade stages (A-H)
built from 125 harness deep-dives, merged as PRs #2-#10 on top of the imported
v1.11.3 source tree (PR #1).

- **A - Durable turn spine** (PR #2): typed, ordered `turn_events` per turn;
  write-ahead logging flushes strictly before side effects (fail closed);
  OTel GenAI token-usage attributes on model events; deterministic postmortem
  replay (`get_turn_events` / `render_turn`).
- **B - Policy engine + approval leases** (PR #3): ordered allow/ask/deny
  rules (`NOESEK_POLICY_RULES`); the hardline content gate is always rule 0;
  approvals are single-use leases bound to conversation + tool + canonical
  arguments + turn, tamper-blocked, TTL'd.
- **C - Loop guardrails** (PR #4): identical-retry warn-then-stop, doom-loop
  cycle detection, no-progress error-streak stops with stable error classes.
- **D - Memory v2** (PR #5): typed memories (note/fact/preference/episode)
  with provenance, supersede-not-overwrite, SQLite FTS5 search (no new
  dependencies), persisted compaction transitions, untrusted-content wrapping
  for tool results.
- **E - Real coder worker** (PRs #6, #7): aider-style SEARCH/REPLACE edit
  protocol with per-hunk salvage, deterministic repo map, structured submit
  checklist, sandboxed `run_command` verification (read-only workspace mount,
  network disabled).
- **F - Tool scaling** (PR #8): deferred schema exposure with `search_tools`
  activation; MCP tools adapted into policy-gated ToolSpecs.
- **G - Eval upgrade** (PR #9): trajectory assertions over the turn spine,
  AgentDojo-style injection suite (4 scenarios, all defended), CI eval gate
  on every PR and push.
- **H - Live steering + session fork** (PR #10): mid-turn steering notes
  consumed between tool steps; conversation fork copies messages + active
  memories with provenance.

Tests: 574 passed, 44 skipped, 0 failed (v1.11.3 baseline: 515 passed, 1
failing browser test, since fixed). Injection suite: 4/4 scenarios defended.

License posture: only patterns re-implemented from MIT/Apache-2.0/BSD
codebases; every new design doc carries provenance; no copyleft or
source-available code copied.
