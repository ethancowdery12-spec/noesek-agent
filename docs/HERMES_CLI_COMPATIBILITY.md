# Hermes CLI compatibility

Noesek 1.11 provides a `hermes` entry point generated from canonical Hermes
Agent commit `c712f06dcdd24053a4118f38d2090ac53137ecfc` (MIT). The machine-readable
source of truth is `compat/hermes-cli-manifest.json`; it includes per-file
SHA-256 hashes, command paths, options, aliases, help metadata, and the slash
command registry.

The parser accepts the complete statically recoverable public surface. Commands
backed by coherent Noesek services execute through adapters: chat/one-shot,
status, doctor, prompt-size, config show/path, sessions list, local backup, ACP,
gateway foreground run, pairing list, cron incident inspection, and completion.
They use Noesek's thin controller, scoped workers, approval gate, state, and
sandbox boundaries.

A parsed command without a safe adapter exits 3 and says it did not run. This is
intentional and testable, not claimed behavioral parity. Major gaps are Hermes
self-update/uninstall, desktop/dashboard/pet UI, provider billing/portal login,
unrestricted host shell console, Hermes kanban/projects, Hermes credential pool,
and Hermes-specific session/checkpoint formats. Matching those would either
replace Noesek's controller, weaken its security model, require unavailable
Hermes product services, or silently mutate external state.

`hermes --noesek-compat-report` prints the pinned source and inventory counts.
Regenerate with `HERMES_SOURCE=/path/to/pinned/hermes-agent python tools/inventory_hermes_cli.py`.

## Behavioral adapter coverage added after initial v1.11 packaging

Coherent local groups now implemented beyond the initial set:

- Cron: list, create, pause, resume, trigger, remove, runs, incidents,
  notepad, and resnapshot use the vendored MIT Hermes cron store adapted under
  `NOESEK_HOME`. They do not start an external gateway or provider.
- Sessions: list, JSON export, and explicit delete use Noesek durable state.
- Skills: local installed-skill listing scans inert `SKILL.md` files only.
- Plugins: local list/show/capabilities reads manifests without importing code.
- Tools: list shows Noesek's typed tool registry.
- Fallback: list reports available/configured providers with API keys removed.
- Config get reads the effective redacted Noesek settings.

Mutation-heavy groups remain explicit exit 3 where the safe behavior is not yet
implemented: remote skill/plugin install/publish/update, profile archive and
identity migration, MCP configuration/auth mutations, browser driver install,
provider login/billing, gateway service installation, hooks, secrets/vault,
self-update/uninstall, peer/webhook sends, desktop/dashboard, kanban/projects,
and Hermes-native checkpoint/session repair. Many need download trust policy,
operator process ownership, external services, or formats Noesek does not own.

## Local administration tranche

- MCP add/list/remove/configure-status persist disabled-by-default connection
  records with environment variable names only. Raw environment values and
  headers are never shown. Device login starts only when the operator has
  already configured RFC 8628 endpoints; it returns user code and verification
  URI, never the device code. Browser OAuth and catalog install remain blocked.
- Hooks list and doctor inspect inert local definitions. `hooks test` returns a
  non-executing plan marked `approval_required`; it never runs a command.
  Revocation removes a hash from the approval record.
- Secrets and vault commands show references and metadata only. They do not
  accept secret values on argv or stdout. Interactive secret collection and
  password-manager setup remain blocked pending a real secure input channel.
- Profiles are local Noesek configuration records. List/show/create/use,
  literal describe, rename, and confirmed delete are supported. Remote profile
  install/update, archive interchange, shell aliases, and identity migration
  remain blocked because those formats and process effects are Hermes-specific.
- Checkpoint status/list inspect Noesek's local checkpoint directory. Prune is
  local and requires `--force`. Session repair/optimize commands run Noesek's
  idempotent schema checks; they never claim to repair Hermes SQLite formats.

## Signed plan and archive tranche

- Device-flow initiation persists only user-safe status plus a token reference;
  device/access codes are not printed. Token material remains in the 0600 token
  store. A later process can inspect the reference/status without exposing it.
- `vault add` emits a signed 0600 request-intent artifact describing required
  fields. It cannot accept values on argv or stdin. Password-manager commands
  expose dry connector contracts and reference schemes only.
- Profile export/import uses a versioned JSON schema authenticated with the
  local 0600 operator key. Tampered and cross-home archives are rejected.
- Update, uninstall, and gateway service lifecycle commands create signed,
  non-executing operator plans. `--yes` records approval in the plan but still
  does not mutate the host. An operator-owned executor is a separate boundary.
- External sends, billing, remote installs, and UI/project mutation remain
  explicit exit 3.
