# Needle tuning - decision record (Sep 23, 2026)

Readable cold. Why needle3 (the 121M CPU tool-router) is still assist-only,
what we verified about the engine, the options for getting to auto-execute,
what we chose, and what is still open.

## Current state

- Pipeline MERGED to main in PR #130 (`finetune/` + this doc + the runbook
  `NEEDLE_TUNING.md`). Scripts and docs only - nothing flips at runtime.
- `NOESEK_NEEDLE_WEIGHTS` is UNSET everywhere. Production runs base weights.
- Needle assist is ON (suggests tools to the LLM; measured 13-14s answers,
  no chat flap after #126-#128). Auto-execute is OFF
  (`needle_auto_execute=False`), and base weights measured wrong picks at
  0.69-0.99 "confidence" - no safe threshold exists until tuned.

## Verified engine facts (needle 3.0.4, read from the installed package)

1. The runtime is a closed native library. Its whole API is
   `needle_init / needle_complete / needle_reset / needle_load / needle_embed`.
   `needle_complete` returns one JSON envelope: `{type, function_calls,
   confidence, ...}`. There are NO logits, logprobs, or per-call scores
   exposed. (needle/__init__.py, _worker.py)
2. Local fine-tuning can never ship a confidence head. `needle finetune`
   trains LoRA adapters only; `needle build` DROPS the head on export -
   the package says it verbatim: "local tuning leaves the confidence head
   untrained; needle build drops it and confidence reports None"
   (model/finetune.py). There is no flag to keep it. Only the Cactus
   platform tune trains + ships the head.
3. Base weights DO carry a head (that's where the misleading 0.69-0.99
   numbers come from), but it is not trained for our tools.
4. The training stack is JAX/Flax and exposes full logits
   (`model.apply(...)`, model/finetune.py:415) - so a self-built scorer is
   possible offline even though the prod engine gives no scores.
5. Training data embeds the full tool schema set per example; all 35 noesek
   schemas blow past max-len 1024. Hence per-example target+distractor
   subsets (finetune/gen_data.py).

## Options considered

### A. Local LoRA tune + per-tool empirical gate  <- CHOSEN free path
Tune free on Ethan's Windows box (WSL2) overnight, then gate auto-execute
per tool on MEASURED behavior: run a frozen eval (>=50 examples/tool),
auto-execute only tools with >=98% precision AND zero false fires on
critical traffic, on top of the frozen acceptance suite (88 cases, >=90%
pass + zero critical failures). READ-risk tools first; WRITE tools keep
their existing approvals regardless.
- Pros: $0. More conservative than a scalar. No new prod runtime path.
- Cons: no per-call confidence score (gate is a static per-tool table, not
  a live judgment); overnight CPU run on Ethan's box; we own the eval
  harness forever; table must be re-measured after every re-tune.

### B. Local LoRA + self-built Platt calibration (JAX-side)
Score each pick's sequence logprob with the [train] package's JAX model,
fit Platt scaling on the frozen eval, gate on the calibrated probability.
- Pros: a real per-call scalar, $0.
- Cons: raw sequence likelihood is length-biased and likelihood !=
  P(correct) - post-hoc scaling ranks worse than a learned head; jax in the
  prod image (~100MB) and ~1-3s CPU per turn; most custom code to maintain.
  Held as the upgrade if A's table proves too coarse.

### C. Cactus platform tune - $19 Starter (one-time)
`needle platform finetune`: hosted GPUs, full-model training, data
reinforced with the vendor's dataset, 2-bit export, per-depth accuracy.
- Buys: the LEARNED confidence head calibrated on our tools (the only
  vendor-supported confidence), no overnight local run, better exports.
- Does NOT buy: safety. Critical refusals and per-tool trust still have to
  be measured on OUR frozen suite; the vendor head doesn't replace it.
- Pricing verified live (GET /v1/plans): Starter $19 once, 3 tunes +
  3,000 generated examples, 30 days. Pro $99/mo exists; Starter suffices.

## Status: DEFERRED by Ethan (Sep 23, 2026)

Ethan's call: "I will invest in it at a later point." Data-gen, the training
run, and the Starter purchase are deferred indefinitely. Needle stays in
assist mode as shipped; auto-execute stays OFF. This lane re-opens ONLY on
his word - when it does, start from "Open decisions" below.

## Open decisions (Ethan) - parked

1. Data-gen path: (a) free - run finetune/gen_data.py on his box against
   his existing LLM provider endpoint (OPENROUTER_URL override; key never
   leaves his shell); (b) ~$0.60 OpenRouter pay-per-token via a fresh
   vaulted key; (c) bundled in the $19 Starter.
2. Starter: buy for the calibrated head + hosted tune, or stay free.
3. Weights flip: set NOESEK_NEEDLE_WEIGHTS on Render only after the
   acceptance suite PASSes on the tuned artifact (reversible env flip).
4. Auto-execute criteria: exact precision bar, per-tool allowlist contents,
   and READ-only scope for v1 - to be set from the measured per_tool table,
   not picked in advance.

## Also still open elsewhere

- "laya" model pick (xLAM-1b-fc-r / LFM2-1.2B-Tool / Llama-3.2-1B) -
  awaiting Ethan's choice; separate from this lane.
