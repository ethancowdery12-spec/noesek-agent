# Lane 1: scale hardening plan (thousands of concurrent users)

Ordered by Ethan Sep 24 (five-lane program). Money gate: nothing here spends
money without his explicit approval, surfaced through the parent agent first.

## Findings (measured against the codebase)

1. **NullPool in production.** `src/noesek/db.py` built the engine with
   `poolclass=NullPool`: every request opens a fresh Postgres connection and
   closes it. At thousands of concurrent users the connect/disconnect churn
   (plus TLS handshake per connect) melts a hosted Postgres long before the
   app is CPU-bound.
2. **No pgBouncer-incompatible features.** No LISTEN/NOTIFY (the task runner
   polls), no temp tables, no advisory locks, no session state - so Neon's
   pooled endpoint (pgBouncer transaction mode) is compatible. asyncpg's
   prepared-statement cache must be off behind a pooler (handled in code).
3. **Free-tier Render service** (render.yaml: plan free, shared CPU, spins
   down after 15 min idle). At 1k concurrency the instance CPU/queue
   dominates latency - that is itself a finding the load test should
   quantify, not hide.

## What shipped in this PR (free, env-tunable, reversible)

- **Bounded QueuePool for Postgres** (`db_pool_size=5`, `db_max_overflow=10`,
  `db_pool_timeout_seconds=30`, `db_pool_recycle_seconds=300`, pre-ping on;
  recycle sits under Neon's ~5 min idle-compute autosuspend). sqlite keeps
  NullPool. Per-instance connection ceiling is now 15.
- **Pooler detection**: a `-pooler` host in DATABASE_URL disables asyncpg's
  statement cache automatically.
- **Echo LLM adapter** (`NOESEK_LLM_PROVIDER=echo`): exercises the full
  HTTP/controller/DB path with zero provider calls, so load tests measure
  infrastructure at $0 token spend. Never for production traffic.
- **`scripts/load_test.py`**: self-hosted async load driver (ramp + soak,
  p50/p95/p99, status breakdown), 50 hot sessions, refuses URLs that do not
  look like staging.

## Remaining steps (approval-gated)

1. **Neon pooled endpoint** - $0. Neon includes the `-pooler` hostname on
   every plan. Action: swap DATABASE_URL host on the *staging* service to the
   pooled variant. No Neon plan change, no cost.
2. **Staging service on Render** - two options:
   - **Free tier: $0.** A second free web service (shares the 750 free
     instance-hours/month; spins down when idle). Caveat: free shared CPU
     starves at 1k concurrency, so absolute latency numbers reflect the free
     tier, not paid capacity.
   - **Starter: $7/mo.** Always-on, more CPU - realistic capacity read.
     This is the only spend in the whole lane and needs Ethan's yes.
3. **1k-concurrent load test against STAGING ONLY** - $0 incremental with
   the echo adapter and a free staging service. 60s ramp to 1,000 concurrent
   workers, 5 min soak, ~30-50k requests. Success criteria: p95 < 5s under
   load, error rate < 1%, no Neon connection saturation (pooler absorbs
   fan-out: 1 instance x 15 conns max), no task-runner starvation.
4. **Lane 2 keyed eval** (`python -m evals.entity_extraction`) runs on the
   same staging shell while it exists - the build container has no provider
   keys. Wire-in decision: LLM extraction must beat 54.6% F1.

## Cost summary for approval

| item | cost | status |
|---|---|---|
| pool tuning + echo adapter + load script | $0 | merged |
| Neon pooled endpoint | $0 | config swap, pending |
| staging on Render free tier | $0 | option A |
| staging on Render starter | $7/mo | option B, needs approval |
| load test execution | $0 (echo LLM, free tier) | gated on this plan |
| DeepSeek tokens during test | $0 (echo adapter, no provider calls) | by design |

Staging eval capability (Sep 24): the computer image also COPYs `evals/`, so the Render web shell can run the keyed entity-extraction eval (`python -m evals.entity_extraction`) in place; `.dockerignore` keeps generated adapter-results and pycache out of the image.
