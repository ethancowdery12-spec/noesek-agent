"""Self-hosted /chat load test (lane 1 scale hardening). $0: pure stdlib+httpx,
runs from any machine, targets a STAGING deployment only.

Prereqs on the target (staging) service:
  NOESEK_LLM_PROVIDER=echo   - no provider spend, full HTTP/DB path exercised
  a Neon *pooled* endpoint   - pgBouncer absorbs per-instance pool fan-out

Usage: python scripts/load_test.py --url https://STAGING.onrender.com \
         --concurrency 1000 --duration 300 --ramp 60
NEVER point this at production.
"""
import argparse
import asyncio
import statistics
import time

import httpx

PROMPTS = [
    "What's on my calendar today?",
    "Summarize my latest emails.",
    "Remind me in 2 hours to call the bank.",
    "What do you remember about my drinks?",
    "Find where authenticate is defined in this repo.",
]


async def worker(client, url, results, stop_at, wid):
    i = 0
    while time.monotonic() < stop_at:
        prompt = PROMPTS[(wid + i) % len(PROMPTS)]
        t0 = time.monotonic()
        try:
            r = await client.post(f"{url}/chat", json={
                "chat_id": f"loadtest-{wid % 50}",  # 50 hot sessions
                "text": prompt}, timeout=60)
            results.append((time.monotonic() - t0, r.status_code))
        except Exception:
            results.append((time.monotonic() - t0, 0))
        i += 1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--concurrency", type=int, default=1000)
    ap.add_argument("--duration", type=int, default=300, help="seconds at full load")
    ap.add_argument("--ramp", type=int, default=60, help="seconds to reach full load")
    args = ap.parse_args()
    if ".onrender.com" in args.url and "staging" not in args.url and "stg" not in args.url:
        raise SystemExit("refusing: URL does not look like staging - never load-test production")

    results: list[tuple[float, int]] = []
    limits = httpx.Limits(max_connections=args.concurrency + 50,
                          max_keepalive_connections=args.concurrency + 50)
    async with httpx.AsyncClient(limits=limits) as client:
        stop_at = time.monotonic() + args.ramp + args.duration
        tasks = []
        for w in range(args.concurrency):
            tasks.append(asyncio.create_task(worker(client, args.url, results, stop_at, w)))
            await asyncio.sleep(args.ramp / args.concurrency)
        await asyncio.gather(*tasks)

    lat = sorted(l for l, _ in results)
    ok = sum(1 for _, s in results if s == 200)
    n = len(results)
    def pct(p):
        return lat[int(p * (n - 1))] if n else 0
    print(f"requests={n} ok={ok} ({ok / max(1, n):.1%}) errors={n - ok}")
    print(f"latency p50={pct(.5):.2f}s p95={pct(.95):.2f}s p99={pct(.99):.2f}s "
          f"mean={statistics.fmean(lat) if lat else 0:.2f}s max={lat[-1] if lat else 0:.2f}s")
    statuses = {}
    for _, s in results:
        statuses[s] = statuses.get(s, 0) + 1
    print("status breakdown:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    asyncio.run(main())
