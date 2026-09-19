# Noesek v1.6.0 - reuse tranche 6: channel SDKs, eval boundary, teams migration

## What landed

1. **Slack transport** (`channels/slack_sdk.py`) on pinned `slack-sdk==3.39.0`
   (MIT): real SignatureVerifier request verification (fails closed without a
   configured signing secret), Web API sends with dry-run when unconfigured,
   injectable client. No live workspace contacted.
2. **Telegram transport** (`channels/telegram_sdk.py`): constant-time
   secret-token webhook verification (fails closed unconfigured), Bot API sends
   with dry-run, injectable Bot. aiogram (MIT) is NOT a core dependency - it caps
   pydantic below the project's exact 2.13.5 pin - so the bot process runs as a
   sidecar with its own environment (`sidecars/telegram_bot.py`), transport only;
   Noesek remains policy owner.
3. **deepeval boundary**: process-isolated by design (heavy import graph);
   `tools/evals.build_deepeval_cases` emits deepeval-compatible case JSON for an
   external runner. Joins the promptfoo process boundary from v1.5.0.
4. **teams.py migrated** onto orchestration primitives: TeamRun carries a
   WorkBudget and CancellationToken; reports accept typed WorkerResults;
   cancel() propagates through the token; controller-owned `synthesize()` runs
   only after the outcome owner completes. Existing constructor semantics kept.
5. **browser-use deferred with reason**: 0.9.5 (MIT) forces a downgrade of the
   pinned websockets 17.1 -> 16.1.1, violating the exact-pin policy. Deferred
   until a compatible release.

## Verification

473 passed, 43 skipped (255 unchanged upstream Hermes tests included).
Signature forgery, fail-closed, dry-run, injected-client, budget, cancellation,
and synthesis-ordering paths all covered.

## Next-stage ledger

- Wire Slack/Telegram transports into channel routers behind the authorization
  gate (ingress verification handlers).
- browser-use once a release respects the websockets pin.
- Broader Hermes evals/ suite as external harness (process boundary).

Also fixed: earlier dependency installs had silently downgraded pydantic below the exact pin; restored and lock-regenerated.
