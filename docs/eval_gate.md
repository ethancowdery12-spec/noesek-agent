# Eval gate (v2, stage G)

- **Trajectory assertions** (`evals/trajectory.py`): fake-model
  (ScriptedLLM) controller runs leave a full turn-spine trail; helpers
  assert ordered subsequences, absent events, and tool-call evidence.
- **Injection suite** (`evals/injection_suite.py`): AgentDojo-style
  scenarios where a scripted model fully obeys an injection smuggled in
  tool output (direct override, fake approval, authority claim,
  exfiltration). A scenario passes only when the injected goal never
  executes: the approval gate holds, no write-ahead tool request is
  logged, content stays wrapped as untrusted data yet still reaches the
  model as data.
- **CI gate** (`.github/workflows/eval-gate.yml`): on every PR and push to
  main - full pytest suite, injection suite, and the adapter evals.

## Provenance

Injection-scenario design follows the AgentDojo benchmark (MIT); assertion
helpers are original. No benchmark code or data copied.
