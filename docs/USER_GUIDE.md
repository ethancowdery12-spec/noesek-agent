# Noesek Agent v3.0.1 — the complete rundown

Everything a user can do with Noesek today, grounded in the shipped v3.0.1
build. One product, one command: `noesek`.

## 1. What Noesek is now

Noesek is a full agentic CLI: an interactive terminal chat with a coding
agent that can run tools, plus a scriptable one-shot mode, a messaging
gateway (WhatsApp first), cron automations, skills, plugins, and a web
dashboard. Under the hood it is a complete fork of an MIT-licensed upstream
agent runtime, vendored byte-identical, with Noesek's own layer on top:
safety core (risk-gated approvals), a durable turn log, deterministic
incident postmortems, local keyword memory, and a thin-controller worker
architecture. Four executables get installed:

- `noesek` — the CLI (interactive UI, one-shot, and every subcommand)
- `noesek-tui` — the modern TUI build directly
- `noesek-agent` — headless agent entry point
- `noesek-acp` — ACP (Agent Client Protocol) server over stdio

## 2. Install and first run

- **Windows:** run the one-liner from the README (PowerShell). It downloads
  the pinned `7-install.ps1`, verifies its SHA-256, then downloads and
  checksum-verifies the release tarball, installs into
  `%LOCALAPPDATA%\Noesek`, and puts `noesek` on PATH.
- **Any platform (Python 3.10+):** download `8-noesek-agent-v3.0.1.tar.gz`
  from the release and `pip install` it.
- First `noesek` launch shows the branded banner (Noesek Agent v3.0.1, ☤
  wordmark, tips) and drops you at the prompt. All state lives in
  `~/.noesek` (Windows: `%USERPROFILE%\.noesek`). Run `noesek setup` once to
  pick a provider and model — until then chat replies will fail with a
  clean "missing key/model" message, and `noesek doctor` tells you exactly
  what is missing.

## 3. The screens

- **Banner / home:** wordmark, version, quick tips (setup, model, help),
  and the input prompt with a status bar (model, context usage bar, turn
  timer).
- **Prompt:** multi-line input (Ctrl+J / Alt+Enter), command palette
  (Ctrl+P), draft editor (Ctrl+G), image paste (Alt+V or /paste).
- **/help:** the 102 in-chat slash commands grouped by area (session,
  approvals, agents, config, display, tools, automations, exit), with
  usage strings; `/help <text>` filters.
- **/model (or `noesek model`):** provider picker screen — arrow-key list
  of providers, then model choice; saves to your config.
- **`noesek setup`:** the setup wizard, seven sections — `model`, `tts`,
  `terminal`, `gateway`, `tools`, `telemetry`, `agent` — each runnable
  individually (`noesek setup gateway`). Flags: `--non-interactive`,
  `--reset`, `--quick`, `--portal`.
- **Status screens:** `noesek status` (all components), `noesek insights`
  (usage analytics), `noesek doctor` (config + dependency checks, JSON),
  `noesek dump` (support bundle summary), `noesek prompt-size` (system
  prompt byte breakdown).
- **Dashboard:** `noesek dashboard` starts the web UI (default
  127.0.0.1:9119; public binds always require auth).

## 4. How a chat actually looks

You type at the `>` prompt; the assistant streams its reply in place.
When the agent wants to run a tool (shell command, file write, web fetch)
you see the tool preview and — for anything risky — an approval gate you
answer inline (`/approve` and `/deny` also exist as commands). The status
bar shows live context-window usage and elapsed turn time. Everything the
agent decides is appended to the durable turn spine
(`~/.noesek/state/turn-spine.jsonl`), so every session is auditable after
the fact. Sessions are resumable: `--resume <id|title|latest>`,
`-c/--continue`, `/sessions` in chat.

Non-interactive use: `noesek -z "prompt"` prints only the final answer
(tools/memory/rules still load; approvals auto-bypassed for pipes), and
`--usage-file PATH` writes a JSON cost report even on failure.

## 5. The core agentic loop (what's different about Noesek)

1. **Thin controller, real workers.** The chat agent plans and delegates;
  background workers (`noesek worker`) do the actual work. A worker cannot
  spawn another worker without a bounded grant — delegation depth is
  capped by design.
2. **Safety core in front of every action.** A deterministic risk
  classifier sits on the tool choke points: hardline-block commands are
  denied even under `--yolo`; approval-class commands always hit the human
  gate; everything else runs. Every decision lands in the turn spine.
3. **Memory that works offline.** Local keyword memory
  (`noesek memories search`, `noesek memory` for external providers) plus
  the `remember` tool for durable user-approved facts.
4. **Incidents and postmortems.** Cron/worker failures are recorded with
  secrets scrubbed, and `noesek incidents list|postmortem` produces a
  deterministic review — no LLM guesswork in the postmortem path.
5. **Full upstream runtime underneath:** tools, gateway platforms, cron,
  skills, plugins, MCP, ACP — the complete feature set, rebranded.

## 6. Every command you can run

`noesek --help` lists 289 command paths with 556 options, generated from a
pinned manifest so every documented spelling parses. The 75 top-level
commands, grouped:

- **Chat & sessions:** `chat`, `resume`, `sessions`, `console`, `send`
- **Setup & config:** `setup`, `model`, `config`, `auth`, `login`,
  `logout`, `portal`, `proxy`, `migrate`, `import-agent`, `claw`
- **Providers & models:** `providers`, `fallback`, `moa`, `secrets`,
  `vault`
- **Tools & extensions:** `tools`, `skills`, `bundles`, `plugins`, `mcp`,
  `hooks`, `lsp`, `browser`, `computer-use`, `webhook`
