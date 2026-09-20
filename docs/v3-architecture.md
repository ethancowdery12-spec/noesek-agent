# Noesek v3 architecture: full fork + Noesek core

Since v3.0.0, Noesek is a full fork of upstream NousResearch/hermes-agent
(MIT, (c) 2025 Nous Research), vendored complete and byte-identical at
`vendor/hermes-agent/` (pinned commit d7b836ab, per-file SHA-256 manifest at
`vendor/VENDOR_PROVENANCE.sha256`). Everything user-visible reads noesek;
Python identifiers inside the vendored tree keep upstream names so upstream
diff/sync and the provenance manifest stay valid.

## Layers

1. **Vendored upstream runtime** (the base): the complete CLI
   (`hermes_cli`), agent loop (`agent`), tools, gateway (Telegram, Slack,
   Discord, WhatsApp Cloud, and the other upstream platforms), cron,
   plugins, skills, TUI gateway, ACP adapter. Installed as importable
   top-level packages by the noesek wheel, mirroring upstream's packaging.

2. **Noesek boot shim** (`src/noesek/upstream_boot.py`): `noesek` with no
   arguments boots the vendored CLI. Maps `HERMES_HOME` to `NOESEK_HOME`
   (default `~/.noesek`) so ALL vendored state - sessions, messages, cron,
   gateway state, logs, skins - lives under the Noesek home (regression-
   tested; `~/.hermes` is never created). Installs and activates the
   managed `noesek` skin (wordmark/branding) and wraps the top-level parser
   so help/usage/errors read `noesek`.

3. **Noesek safety core** (`src/noesek/core/`): our differentiating layer,
   wired in at runtime (no vendored edits):
   - `approval_engine.py` - deterministic risk classification backed by the
     upstream detection tables (hardline block / approval / allow).
   - `upstream_safety.py` - wraps the vendored approval choke points so our
     risk gate consults first: hardline blocks deny even under `--yolo`,
     approval-class commands force the human gate, and every decision is
     appended to the durable turn spine at `~/.noesek/state/turn-spine.jsonl`.
   - `redact.py` - conservative secret scrubber applied before errors are
     persisted by the cron incident ledger.
   - Thin-controller architecture: chat agent delegates only; workers do
     real work; workers cannot spawn workers without a bounded SpawnGrant.

4. **Noesek services** (`src/noesek/`): controller, jobs/workers, channels,
   local keyword memory, ACP server, and the Noesek interactive UI
   (`noesek chat` / `noesek-tui`).

## State coexistence

Two stores, deliberately separate:

- **Vendored `hermes_state`** (SQLite, WAL) under `~/.noesek`: everything
  the vendored CLI/gateway/cron persists - sessions, messages, timelines,
  pairing, cron jobs.
- **Noesek DB** (`src/noesek/db.py`, SQLite default / Postgres optional via
  `NOESEK_DATABASE_URL`): controller conversations, jobs, approvals, and
  the v2 service layer.

They do not share tables; the Noesek home is the single root for both.

## Channel strategy

WhatsApp-first. The vendored gateway provides WhatsApp Cloud
(`gateway/platforms/whatsapp_cloud.py`) plus the other upstream platforms;
Noesek's own channel layer (`src/noesek/channels/`) carries our pairing and
authorization policy, built on the vendored gateway mixins.
