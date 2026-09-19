# Durable turn spine (v2, stage A)

Every controller turn emits a typed, ordered event log to the `turn_events`
table. One `turn_id` per turn; `seq` increases monotonically, so a postmortem
replays deterministically with `get_turn_events` / `render_turn`.

## Event kinds

`turn_started`, `model_request`, `model_response`, `tool_call_requested`,
`tool_call_result`, `approval_required`, `approval_decided`,
`policy_blocked`, `turn_completed`, `turn_stopped`, `turn_failed`.

## Write-ahead rule

`tool_call_requested` flushes STRICTLY before the tool runs: if the spine
write fails, the side effect does not run (fail closed; `SpineWriteError`).
All other kinds are best-effort, matching `record_trace`: logging never
breaks a user turn. A crash mid-turn leaves a `tool_call_requested` without
a matching `tool_call_result`, which is exactly what a postmortem needs.

## OTel GenAI attributes

Model events carry OpenTelemetry GenAI semantic-convention attributes:
`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
`gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`. `LLMReply`
gained `usage` (normalized to input/output tokens) and `finish_reason`;
the OpenAI-compatible, fallback, Anthropic, Gemini, and Bedrock adapters
all populate them.

## Redaction

Event data passes through secret-key redaction (same rule as telemetry).
The `gen_ai.*` namespace is exempt: those keys are spec constants, never
credentials.

## Provenance

- Attribute names follow the OpenTelemetry GenAI semantic conventions
  (opentelemetry.io, Apache-2.0). No code copied.
- Write-ahead audit ordering and typed turn events re-implement patterns
  studied in MIT-licensed agent harnesses (see THIRD_PARTY_NOTICES.md) and the
  OpenClaw deep-dive (TypeScript; pattern re-implemented in Python, no
  code ported).
- The pre-existing `traces` audit table is unchanged for compatibility.
