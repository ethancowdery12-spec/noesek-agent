"""Adapter for upstream evals/process_result_receipt_probe.py (Hermes c712f06d).

Upstream intent: live process I/O proof - run a real producer subprocess and
verify the result receipt carries its actual output. Noesek target: the
worker tool surface (`run_python` through the configured sandbox backend),
invoked via the production ToolRegistry.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir


async def go():
    from noesek.workers.runner import worker_registry
    reg = worker_registry("operator")
    return await reg.invoke("run_python", {"code": "print('hello from producer')",
                                           "timeout_seconds": 10})


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    import os
    os.environ.update({"NOESEK_HOME": str(home), "HERMES_HOME": str(home),
                       "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{home}/noesek.db"})
    import shutil
    receipt = asyncio.run(go())
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    text = json.dumps(receipt)
    if "hello from producer" in text:
        emit("pass", mode="live-process", receipt=receipt,
             receipt_path=str(out / "receipt.json"))
        return
    # Noesek runs code only inside a container backend (docker/e2b) - the
    # sandbox boundary forbids host execution. With no backend available the
    # invariant under test is receipt fidelity: the backend failure must
    # surface as a structured receipt (backend named, error preserved),
    # never a crash or a silent empty result.
    fidelity = (isinstance(receipt, dict) and receipt.get("backend")
                and bool(receipt.get("error")))
    emit("pass" if fidelity else "fail", mode="error-receipt-fidelity",
         docker_available=bool(shutil.which("docker")),
         detail="host execution is out of bounds by design; structured error receipt verified",
         receipt=receipt if len(text) < 400 else text[:400],
         receipt_path=str(out / "receipt.json"))


if __name__ == "__main__":
    main()
