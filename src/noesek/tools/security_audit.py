"""Security audit harness (P8, roadmap item 33 - Strix pentest).

`usestrix/strix` is an agentic AI pentester (Apache-2.0). Instead of
embedding an external agent, this is our own bounded auditor: static
probes over our source layer, route enumeration of the FastAPI surface,
and a structured report with file:line evidence for every finding. The
vendored upstream tree (vendor/) is out of scope - it stays
byte-identical; findings there are reported separately, not fixed here.
Deterministic, no model call, no dependencies.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel


class SecurityAuditInput(BaseModel):
    root: str = ""  # empty = the installed noesek package
    include_vendor: bool = False


# (probe_id, severity, regex, message)
PROBES = [
    ("dynamic-exec", "high", r"(?<![\w.])(?:eval|exec)\s*\(",
     "dynamic code execution (eval/exec)"),
    ("shell-true", "high",
     r"\b(?:subprocess\.(?:run|call|Popen|check_output|check_call)|Popen)"
     r"\s*\([^)]*shell\s*=\s*True",
     "subprocess with shell enabled (command-injection risk)"),
    ("os-system", "high", r"\bos\.system\s*\(",
     "os.system call (command-injection risk)"),
    ("pickle-loads", "high", r"\bpickle\.loads?\s*\(",
     "pickle deserialization of untrusted data is unsafe"),
    ("yaml-unsafe", "medium", r"\byaml\.load\s*\((?![^)]*[Ll]oader)",
     "yaml.load without a safe Loader"),
    ("tls-noverify", "medium", r"verify\s*=\s*False",
     "TLS verification disabled"),
    ("cors-wildcard", "medium", r"allow_origins\s*=\s*\[\s*[\"']\*[\"']",
     "CORS allows any origin"),
    ("hardcoded-secret", "high",
     r"(?i)\b(?:api_key|secret|token|password)\s*=\s*[\"'][^\"'\s]{8,}[\"']",
     "possible hardcoded secret"),
    ("sql-fstring", "medium",
     r"(?:execute|executemany|raw)\s*\(\s*f[\"']",
     "SQL built with an f-string (injection risk)"),
    ("bind-all", "low", r"[\"']0\.0\.0\.0[\"']",
     "binds on all interfaces (0.0.0.0)"),
]

# Lines that look like probes but are not real findings.
_PLACEHOLDER = re.compile(
    r"os\.environ|getenv|example|placeholder|xxxx|changeme|your[-_]"
    r"|\.\.\.|redacted|dummy", re.IGNORECASE)

_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}


def _iter_py(root: Path, include_vendor: bool):
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if not include_vendor and rel.parts and rel.parts[0] == "vendor":
            continue
        yield path, rel


def scan_source_tree(root: str | Path, include_vendor: bool = False) -> list[dict]:
    """Run all static probes over a source tree; findings carry evidence."""
    root = Path(root)
    findings: list[dict] = []
    for path, rel in _iter_py(root, include_vendor):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            code = stripped.split("#", 1)[0] if " #" in stripped else stripped
            for probe_id, severity, pattern, message in PROBES:
                if re.search(pattern, code):
                    if probe_id == "hardcoded-secret" and _PLACEHOLDER.search(code):
                        continue
                    findings.append({
                        "probe": probe_id,
                        "severity": severity,
                        "file": str(rel),
                        "line": lineno,
                        "evidence": stripped[:160],
                        "message": message,
                    })
    rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (rank[f["severity"]], f["file"], f["line"]))
    return findings


def enumerate_routes() -> list[dict]:
    """List FastAPI routes of the deployed app; empty if app unavailable."""
    try:
        from ..main import app
    except Exception:
        return []
    routes = []
    for r in app.routes:
        methods = sorted(getattr(r, "methods", []) or [])
        if not methods:
            continue
        deps = [getattr(d, "call", d).__class__.__name__
                for d in getattr(r, "dependant", None).dependencies] \
            if getattr(r, "dependant", None) else []
        routes.append({"path": getattr(r, "path", "?"), "methods": methods,
                       "name": getattr(r, "name", ""), "dependencies": deps})
    return sorted(routes, key=lambda r: r["path"])


def build_report(root: str | Path, include_vendor: bool = False) -> dict:
    findings = scan_source_tree(root, include_vendor=include_vendor)
    by_sev = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        by_sev[f["severity"]] += 1
    routes = enumerate_routes()
    unauthenticated = [r for r in routes
                       if not r["dependencies"] and r["path"] not in ("/healthz", "/readyz")]
    return {
        "root": str(root),
        "scope": ("own layer only (vendor/ excluded)" if not include_vendor
                  else "own layer + vendored upstream"),
        "findings": findings,
        "by_severity": by_sev,
        "routes": routes,
        "routes_without_dependencies": unauthenticated,
        "summary": (f"{len(findings)} finding(s): {by_sev['high']} high, "
                    f"{by_sev['medium']} medium, {by_sev['low']} low; "
                    f"{len(routes)} route(s), {len(unauthenticated)} without "
                    "declared dependencies"),
    }


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]  # src/noesek/


async def security_audit(inp: SecurityAuditInput) -> dict:
    root = inp.root or str(_default_root())
    return build_report(root, include_vendor=inp.include_vendor)
