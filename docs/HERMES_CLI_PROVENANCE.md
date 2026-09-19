# Hermes CLI provenance and adaptation

Audited 2026-09-17 against the canonical public repository
https://github.com/NousResearch/hermes-agent at commit
`228022ef5b209cb0a3d739394edddf887e1db0f6`.

Hermes Agent is MIT licensed by Nous Research. The license permits use,
modification, distribution, and sublicensing provided its copyright and
permission notice accompany copies or substantial portions. Noesek includes
that notice in `docs/licenses/HERMES-AGENT-MIT.txt` and attribution in
`THIRD_PARTY_NOTICES.md`.

## What was reused

Behavioral and UX ideas from the public CLI documentation:

- one-shot chat with clean text, JSON, or JSONL event output
- status and doctor diagnostics
- secret-redacted configuration inspection
- session list, JSON export, and explicit-confirmation deletion
- prompt/tool-schema size reporting
- local backup and bash/zsh/fish completion

## What was not copied

No Hermes Python, JavaScript, prompts, assets, dependencies, credentials, or
private material are included. The Noesek implementation was written against
Noesek's existing database, controller, and configuration types. This avoids
pulling Hermes' much larger optional dependency tree or code with unclear
upstream provenance. Hermes capabilities outside this focused subset, such as
OAuth provider setup, plugin marketplaces, ACP/MCP servers, desktop UI,
terminal execution, and multi-host peer control, remain out of scope.

## Dependency audit boundary

Because no Hermes dependency was added, Noesek's runtime dependency set is
unchanged. The Hermes repository includes many optional Python and JavaScript
components; their transitive licenses do not transfer to this release because
none are redistributed or imported. Noesek's own dependency notices remain in
`THIRD_PARTY_NOTICES.md`.

## v0.4 full-port Stage 1
The modules in `noesek.compat` are independent implementations based on public behavior and feature categories. No Hermes source, prompts, assets, tests, dependency lockfiles, or generated compatibility shims were copied. The pinned repository was used for the matrix and gap ledger. Its full MIT notice remains in `docs/licenses/HERMES-AGENT-MIT.txt`.
