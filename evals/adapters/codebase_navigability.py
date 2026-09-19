"""Adapter for upstream evals/codebase_navigability/ (Hermes c712f06d).

Upstream intent: offline, deterministic static metrics of what a codebase
costs an LLM agent to navigate. The upstream tool is codebase-agnostic
(static_metrics.py TREE LABEL), so this adapter runs the PINNED UPSTREAM CODE
UNMODIFIED against the Noesek tree - a true `run`, not a reimplementation.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REPO, emit, out_dir

UPSTREAM = REPO.parent / "hermes-src" / "evals" / "codebase_navigability" / "static_metrics.py"


def main():
    out = out_dir()
    if not UPSTREAM.is_file():
        emit("skip", reason="pinned hermes-src checkout not present", tool=str(UPSTREAM))
        return
    import shutil
    if not (shutil.which("radon") or (Path(sys.executable).parent / "radon").exists()):
        emit("skip", reason="radon not installed (test extra)", tool=str(UPSTREAM))
        return
    r = subprocess.run([sys.executable, str(UPSTREAM), str(REPO), "noesek"],
                       capture_output=True, text=True, timeout=300)
    (out / "static_metrics_stdout.txt").write_text(r.stdout)
    (out / "static_metrics_stderr.txt").write_text(r.stderr)
    ok = r.returncode == 0 and bool(r.stdout.strip())
    emit("pass" if ok else "fail", tool=str(UPSTREAM), exit=r.returncode,
         output_path=str(out / "static_metrics_stdout.txt"))


if __name__ == "__main__":
    main()
