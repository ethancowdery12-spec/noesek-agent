# Loop guardrails (v2, stage C)

`core.loop_guard.LoopGuard` watches (tool, canonical-arguments) signatures
within one controller turn:

- **Identical retry**: same signature repeated. The first repeat injects a
  synthetic `loop_guard` tool result telling the model to change arguments
  or justify the retry (the call is NOT executed); the next repeat stops
  the turn with an explanatory message.
- **Doom loop**: the last `cycle_window` signatures repeat exactly
  (A,B,C,A,B,C). The turn stops.
- **No progress**: `max_consecutive_errors` failed calls in a row. The turn
  stops with the latest error class so the user gets an actionable summary
  instead of a silent max-steps stop.

Tool exceptions are classified (`timeout`, `validation`, else the exception
type) so spine events and stop messages carry a stable error class.

Thresholds: `NOESEK_LOOP_MAX_IDENTICAL` (3), `NOESEK_LOOP_MAX_ERRORS` (3),
`NOESEK_LOOP_CYCLE_WINDOW` (3). All guard interventions land on the turn
spine (`loop_guard` / `turn_stopped` events).

## Provenance

Identical-retry and cycle detection re-implement patterns studied in the
MIT-licensed harness deep-dives (SWE-agent, opencode, Aider). No code copied.
