# Database evaluation (item 62, Ethan Sep 23 2026)

Request (voice-dictated): "switch to using MAX DB for the database or duck DB, or sql lite,
or a columnar database or clickhouse."

## The actual workload

Measured from the codebase, not guessed:

- **11 OLTP tables** (db.py): conversations, messages, memories, browser_state,
  browser_audit, tasks, approvals, traces, compactions, steering_notes, turn_events.
  Access pattern: small point writes per chat turn, short transactions, keyed reads.
- **Full-text memory search**: FTS5 on SQLite / pg full-text on Postgres (translated in db.py).
- **Vector memory**: BLOB vectors, cosine similarity computed in Python (memory_vector.py);
  256-dim default, one row per memory.
- **Scale**: single-user assistant. Thousands of rows, not millions. Concurrency: a handful
  of simultaneous turns.
- **Ops reality**: prod runs on Render (ephemeral disk) with Neon serverless Postgres
  (managed, backups, scale-to-zero). SQLite remains the built-in local/dev default
  (Dockerfile.computer). A real-Postgres CI gate (postgres-boot job) protects the prod path.

## Verdict: no switch wins. Stay on Neon Postgres, keep SQLite as the local default.

| Candidate | Type | Fit for this workload | Verdict |
|---|---|---|---|
| **Neon Postgres (current)** | Managed OLTP row store | Exact fit: ACID for approvals/chat state, full-text search, managed durability on ephemeral hosts, already deployed and healthy | KEEP |
| **SQLite** | Embedded OLTP | Already the built-in local/dev default. Cannot serve prod on Render (ephemeral disk, single-writer, no managed backups) | KEEP as fallback, not a switch |
| **DuckDB** | Embedded OLAP (columnar) | Wrong access pattern: engineered for analytical scans over big data, not small concurrent writes. Nothing to analyze at this scale | REJECT as primary |
| **ClickHouse** | Server OLAP (columnar) | Wrong access pattern + heavy ops (another service to run) for zero analytical need | REJECT |
| **Columnar stores (general)** | OLAP | Chat state is point-write/point-read; columnar pays its cost on exactly the operations we do most | REJECT |
| **MaxDB (SAP)** | Legacy enterprise OLTP | Legacy SAP ecosystem, dead community momentum, no managed free tier, no advantage over Postgres for anything we do | REJECT |

## When to revisit

- **DuckDB** becomes interesting if we ever want offline analytics over the traces /
  turn_events tables (export and query). That is an add, not a switch, and there is no
  consumer for it today.
- **pgvector** becomes interesting if memory vectors outgrow in-Python cosine (tens of
  thousands of memories). Neon supports it; one migration away, not needed at current scale.
- A workload change (many users, heavy multi-writer concurrency) would reopen the question;
  the answer would still be Postgres, just a bigger plan.
