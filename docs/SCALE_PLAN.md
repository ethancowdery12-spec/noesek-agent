# Scale plan: thousands of concurrent users (item 67, Ethan Sep 23 9:31 AM)

"Do the heavy stuff as this will eventually have thousands of concurrent users."
This re-opens every single-user decision. Ordered by what breaks first.

## 1. Database engine: verdict HOLDS (Neon Postgres), addendum to docs/DB_EVALUATION.md
The engine is not the bottleneck at this scale:
- Neon serverless Postgres scales compute automatically and ships a built-in
  PgBouncer pooler endpoint; thousands of concurrent users need the pooler
  DSN + SQLAlchemy pool sizing (pool_size, max_overflow, pool_pre_ping),
  documented in the deploy checklist below.
- DuckDB/ClickHouse/columnar stay rejected: OLAP engines for an OLTP+FTS
  workload. MaxDB stays rejected (legacy SAP). SQLite stays local-dev only
  (single-writer file - wrong for concurrent writes).
- Read scaling path if ever needed: Neon read replicas for recall/assemble
  reads. Not needed at thousands of users on one writer.

## 2. What actually falls over (build-now items)
a. **User scoping (correctness + privacy, not just scale).** recall/assemble
   pool ALL active memories deployment-wide (Sep 22 single-user fix), and
   graph_boost/vector_scores scan deployment-wide tables. One user on the
   deployment: fine. Thousands: user A's memories leak into user B's recall
   and every recall scans every user's data. Fix: pool scoping threaded
   through recall/assemble/graph/vector (this PR). OPEN PRODUCT DECISION
   (Ethan): the computer surface identifies sessions by chat_id only; a real
   user identity (auth) must group a user's chats into one pool. Until that
   exists the scope defaults to deployment-wide = today's behavior.
b. **graph_boost full-table Python scans.** Every recall loaded ALL entities
   and edges into Python. Fixed this PR: 1-hop expansion pushed into SQL.
c. **vector_scores in-Python cosine over all vectors.** Acceptable per-user
   at hundreds of memories; at thousands per user move to pgvector
   (Neon supports it) - deferred, trigger documented.
d. **Connection churn:** computer server opens sessions per request; pool
   settings above + Neon pooler cover it.

## 3. IBM-paper heavy options re-decided at scale
- Schema-rich KG: STILL rejected - the paper's cost finding is about
  construction tokens per memory, which scales with memories, not users.
- Hierarchical LLM retrieval + write-time rerank: STILL rejected - per-user
  memory pools stay small (hundreds); concurrency does not change per-pool
  size. Revisit trigger: a single user's active memories > ~500.
- What DOES earn its place at scale: per-user scoping (2a) and set-based SQL
  retrieval (2b) - built here.

## 4. Deploy checklist when multi-user ships
- [ ] User identity/auth on the computer surface (groups chats into pools)
- [ ] DATABASE_URL pointed at Neon's pooled endpoint (-pooler host)
- [ ] SQLAlchemy pool_size/max_overflow tuned; pool_pre_ping on
- [ ] pgvector migration if any user passes ~500 active memories
- [ ] Load test: 1k concurrent chat posts against staging
