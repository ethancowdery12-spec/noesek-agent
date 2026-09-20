#!/usr/bin/env python3
"""Run vendored upstream pytest tranches in place and record results.

Each argument is a tranche spec: "<path>" or "<path>::<kexpr>" where kexpr is a
pytest -k expression WITHOUT the -k flag itself (e.g. "not browser and not camofox").

For every tranche we run, with cwd = vendor/hermes-agent:
    python -m pytest <path> -q --no-header -p no:cacheprovider [-k <kexpr>]

Results are merged into tests/upstream/TRANCHE_RESULTS.json after each tranche
(so partial progress survives). A tranche that exceeds the timeout is killed as
a whole process group (SIGKILL) and recorded with exit_code -9.

Never edits vendored files; this only runs tests and writes the manifest.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(REPO, "vendor", "hermes-agent")
MANIFEST = os.path.join(REPO, "tests", "upstream", "TRANCHE_RESULTS.json")
TIMEOUT_S = int(os.environ.get("TRANCHE_TIMEOUT_S", "1500"))

COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|skipped|error|errors|xfailed|xpassed|warning|warnings|deselected)")


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            return json.load(f)
    return {"runner": os.path.basename(__file__), "tranches": {}}


def save_manifest(data):
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, MANIFEST)


def parse_counts(output):
    counts = {}
    for m in COUNT_RE.finditer(output):
        n, kind = m.group(1), m.group(2)
        kind = {"errors": "error", "warnings": "warning"}.get(kind, kind)
        counts[kind] = int(n)
    return counts


def run_tranche(spec):
    if "::" in spec:
        path, kexpr = spec.split("::", 1)
    else:
        path, kexpr = spec, None
    cmd = [sys.executable, "-m", "pytest", path, "-q", "--no-header", "-p", "no:cacheprovider"]
    if kexpr:
        cmd += ["-k", kexpr]
    print(f"[tranche] {spec} ...", flush=True)
    started = time.time()
    proc = subprocess.Popen(
        cmd, cwd=VENDOR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=TIMEOUT_S)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = proc.communicate()
        exit_code = -9
    counts = parse_counts(out or "")
    duration = round(time.time() - started, 1)
    print(f"[tranche] {spec}: {counts} exit={exit_code}", flush=True)
    return {
        "cmd": " ".join(cmd), "counts": counts, "exit_code": exit_code,
        "timed_out": timed_out, "duration_s": duration,
        "tail": (out or "")[-2000:],
    }


def main():
    specs = sys.argv[1:]
    if not specs:
        print("usage: run_upstream_tranches.py <path[::kexpr]> [...]", file=sys.stderr)
        return 2
    data = load_manifest()
    for spec in specs:
        data["tranches"][spec] = run_tranche(spec)
        data["tranches"][spec]["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_manifest(data)
    print("[tranche] all done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
