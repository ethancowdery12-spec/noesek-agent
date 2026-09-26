# noesek for Obsidian - design brief (item 93 candidate)

Ethan, Sep 25 7:57 PM: "for the Claudean, we can make an Obsidian plugin. I think
that'd be also nice." Reference: YishenTu/claudian (MIT) - studied, NOT copied:
different shape (Claudian wraps local coding-agent CLIs; ours talks to the hosted
noesek agent). This is a design for review before any build.

## What it is

An Obsidian community plugin (TypeScript, desktop-only v1) that puts noesek in
the vault: a chat sidebar backed by the user's real noesek agent (memory,
tools, playbooks - the same agent as WhatsApp/Slack, not a local CLI), with
vault files as first-class context and agent-proposed edits applied locally
after user approval.

## Why not Claudian's shape

Claudian is a provider-neutral shell over LOCAL harnesses (Claude Code, Codex,
Grok, OpenCode, Pi) - the agent runs on the user's machine and touches vault
files directly. noesek is a hosted agent the user already talks to from
messaging channels. The Obsidian plugin is therefore a THIN CHANNEL CLIENT,
not an agent runtime: vault context is collected by the plugin and sent with
the message; edits return as proposals the plugin applies after approval.
This matches the channel architecture noesek already has (WhatsApp, Slack,
Telegram adapters into one controller) and keeps vault write access local.

## Server side: a new `obsidian` channel adapter (noesek-agent repo)

Same shape as slack.py/telegram.py:
- `src/noesek/channels/obsidian.py` + `obsidian_router.py`: HTTP endpoints on
  the existing gateway. v1 transport: long-poll or SSE for replies, plain POST
  for sends (WebSocket optional later). Messages route into the same
  Controller, so memory, tools, playbooks, and approvals behave identically
  to other channels.
- Auth: reuse the existing authorization gate (channels/authorization.py) -
  the plugin asks to pair, noesek issues a pairing code the user approves from
  any authorized channel; the plugin stores the resulting token in Obsidian's
  settings (never in the vault, never synced to git).
- Payload: {text, context: [{path, content, selection?}], conversation hints}.
  File contents travel as message context; the server never holds vault write
  access. Context capped (e.g. 50KB total) with a manifest of what was sent.

## Plugin side (new repo noesek-obsidian, MIT)

Obsidian community plugin requirements (own repo, manifest.json, releases,
desktop-only v1). v1 scope, deliberately small:
1. Chat sidebar (ribbon icon + command palette): send/receive, streaming
   rendering if SSE, conversation per-vault.
2. @mention: `@note` attaches the note's content to the message; `@folder/`
   attaches a file list (not contents). Selection in the active editor is
   auto-attached as context when non-empty.
3. Edit proposals: when noesek's reply includes an edit block
   ({path, find, replace} or full-file), the plugin shows a word-level diff
   preview; user accepts or rejects per hunk. Applied edits are normal vault
   writes (undoable, git-visible). Never auto-apply in v1. Server side,
   obsidian conversations carry a channel hint in the assembled system prompt
   (OBSIDIAN_EDIT_HINT in src/noesek/core/context.py) teaching the model the
   fenced noesek-edit contract, so proposals arrive in the format the plugin
   parses.
4. Settings: server URL, pairing flow, context size cap, excluded folders
   (.obsidian, private/).

v2 candidates (not in v1): inline edit hotkey on selection, /side temporary
chat, tabs/sessions, slash commands mapping to noesek playbooks, mobile.

## Trust and safety (matches noesek's existing rules)

- Pairing code approved out-of-band; token revocable from any channel
  (existing gate revoke path).
- Plugin sends only files the user explicitly @mentions or selects, plus
  paths it lists; excluded folders are hard-filtered client-side.
- Edit proposals are proposals: diff preview, per-hunk accept, no auto-apply.
- No vault indexing server-side in v1; no background vault reads.
- Plugin repo carries the MIT notices for anything adapted; Claudian is a
  UX reference only (its code is harness-specific and not reused).

## Build order

1. Server: obsidian channel adapter + pairing endpoints + tests (offline
   channel tests like the other adapters). Small PR.
2. Plugin skeleton: repo, manifest, settings + pairing, sidebar echo against
   staging. Small PR.
3. @mention context + manifest. 4. Edit proposals + diff preview.
Each is its own PR; plugin stays private until community-store submission is
worth it (store review needs a privacy statement - the context rules above
are drafted to satisfy it).
