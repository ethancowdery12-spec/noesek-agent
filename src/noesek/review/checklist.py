"""Review checklists by language (own wording).

A checklist keeps review coverage stable across diffs: correctness,
security, performance, maintainability, tests, plus language-specific
traps for Python. The precision-over-recall stance is deliberate: report
only what you can stand behind; a false alarm costs more trust than a
missed nit.
"""
from __future__ import annotations

STANCE = (
    "Precision over recall: raise an issue only when you are confident it is a real "
    "defect; stay silent when the context is unclear. Treat correctness and security "
    "findings as blocking; style suggestions are non-blocking."
)

DEFAULT_CHECKLIST = """\
Correctness
- Does the new logic do what surrounding contracts imply? Missing boundary
  conditions (empty input, first/last element, zero, None)?
- Are errors handled and surfaced, not swallowed? Is shared state safe under
  concurrent use?
Security
- Injection surfaces (SQL, shell, template, markup) built from untrusted input?
- Secrets, tokens, or personal data logged, hardcoded, or exposed? Missing
  permission checks on new endpoints or handlers?
Performance
- Obvious repeated work (queries or recomputation inside loops)? Unbounded
  growth of memory, files, or connections? Resources released?
Maintainability
- Do names say what the thing is? Does the change follow the patterns of the
  code around it instead of inventing a parallel way?

AI-generation debt (patterns machine-written code gets wrong)
- Failure modes: what happens on timeout, full disk, denied permission, null
  input? Exceptions caught specifically, resources cleaned up on the failure
  path (connections returned, temp files deleted)?
- Orphans: every open/create/subscribe paired with a close/dispose/unsubscribe?
- Hallucinated dependencies: every import a real package and a real exported
  symbol? (Invented plausible-sounding methods are a known failure mode.)
- Architectural drift: same error-handling style, utilities, and structure as
  the surrounding project, not a parallel invention?
- Red flags: empty catch blocks, TODO-instead-of-handling, timeouts with no
  cleanup on expiry.
Tests
- Does new behavior come with coverage? Do the tests exercise the boundary
  cases, not just the happy path?"""

PYTHON_CHECKLIST = """\
Python traps
- Mutable default arguments (def f(x=[])); shared class-level or module-level
  mutable state mutated per call; closures capturing a loop variable.
- Bare 'except:' or 'except Exception' broader than the failure being handled;
  exceptions caught and discarded silently; re-raise losing the original cause
  (use 'raise ... from err'); 'assert' used to validate external input.
- 'is' / 'is not' against string, number, or tuple literals (interning is an
  implementation detail - use ==); == against True/False instead of a plain
  truthiness check; exact == on floats.
- Indexing xs[0], max()/min(), or d[k] on inputs that can be empty or missing
  the key, when no caller contract rules it out; ZeroDivisionError paths."""


def checklist_for(paths: list[str]) -> str:
    parts = [DEFAULT_CHECKLIST]
    if any(p.endswith(".py") or p.endswith(".pyi") for p in paths):
        parts.append(PYTHON_CHECKLIST)
    return "\n\n".join(parts)
