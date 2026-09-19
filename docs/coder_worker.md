# Coder worker (v2, stage E)

The coder worker edits the local workspace through an aider-style edit
protocol instead of free-form shell access:

- `repo_map` - deterministic workspace map: file list plus Python
  def/class signatures (ast), budget-truncated. Map first, then edit.
- `apply_edit` - SEARCH/REPLACE hunks. A hunk applies only when its search
  text matches exactly once; failed hunks are reported and skipped
  (per-hunk salvage), so one bad hunk never discards good edits.
- `write_file` - create/overwrite (new files).
- `submit` - structured submit checklist: summary, files_changed,
  verification (command + observed result), limitations.

All file access is confined to the allowlisted workspace root (same
confinement as `read_file`, vendored Hermes path-security helpers).
Delegation to the coder is approval-gated at the controller
(`delegate_task` is a WRITE tool); these tools never leave the workspace.

## Provenance

SEARCH/REPLACE with exact-match hunk application and per-hunk salvage
re-implements the aider edit format (Apache-2.0) and the repo-map idea
(aider, Apache-2.0; SWE-agent, MIT). No code copied; implemented against
the local pydantic/SQLite stack.

## Follow-up (E2)

Sandboxed `run_command` verification (workspace mounted read-only,
network disabled) for build/test evidence on the submit checklist.

## E2: sandboxed verification

`run_command` runs a shell command in the Docker sandbox with the workspace
mounted READ-ONLY at `/workspace`, network disabled, same isolation flags as
`run_python` (plus `PYTHONDONTWRITEBYTECODE=1` so test runs work on the ro
mount). docker-cli and docker-py backends implement it; e2b reports it as
unsupported. The submit checklist's `verification` field is where observed
exit codes and output tails land.