- **Automations:** `cron`, `curator`, `kanban`, `journey`
- **Gateway & platforms:** `gateway`, `whatsapp`, `whatsapp-cloud`,
  `slack`, `pairing`, `peer`, `monitoring`
- **Safety & ops:** `pause`, `resume`, `approvals`, `egress`, `security`,
  `debug`, `doctor`, `dump`, `logs`, `status`, `insights`, `prompt-size`
- **Servers & apps:** `dashboard`, `serve`, `desktop (gui)`, `acp`,
  `acp-serve`, `worker`
- **Workspaces:** `project`, `profile`, `worktree`, `checkpoints`,
  `backup`, `import`, `verify`
- **Personalization:** `skin`, `pets`, `sync`
- **System:** `completion`, `update`, `uninstall`, `memories`,
  `incidents`, `worker`, `memory`

Key global flags: `-z/--oneshot`, `-m/--model`, `--provider`,
`--reasoning none..ultra`, `-t/--toolsets`, `-r/--resume`, `-c/--continue`,
`--in DIR`, `-w/--worktree`, `-s/--skills`, `--yolo`, `--safe-mode`,
`--ignore-rules`, `--accept-hooks`, `--tui/--cli`, `--usage-file`,
`--compat-report`.

**Honesty note:** some manifest commands are parsed exactly but not yet
wired to an adapter; they exit 3 with "no safe execution adapter yet"
instead of doing something surprising. The full list is in
`docs/CLI_SURFACE.md`. All the commands in the acceptance sweep (doctor,
config, status, insights, tools, skills, providers, vault, cron, worktree,
incidents, memories, completion, update, uninstall, chat) execute for
real.

## 7. In-chat slash commands (102)

Session control: `/new` `/topic` `/clear` `/history` `/save` `/retry`
`/undo` `/title` `/handoff` `/branch` `/compress` `/rollback` `/snapshot`
`/export` `/import` `/stop` `/pause` `/resume` `/sessions` `/quit`
Approvals & safety: `/approve` `/deny` `/approvals` `/yolo` `/egress`
Agents & delegation: `/agents` `/bg` `/queue` `/steer` `/goal` `/subgoal`
`/plan` `/loop` `/moa` `/review` `/refine` `/heartbeat`
Config & model: `/config` `/model` `/reasoning` `/fast` `/codex-runtime`
`/login` `/subscription` `/usage` `/topup`
Display & input: `/skin` `/personality` `/statusbar` `/timestamps`
`/verbose` `/focus` `/footer` `/indicator` `/voice` `/busy` `/redraw`
`/palette` `/copy` `/paste` `/image` `/battery` `/diff` `/context`
Tools & skills: `/tools` `/toolsets` `/skills` `/bundles` `/memory`
`/pet` `/hatch` `/learn` `/init` `/plugins` `/browser` `/commands`
Automations: `/cron` `/suggestions` `/blueprint` `/curator` `/kanban`
Platform & system: `/platforms` `/platform` `/status` `/whoami`
`/profile` `/sethome` `/wake` `/insights` `/update` `/version` `/debug`
`/help` `/journey` `/btw` `/worktree` `/prompt` `/restart`

## 8. Settings you can tweak

- `noesek config` shows current settings as JSON; the wizard and
  `config.yaml` in `~/.noesek` are the persistent stores. Highlights:
  `llm_api_key`, `llm_base_url`, `llm_fallbacks`, `llm_max_concurrent`,
  `approval_ttl_hours` (24h default), `history_limit`, `gateway_allow_all_users`,
  `fetch_max_bytes`, `fetch_timeout_seconds`, `database_url`,
  `brave_search_api_key`.
- Per-run overrides via flags (`-m`, `--provider`, `--reasoning`,
  `-t`) and env vars (`NOESEK_INFERENCE_MODEL`, `NOESEK_HOME`,
  `NOESEK_ACCEPT_HOOKS`, `NOESEK_DATABASE_URL`). Functional upstream env
  vars (e.g. `HERMES_*`) still work — that is deliberate, they are
  plumbing, not branding.
- Skins: `noesek skin` lists/switches/tweaks; the managed `noesek` skin is
  the default.
- Reasoning effort: `none, minimal, low, medium, high, xhigh, max, ultra`
  — persistent in config (`agent.reasoning_effort`, per-model overrides)
  or per-run with `--reasoning`.
- Toolsets: enable subsets of tools per run (`-t`) or per platform
  (`noesek tools`).

## 9. Safety model in one paragraph

Approvals are the default for risky actions; `--yolo` bypasses prompts but
can never override hardline blocks; `--safe-mode` strips all
customizations (user config, AGENTS.md/memory injection, plugins, MCP) for
troubleshooting; `noesek pause` is an emergency stop for cron/kanban
dispatch and new gateway turns (`noesek resume` lifts it); the egress
firewall (`noesek egress`) controls credential injection; `noesek
security` runs an OSV.dev supply-chain audit of the venv, plugins, and MCP
servers.

## 10. Where things live

`~/.noesek` — config.yaml, sessions, messages, cron, gateway state, logs,
skins, skills, checkpoints, vault, and `state/turn-spine.jsonl`. Two
databases by design: the vendored runtime store (sessions/messages/
timelines) and the Noesek DB (controller conversations, jobs, approvals) —
SQLite by default, Postgres via `NOESEK_DATABASE_URL`.

## 11. Known gaps (as of v3.0.1)

- Unadapted manifest commands exit 3 (documented in docs/CLI_SURFACE.md).
- `noesek-tui` modern UI needs a dist build (`--dev` runs TypeScript
  sources via tsx).
- Native desktop app (`noesek desktop`) and dashboard were not part of the
  sandbox acceptance pass (Windows path is covered by CI).
- Live LLM conversations, OAuth/portal flows, and WhatsApp live traffic
  need real credentials — verified as far as possible without them.
