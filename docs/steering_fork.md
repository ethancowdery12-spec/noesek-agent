# Live steering + session fork (v2, stage H)

- **Live steering**: `steer(conversation_id, text)` queues a durable note;
  the controller drains pending notes between tool steps and injects them
  as `[Steering from the user]: ...` context, so a long turn can be
  redirected without waiting for it to finish. Notes are consumed once and
  land on the turn spine.
- **Session fork/resume**: `fork_conversation(...)` copies messages and
  active memories (provenance `fork:<id>`) into a new conversation;
  resume = keep talking to the fork. Forking onto an existing destination
  refuses, matching the import path's never-overwrite rule
  (core/session_portability.py).

## Provenance

Between-step steering re-implements the interrupt/steer pattern studied in
the opencode and OpenCode-derived harness deep-dives (MIT); fork semantics
extend Noesek's existing session portability format. No code copied.
