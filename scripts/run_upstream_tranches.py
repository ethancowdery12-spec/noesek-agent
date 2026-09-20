#!/usr/bin/env python3
"""Run vendored upstream pytest tranches in place and record results.

Each argument is a tranche spec: "<paths>" or "<paths>::<kexpr>" where <paths>
is a comma-separated list of paths or glob patterns (expanded inside
vendor/hermes-agent) and kexpr is a pytest -k expression WITHOUT the -k flag.

For every tranche we run, with cwd = vendor/hermes-agent:
    python -m pytest <expanded paths> -q --no-header -p no:cacheprovider [-k <kexpr>]

Pytest output streams live into tests/upstream/logs/<tranche>.log, so a job
that dies mid-tranche still leaves full partial output behind. Results are
merged into tests/upstream/TRANCHE_RESULTS.json after each tranche. A tranche
that exceeds the timeout is killed as a whole process group (SIGKILL) and
recorded with exit_code -9.

Never edits vendored files; this only runs tests and writes the manifest/logs.
"""
import glob
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
LOGDIR = os.path.join(REPO, "tests", "upstream", "logs")
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


def safe_name(spec):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", spec)[:120]


def run_tranche(spec):
    if "::" in spec:
        paths_part, kexpr = spec.split("::", 1)
    else:
        paths_part, kexpr = spec, None
    paths = []
    for pat in paths_part.split(","):
        expanded = sorted(glob.glob(os.path.join(VENDOR, pat)))
        paths.extend(os.path.relpath(p, VENDOR) for p in expanded if os.path.isfile(p) or os.path.isdir(p))
    if not paths:
        print(f"[tranche] {spec}: NO FILES MATCHED", flush=True)
        return {"cmd": "", "counts": {}, "exit_code": 4, "timed_out": False,
                "duration_s": 0.0, "tail": "no files matched"}
    cmd = [sys.executable, "-m", "pytest"] + paths + ["-q", "--no-header", "-p", "no:cacheprovider"]
    if kexpr:
        cmd += ["-k", kexpr]
    os.makedirs(LOGDIR, exist_ok=True)
    logpath = os.path.join(LOGDIR, safe_name(spec) + ".log")
    print(f"[tranche] {spec} -> {len(paths)} paths, log {logpath}", flush=True)
    started = time.time()
    with open(logpath, "w") as logf:
        proc = subprocess.Popen(
            cmd, cwd=VENDOR, stdout=logf, stderr=subprocess.STDOUT,
            text=True, start_new_session=True,
        )
        timed_out = False
        try:
            proc.wait(timeout=TIMEOUT_S)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            exit_code = -9
    with open(logpath, errors="replace") as f:
        out = f.read()
    counts = parse_counts(out)
    duration = round(time.time() - started, 1)
    print(f"[tranche] {spec}: {counts} exit={exit_code}", flush=True)
    return {
        "cmd": " ".join(cmd), "counts": counts, "exit_code": exit_code,
        "timed_out": timed_out, "duration_s": duration,
        "log": os.path.relpath(logpath, REPO), "tail": out[-2000:],
    }


def main():
    specs = sys.argv[1:]
    if not specs:
        print("usage: run_upstream_tranches.py <paths[::kexpr]> [...]", file=sys.stderr)
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
