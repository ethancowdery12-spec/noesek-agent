"""Generate needle training data from noesek's production tool schemas.

Wraps the vendor's needle.model.finetune.generate_dataset with the one thing
noesek needs that the stock CLI lacks: per-example TOOL SUBSETS. Embedding
all 35 schemas in every example blows past the model's max-len (1024), so
each generation batch sees one target tool plus a few sampled distractors -
which also teaches discrimination across the full registry.

Keys: the vendor generator reads OPENROUTER_API_KEY (and optional
OPENROUTER_URL override for another OpenAI-compatible provider) from the
environment of the shell you run it in. Run this on a machine where that key
already lives; never paste a key into chat, files, or commands.

Usage (repo root):
    set OPENROUTER_API_KEY=...   (PowerShell: $env:OPENROUTER_API_KEY="...")
    python -m finetune.gen_data --examples 2000 --out finetune/data

Writes train.jsonl / validation.jsonl / test.jsonl (80/10/10) plus a
manifest.json recording exactly how the data was made.
"""
import argparse
import itertools
import json
import os
import random
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def subsets(tools, distractors, seed=42):
    """Yield (target_name, subset) rotating through every tool as the target,
    each padded with a random sample of distractor schemas."""
    rng = random.Random(seed)
    names = [t["name"] for t in tools]
    by_name = {t["name"]: t for t in tools}
    for target in itertools.cycle(names):
        pool = [n for n in names if n != target]
        pick = [target] + rng.sample(pool, min(distractors, len(pool)))
        rng.shuffle(pick)
        yield target, [by_name[n] for n in pick]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", default=os.path.join(_ROOT, "finetune", "tools.json"))
    ap.add_argument("--examples", type=int, default=2000)
    ap.add_argument("--distractors", type=int, default=6,
                    help="distractor schemas per batch (target + this many)")
    ap.add_argument("--model", default="deepseek/deepseek-flash-latest")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(_ROOT, "finetune", "data"))
    args = ap.parse_args()

    with open(args.tools, encoding="utf-8") as f:
        tools = json.load(f)
    os.makedirs(args.out, exist_ok=True)

    from needle.model.finetune import _dedup_key, generate_dataset

    per_batch = max(50, args.examples // len(tools))  # one pass per target
    rows, seen = [], set()
    gen = subsets(tools, args.distractors, seed=args.seed)
    produced = 0
    while produced < args.examples:
        target, subset = next(gen)
        want = min(per_batch, args.examples - produced)
        print(f"[target={target}] generating ~{want} (subset={len(subset)} schemas)", flush=True)
        batch = generate_dataset(subset, want, model=args.model)
        for ex in batch:
            key = _dedup_key(ex)
            if key not in seen:
                seen.add(key)
                rows.append(ex)
        produced = len(rows)
        print(f"  total unique examples: {produced}", flush=True)

    rng = random.Random(args.seed)
    rng.shuffle(rows)
    n_val = max(1, len(rows) // 10)
    n_test = max(1, len(rows) // 10)
    splits = {
        "train.jsonl": rows[n_val + n_test:],
        "validation.jsonl": rows[:n_val],
        "test.jsonl": rows[n_val:n_val + n_test],
    }
    for name, split in splits.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            for ex in split:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    manifest = {
        "tools": args.tools, "tool_count": len(tools),
        "examples": len(rows), "distractors": args.distractors,
        "model": args.model, "seed": args.seed,
        "splits": {k: len(v) for k, v in splits.items()},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest["splits"], indent=2))
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
