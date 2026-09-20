# The Noesek Computer - agent-first architecture plan (v4 line)

Ethan's direction (2026-09-20): Noesek becomes a "computer" - an agent that
lives on its own Linux machine and is talked to the way you talk to a real
coworker: WhatsApp, messages, Teams, Zoom-era channels. No CLI UI, no
human-facing screens. Chats ARE sessions. Connectors (OAuth, set up by
Ethan) let it act on his accounts. It can screenshot, browse, and drive its
own desktop. This plan is the architecture for that, and what we keep,
strip, and add from the v3.0.1 fork.

## 1. Product shape

- One long-running agent per machine ("the Noesek computer").
- Interfaces are messaging channels only. First: WhatsApp (Cloud API, in
  tree today), then the other vendored gateway platforms (Telegram, Slack,
  Discord), then Ethan's own Noesek mobile app as a first-class channel.
- A chat == a session. New DM/group/thread on any channel maps to a
  durable session id; per-channel identity + chat id is the session key.
- The agent answers, acts, uses tools, asks for approvals in-chat, sends
  files/images/voice back. All output is channel messages.
- Connectors are OAuth-backed tool packs (Gmail, Calendar, GitHub, Slack,
  ...). Ethan completes each provider's OAuth consent once; tokens live in
  the encrypted vault; connector tools register into the agent deferred
  (ToolSearch-style) so 200 connector tools never blow up the prompt.
- The machine itself is a tool: screenshot, browse (Playwright/Chromium),
  click/type, read files, run shell - full computer use inside the VM,
  gated by the same safety core as everything else.

## 2. Keep / strip / add from the v3 fork

KEEP (the reason we forked):
- Vendored MIT runtime as LIBRARIES: agent loop, tool registry, gateway
  platform implementations, cron, skills, plugins, MCP client/server,
  sessions store, memory. Byte-identical vendoring rule unchanged.
- Noesek core: safety/approval engine, durable turn spine, incidents +
  deterministic postmortems, local keyword memory, thin-controller +
  workers + SpawnGrant-style delegation, worktree isolation.
- The command surface - but as AGENT-CALLABLE tools, not human CLI verbs.
  289 commands become the agent's capability catalog; each command path is
  a tool the agent can invoke (with the risk classifier in front).
- Sessions and everything durable.

STRIP (out of the runtime path; kept in git history):
- Interactive REPL/screens (prompt_toolkit UI, banners, pickers, wizards)
- noesek-tui, desktop app, dashboard web UI
- Slash-command UX layer (the 102 slash commands as typed text). Their
  ACTIONS survive as agent tools; the text UI goes.
- Setup wizard screens -> replaced by agent-led setup over chat ("say
  'setup'" and the agent walks you through it in messages) plus env/config
  files on the VM.
- Skins/pets visual layer. Ethan's call on a mascot moment in chat later.

ADD (new Noesek-layer modules):
- `channels/`: channel adapters behind one interface:
  inbound message -> session resolution -> agent turn; agent events ->
  channel-formatted replies (text chunks, image, document, voice). WhatsApp
  Cloud first (vendored implementation reused), session map persisted.
- `server/`: the agent runtime as a service - one controller process,
  workers, event bus; no UI consumers required. Loop emits typed events;
  channels are just consumers (pattern proven by OpenClaude's loop).
- `approvals/chat.py`: per-surface permission handler - approval gates
  arrive as chat messages ("Run `git push`? yes/no/always"), answers bind
  to the single-use lease model we already have.
- `connectors/`: connector framework. A connector = manifest (provider,
  scopes, tool definitions) + OAuth token in vault + tool implementations
  (thin HTTP clients). Deferred tool loading + search (pattern L from the
  OpenClaude read). Ethan does the OAuth consent in browser; the VM holds
  no client secrets beyond what he deposits in the vault.
- `computer/`: the computer-use layer for Linux: screenshots (Xvfb +
  scrot/mss), input (xdotool), browser automation (Playwright, already a
  dependency), and the vendored cua-driver where it fits. Every computer
  action flows through the safety core; screenshots can be sent back to
  the chat on request.
- `proactive/`: the idle engine (activate/pause/tick) so the computer can
  act first - cron + wake patterns we already have, unified.

## 3. The loop, agent-first (from the deep OpenClaude read)

Patterns folded in (ideas only - their license is radioactive):
1. Loop emits typed events; channels consume. No UI imports in the loop.
2. Context pipeline as a stage: snip -> microcompact -> autocompact, with
   a failure guard and one-shot overflow recovery.
3. Withhold transient provider errors from the channel until recovery
   gives up - a WhatsApp session should not die on a retryable hiccup.
4. Tool contract: isDestructive, interruptBehavior, maxResultSizeChars
   (disk spill), deferred loading + search.
5. Permission handler per surface: chat-yes/no on messaging channels,
   policy-only for workers.
6. maxSteps forced structured summaries on workers (= SpawnGrant).
7. Goal evaluator on the main thread only; subagent turns never evaluate.
8. Memory entrypoint caps (lines AND bytes) + what-not-to-save prompting.
9. Loop guards keyed by agentId - workers never wipe the controller's
   doom-loop/failure counters.
10. Don't trust stop_reason; count tool_use blocks.

## 4. VM topology (Phase 2 deliverable)

Target: Ethan double-clicks nothing more than once. Lightest reliable path
on Windows 11:

- **WSL2** (built into Windows, free, `wsl --install` is one command) with
  Ubuntu 24.04. No Docker Desktop license/install burden, systemd works,
  survives reboots, and the same image runs later on a cloud Linux VM
  unchanged.
- Inside WSL2: Python 3.12 venv + noesek-agent wheel, Xvfb virtual display,
  Chromium via Playwright, scrot/xdotool for computer use, a systemd user
  service (`noesek-computer.service`) that starts the agent runtime and the
  WhatsApp channel, and a tiny status file the Windows side can read.
- Packaging: `install.ps1` v4 - one PowerShell one-liner from Windows:
  enables WSL2 if needed, installs Ubuntu, copies in our `setup.sh`, runs
  it, drops the DeepSeek key into the VM's config (from the vault, never
  chat), starts the service, prints "say hi on WhatsApp".
- Docker alternative kept as a Dockerfile for cloud deploys later; not the
  primary ask because Docker Desktop is a heavier, licensed install.

## 5. v4 sequencing

- v4.0.0 (this phase): repo gains `server/` + `channels/whatsapp` +
  `approvals/chat` + `computer/` (screenshot + browser) behind a
  `noesek-computer` entry point; CLI stays shipped as the operator console.
  VM one-liner + E2E chat proof with DeepSeek.
- v4.1: connectors framework + first connectors (Ethan's OAuth).
- v4.2: proactive engine, voice notes, his mobile app as a channel.
- v4.3: cloud VM image (same setup.sh, cloud-init).

## 6. What this does to v3.0.1

Nothing breaks: v3.0.1 stays the released CLI. v4 work lands on `v4/*`
branches, squashed into main behind the same eval gate; the CLI keeps
building because stripped UI is removed only from the new server's runtime
path first, and deleted from the tree only when v4.0.0 ships.
