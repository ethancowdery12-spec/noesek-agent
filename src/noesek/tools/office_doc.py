"""Office document read/edit through the OfficeCLI binary (roadmap item 51).

OfficeCLI (iOfficeAI/OfficeCLI, Apache-2.0) is a single self-contained binary
that reads, creates, and edits Word/Excel/PowerPoint without Office installed.
Noesek does not bundle it: the tool shells out to the binary named by
NOESEK_OFFICE_CLI (default "officecli" on PATH) and degrades cleanly when it
is absent. Files are confined to the agent file store (~/.noesek/files), so
anything created here is downloadable through /files like any other deliverable.

The full OfficeCLI command surface (create/add/set/remove/view/get/close) is
exposed as bounded actions; argv is built as a list (never a shell string) and
output is capped. Study source: https://github.com/iOfficeAI/OfficeCLI
"""
from __future__ import annotations

import os
import shutil
import subprocess

from pydantic import BaseModel, Field

from .. import filestore

_EXTS = (".docx", ".xlsx", ".pptx")
_READ = ("view", "get")
_WRITE = ("create", "add", "set", "remove", "close")
_OUT_CAP = 8000
_INSTALL = ("OfficeCLI is not installed on this box. It is a single binary: "
            "see https://github.com/iOfficeAI/OfficeCLI/releases, or set "
            "NOESEK_OFFICE_CLI to its path.")


class OfficeDocInput(BaseModel):
    action: str = Field(description="view | get | create | add | set | remove | close")
    file: str = Field(description="file name in the agent file store, ending .docx/.xlsx/.pptx")
    path: str = Field(default="", max_length=300,
                      description="element path for get/add/set/remove, e.g. /slide[1]/shape[1]; "
                                  "for view: outline or html (default outline)")
    props: list[str] = Field(default_factory=list, max_length=20,
                             description="key=value properties for add/set, e.g. title=\"Q4 Report\"")
    as_json: bool = Field(default=False, description="get: request structured JSON output")


def _binary() -> str | None:
    return shutil.which(os.environ.get("NOESEK_OFFICE_CLI", "officecli"))


def _check_file(name: str) -> str | None:
    try:
        filestore._check_name(name)
    except filestore.FileStoreError:
        return "invalid file name"
    if not name.lower().endswith(_EXTS):
        return "file must end in .docx, .xlsx, or .pptx"
    return None


def _run(argv: list[str]) -> dict:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"error": "officecli timed out after 60s"}
    out = (proc.stdout or "")[:_OUT_CAP]
    err = (proc.stderr or "")[:2000]
    if proc.returncode != 0:
        return {"error": f"officecli exited {proc.returncode}", "stderr": err, "stdout": out}
    return {"ok": True, "output": out, **({"stderr": err} if err.strip() else {})}


def office_doc(inp: OfficeDocInput) -> dict:
    action = inp.action.strip().lower()
    if action not in _READ + _WRITE:
        return {"error": f"unknown action '{inp.action}'", "actions": list(_READ + _WRITE)}
    bad = _check_file(inp.file)
    if bad:
        return {"error": bad}
    binary = _binary()
    if not binary:
        return {"error": "officecli binary not found", "install": _INSTALL}

    target = str(filestore.files_dir() / inp.file)
    argv = [binary, action, target]
    if action == "view":
        argv.append(inp.path.strip() or "outline")
    elif action == "get":
        if not inp.path.strip():
            return {"error": "get requires an element path, e.g. /slide[1]/shape[1]"}
        argv.append(inp.path.strip())
        if inp.as_json:
            argv.append("--json")
    elif action in ("add", "set", "remove"):
        if not inp.path.strip():
            return {"error": f"{action} requires an element path"}
        argv.append(inp.path.strip())
        for p in inp.props:
            if "=" not in p:
                return {"error": f"prop '{p}' is not key=value"}
            argv += ["--prop", p]
    result = _run(argv)
    if result.get("ok") and action in _WRITE:
        result["download"] = f"/files/{inp.file}"
    return result
