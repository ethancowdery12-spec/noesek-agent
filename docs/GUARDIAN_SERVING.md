# Guardian serving via the Kaggle relay (owner direction 2026-09-26)

Owner: "use the Kaggle token, at least for now, to run the Llama [Laya]
model... use all the free resources you can." This doc is the serving design
for the v6-ep2 guardian checkpoint on $0 infrastructure.

## Why a relay at all

- The v6 checkpoint is 421M params fp16 (~850 MB weights, ~2-3 GB RAM with
  torch). Render free tier has 512 MB - the model cannot live in the web
  service.
- Kaggle gives free CPU/GPU batch kernels with outbound internet but NO
  inbound networking and a 12h session cap. So the model host cannot be a
  server; it must POLL.
- Ergo: Render holds a tiny job queue; a long-running Kaggle CPU kernel
  polls it, scores, posts results back.

## Architecture

```
controller tool call
  -> guardian gate (NOESEK_GUARDIAN_REMOTE=1)
       POST /internal/guardian/jobs            {state}           (enqueue)
       GET  /internal/guardian/jobs/{id}       poll 1s up to timeout
Kaggle relay kernel (CPU, internet on)
       GET  /internal/guardian/jobs/next?wait=25   (long-poll, keyed)
       score with laya.Agent (v6 ep2 checkpoint, mounted as kernel input)
       POST /internal/guardian/jobs/{id}/result    {risk_class, probs}
```

- Relay auth: `X-Guardian-Relay-Key` header == `NOESEK_GUARDIAN_RELAY_KEY`
  (Render env + Kaggle Secret). Job payloads are tool-call state text only;
  results are verdicts only. No credentials, messages, or memory content
  beyond the action under review ever cross the wire.
- Queue: `guardian_jobs` table (id, state, status, result, created_at,
  expires_at). Jobs expire after 120s; the relay skips expired jobs.
- Checkpoint delivery: the relay kernel attaches
  `ethancowdery/noesek-guardian-finetune` as a kernel INPUT - no download,
  no GitHub release hosting. Path:
  /kaggle/input/noesek-guardian-finetune/laya_finetuned_noesek_guardian/
  (the ep2 output dir; ep1 lives beside it at ..._ep1 for rollback).
- 12h cap: at ~11.5h the kernel pushes a NEW VERSION OF ITSELF via
  POST /api/v1/kernels/push (token in a Kaggle Secret) and exits. Cold
  start ~1-3 min; queued jobs drain when the new session starts, so worst
  case a gated call hits its timeout and NOESEK_GUARDIAN_FAIL_MODE applies
  (default open). Two staggered relays (offset ~6h) would shrink the gap;
  noted as an option, not built in v1 of the relay.

## Latency (honest math)

Typical gated call: pickup <=1s (relay usually parked in the 25s long-poll)
+ CPU inference ~0.3-0.8s (2 questions, short sequences) + result post ~0.2s
+ controller poll granularity 1s => ~2-4s typical, ~8s tail under backlog.
This is fine for destructive/irreversible gating and unacceptable as a
per-keystroke check - the gate already only fires on tool calls, and the
parallel fast path is skipped only when the guardian is enabled.

## Rollout

1. Relay endpoints + remote scorer land on main behind
   NOESEK_GUARDIAN_REMOTE=0 (default off), relay kernel pushed but pointed
   at STAGING.
2. Soak on staging: measure real pickup/inference/total latency, watch a
   full 12h self-relaunch cycle.
3. Ethan flips prod (NOESEK_GUARDIAN_ENABLED=1 + REMOTE=1) when he's ready -
   enabling stays his call.
