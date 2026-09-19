# Noesek v2.1.0 - Hermes-look CLI

## What shipped

**Interactive UI (PR #15).** Bare `hermes`, `hermes chat`, and `noesek chat`
now open a real Hermes-look terminal UI built from the upstream implementation
(NousResearch/hermes-agent @ d7b836ab, MIT): welcome banner with the caduceus
and logo art, tools grouped by toolset, skills by category; live status bar
(model, ~tokens/max, [####......] context bar with green/yellow/orange/red
thresholds, cost, duration, YOLO badge, session title, width-adaptive);
slash-command autocomplete over the full 102-command registry; `!` shell mode
(zero model turns, dangerous patterns refused); markdown stripping on final
replies; multiline input (Alt+Enter / Ctrl+J); Ctrl+C interrupt, Ctrl+D exit;
persistent history. prompt_toolkit 3.0.52 added (upstream's own toolkit);
graceful plain-loop fallback without it.

**CLI surface refresh (PR #14).** Command manifest regenerated from upstream
main: 289 command paths / 547 options / 102 slash commands, all parseable.
New groups: kanban, pets, journey, insights, logs, skin, console, dashboard,
desktop, pause/resume, peer, dump, sync, verify, worktree, monitoring, security
audit, claw, import-agent, moa, lsp. Extractor fixes removed double-nesting
artifacts (send send, kanban kanban).

**Sessions analysis + admin (PR #16).** sessions rename/prune/stats (stored
titles, safe prune keeping 5 newest, --yes to execute); per-session analysis
(turns, tools, real input/output tokens, policy blocks, active span) via
`/sessions <id>`; `hermes insights` (turns/day, tool frequency, token totals);
`hermes dump` (redacted support summary); `hermes logs` (confined tailing);
`hermes pause`/`resume` (global emergency stop honored by the task worker);
`hermes worktree list/prune` (conservative: only clean, fully-merged trees,
--yes required); `hermes console` (REPL over the full surface).

## Deferred (explicit)

Skins/pets/voice/ghost-text, the full-screen TUI and Electron desktop app, and
adapters needing live third-party services (provider login/billing, messaging
sends, remote skill/plugin catalogs, Hermes kanban/projects backends) remain
out. Commands without safe Noesek execution still exit 3 and say so.
Token/cost figures in the UI are local estimates (`~`) until provider usage
reporting is wired; cost shows `n/a`.

## Verification

- Suite: 605 passed, 44 skipped, 0 failed (31 new tests across the 3 PRs).
- Injection suite 4/4; Hermes adapter evals pass on every PR via eval-gate.
- Windows installer verified on windows-latest against this release
  (see the release assets and Actions run linked in release notes).
