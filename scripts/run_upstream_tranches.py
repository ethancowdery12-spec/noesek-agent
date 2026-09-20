#!/usr/bin/env python3
"""Run unchanged vendored upstream tests with upstream-equivalent file isolation.

Each argument is ``<paths>`` or ``<paths>::<kexpr>``. Paths may be comma-
separated globs. Every discovered test file runs in its own fresh pytest
subprocess, matching upstream's ``scripts/run_tests.sh`` isolation contract.
This matters: a tranche-wide pytest process leaks module/env/global state across
files and manufactures hundreds of failures that upstream CI never sees.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob, json, os, re, signal, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(REPO, "vendor", "hermes-agent")
MANIFEST = os.path.join(REPO, "tests", "upstream", "TRANCHE_RESULTS.json")
LOGDIR = os.path.join(REPO, "tests", "upstream", "logs")
FILE_TIMEOUT_S = int(os.environ.get("UPSTREAM_FILE_TIMEOUT_S", "900"))
WORKERS = int(os.environ.get("UPSTREAM_TEST_WORKERS", "4"))
COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|skipped|error|errors|xfailed|xpassed|warning|warnings|deselected)")


def parse_counts(output):
    found = {}
    for m in COUNT_RE.finditer(output):
        kind = {"errors": "error", "warnings": "warning"}.get(m.group(2), m.group(2))
        found[kind] = int(m.group(1))
    return found


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:120]


def discover(paths_part):
    files = set()
    for pattern in paths_part.split(","):
        for path in glob.glob(os.path.join(VENDOR, pattern), recursive=True):
            if os.path.isdir(path):
                files.update(glob.glob(os.path.join(path, "**", "test_*.py"), recursive=True))
            elif os.path.isfile(path) and path.endswith(".py"):
                files.add(path)
    return sorted(os.path.relpath(path, VENDOR) for path in files)


def run_file(path, kexpr):
    cmd = [sys.executable, "-m", "pytest", path, "-q", "--no-header"]
    if kexpr:
        cmd += ["-k", kexpr]
    started = time.time()
    clean_env = {
        "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
        "TZ": "UTC", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0", "PYTHONUTF8": "1",
    }
    attempts = []
    timed_out = False
    for attempt in range(2):
        proc = subprocess.Popen(cmd, cwd=VENDOR, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                start_new_session=True, env=clean_env)
        try:
            output, _ = proc.communicate(timeout=FILE_TIMEOUT_S)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, _ = proc.communicate()
            code = -9
        attempts.append(output)
        if code in (0, 5):
            break
    combined = "".join(f"\n--- attempt {i+1} ---\n{text}" for i, text in enumerate(attempts))
    return {"path": path, "cmd": " ".join(cmd), "counts": parse_counts(attempts[-1]),
            "exit_code": code, "timed_out": timed_out,
            "flaky": len(attempts) > 1 and code in (0, 5),
            "duration_s": round(time.time()-started, 1), "output": combined}


def run_tranche(spec):
    paths_part, sep, kexpr = spec.partition("::")
    files = discover(paths_part)
    if not files:
        return {"counts": {}, "exit_code": 4, "timed_out": False,
                "duration_s": 0, "files": 0, "failing_files": [],
                "tail": "no test files matched"}
    os.makedirs(LOGDIR, exist_ok=True)
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pending = {pool.submit(run_file, path, kexpr if sep else None): path for path in files}
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            print(f"[file] {result['path']}: {result['counts']} exit={result['exit_code']}", flush=True)
    results.sort(key=lambda row: row["path"])
    counts = {}
    for row in results:
        for kind, count in row["counts"].items():
            counts[kind] = counts.get(kind, 0) + count
    failing = [row["path"] for row in results if row["exit_code"] not in (0, 5)]
    logpath = os.path.join(LOGDIR, safe_name(spec) + ".log")
    with open(logpath, "w") as log:
        for row in results:
            log.write(f"\n===== {row['path']} (exit {row['exit_code']}, {row['duration_s']}s) =====\n")
            log.write(row["output"])
    with open(logpath, errors="replace") as log:
        output = log.read()
    return {"cmd": "isolated pytest per discovered test file", "counts": counts,
            "exit_code": 1 if failing else 0,
            "timed_out": any(row["timed_out"] for row in results),
            "duration_s": round(time.time()-started, 1), "files": len(files),
            "failing_files": failing,
            "flaky_files": [row["path"] for row in results if row.get("flaky")],
            "workers": WORKERS,
            "log": os.path.relpath(logpath, REPO), "tail": output[-2000:]}


def main():
    if len(sys.argv) < 2:
        print("usage: run_upstream_tranches.py <paths[::kexpr]> [...]", file=sys.stderr)
        return 2
    data = {"runner": os.path.basename(__file__), "isolation": "one pytest process per file", "tranches": {}}
    for spec in sys.argv[1:]:
        print(f"[tranche] {spec}: file-isolated, workers={WORKERS}", flush=True)
        data["tranches"][spec] = run_tranche(spec)
        data["tranches"][spec]["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = MANIFEST + ".tmp"
        with open(tmp, "w") as f: json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, MANIFEST)
    return 0

if __name__ == "__main__":
    sys.exit(main())
