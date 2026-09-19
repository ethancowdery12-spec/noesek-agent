# Memory v2 (v2, stage D)

- **Typed memories with provenance**: `kind` is one of `note`, `fact`,
  `preference`, `episode`; `source` records where the memory came from.
  Memory lines in the system prompt carry `[kind#id]` so the model can
  target them.
- **Invalidate-not-overwrite**: the new `supersede_memory` tool replaces a
  memory by writing a new row and marking the old one inactive +
  `superseded_by`; the old content is never mutated. `forget` invalidates.
- **Episodic FTS search**: a SQLite FTS5 index (`memory_fts`, zero added
  dependencies - FTS5 ships with SQLite) backs recall and context assembly,
  ranked by bm25. Builds without FTS5 fall back to the v1 keyword ranker.
  Index writes/deletes are best-effort and never break a turn.
- **Compaction as a persisted, visible transition**: when context assembly
  drops older messages, a `compactions` row records removed count, budget,
  and the dropped message id range, the system note names the compaction id
  (`[N older messages omitted ...; compaction #K]`), and a `compaction`
  event lands on the turn spine.
- **Untrusted-content wrapping**: tool results enter model context wrapped
  in `<untrusted_content source="...">` markers, reinforcing the system
  prompt's rule that tool and web content is data, not instructions.

## Provenance

FTS-backed memory search and typed/superseding memories re-implement
patterns studied in the Apache-2.0 Mem0 and Graphiti deep-dives; untrusted
wrapping follows the AgentDojo (MIT) injection-defense posture. No code
copied; SQLite FTS5 is a built-in, not a vendored dependency.
