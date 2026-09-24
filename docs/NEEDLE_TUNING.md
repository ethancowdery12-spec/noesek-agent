# Tuning needle for noesek (auto-execute lane)

Goal: lift the needle router (121M CPU model) from assist-only to trustworthy
auto-execute for tool routing. Base weights measured wrong picks at
0.69-0.99 confidence - no safe threshold exists until tuned.

## The two paths

| | Local LoRA (`needle finetune`) | Cactus platform (`needle platform finetune`) |
|---|---|---|
| Cost | Free, your hardware | $19 Starter one-time (3 tunes, 3k generated examples, 30 days) |
| Trains | Routing accuracy (LoRA rank 16, base frozen) | Full model + confidence head calibrated on YOUR tools |
| Confidence | Reports `None` (head untouched) | Calibrated - enables confidence-gated auto-execute |
| Export | 4-bit `.cact` | 2-bit `.cact`, per-depth accuracy scores |

**Consequence:** with a local tune, `confidence` stays None, so
`needle_min_confidence` can never fire. Auto-execute after a local tune is
gated by the acceptance suite instead (below). The $19 platform tune is the
only path to vendor-calibrated confidence gating.

## Pipeline (finetune/)

1. **Dump production tools** (must match prod exactly):
   `python -m finetune.dump_tools` -> `finetune/tools.json` (35 tools)
2. **Frozen acceptance suite**: `finetune/cases.py` - 88 cases, 2 positives
   per tool, multi-tool, off-topic refusals, and 6 CRITICAL safety cases
   (side-effect tools must refuse ambiguous requests). Bar: >=90% pass AND
   zero critical failures. Cases are frozen; changing one changes the gate.
3. **Generate data** (synthetic, from the dumped schemas):
   `python -m finetune.gen_data --examples 2000`
   Each batch shows one target tool + 6 sampled distractors (full-registry
   schema dumps exceed max-len 1024; subsets also teach discrimination).
   Keys: the vendor generator reads `OPENROUTER_API_KEY` (+ optional
   `OPENROUTER_URL` override for any OpenAI-compatible provider) from YOUR
   shell env. Run it on a machine where the key already lives. Never paste a
   key into chat, files, or git. Cost estimate: ~2,000 examples ~ 800k tokens
   on deepseek-flask ~ $0.30, or included in the $19 Starter, or ~free
   against an existing provider endpoint via OPENROUTER_URL.
4. **Acceptance, before**: `python -m finetune.acceptance` (base weights).
5. **Train (local)**: `pip install "cactus-needle[train]"`,
   `needle download needle3.safetensors`,
   `needle finetune data/train.jsonl --epochs 3 --out adapter.safetensors`,
   `needle build --lora adapter.safetensors --out noesek-needle3-tuned.cact`.
   Compute: 121M model, ~2k examples, 3 epochs - hours on a desktop CPU
   (WSL2 on Windows works; JAX). Validation loss is the local quality signal.
6. **Acceptance, after**: `python -m finetune.acceptance --weights noesek-needle3-tuned.cact`
   must print PASS (>=90%, zero critical failures) before the weights ship.
7. **Ship**: set `NOESEK_NEEDLE_WEIGHTS=/path/to/noesek-needle3-tuned.cact`
   on the Render service (the router rebuilds the engine in the background;
   base weights remain the fallback when unset).

## Auto-execute gating after a local tune (free path)

The native engine exposes no logits and local builds drop the confidence head
(verified in needle 3.0.4: `needle build` drops it, confidence reports None;
there is no keep flag). The free gate is therefore EMPIRICAL, not scalar:

1. Generate an eval split alongside training data (>=50 examples per tool).
2. `python -m finetune.acceptance --weights tuned.cact --json out.json` now
   emits `per_tool`: per-tool hits, misses and false fires.
3. Auto-execute turns on PER TOOL only where measured precision clears the
   bar (>=98% on >=50 samples) with zero false fires on critical traffic,
   on top of the suite-level PASS. Everything else stays LLM-routed, and
   every auto-executed call still flows through the existing policy/approval
   path (WRITE tools keep approvals). Start with READ-risk tools only.

Optional upgrade (still free): a JAX-side scorer reading sequence logprobs
(the [train] package exposes full logits via model.apply) with Platt scaling
fitted on the eval set - a true calibrated scalar at the cost of jax in the
prod image. The $19 platform tune remains the polished option: learned
confidence head, 2-bit export, per-depth scores, hosted GPUs.
