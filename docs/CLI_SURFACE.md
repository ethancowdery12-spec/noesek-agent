# Noesek command surface

`noesek` is the product's single CLI. With no arguments (or `noesek chat`) it
opens the interactive terminal UI; `noesek -z "prompt"` runs a one-shot;
`noesek --help` lists the full surface: 289 command paths, 556 options, and
102 in-session slash commands. `noesek --compat-report` prints the manifest
summary and the pinned upstream source.

The command grammar is generated from a pinned manifest
(`compat/cli-manifest.json`, shipped copy at `src/noesek/data/cli-manifest.json`)
so every documented spelling parses exactly. Execution always stays in Noesek:
each command path either has a real Noesek adapter or exits 3 with a clear
"no safe execution adapter yet" message and never falls through to a surprise
behavior. Commands parsed but not yet adapted are the only gaps. The two
onboarding commands, `noesek setup` and `noesek model`, execute the vendored
wizard/provider picker under the Noesek layer (Noesek home, skin, branded
output, safety shim).

Noesek-native additions beyond the manifest surface: `worker`, `acp-serve`,
`providers`, `memories search`, and `incidents list|postmortem`.

Upstream code is vendored under `src/noesek/vendor/` under the MIT License;
see `THIRD_PARTY_NOTICES.md`, `VENDORING.md`, and `docs/licenses/` for the
required attribution, and `tools/inventory_hermes_cli.py` for regenerating the
manifest from the pinned upstream checkout.
