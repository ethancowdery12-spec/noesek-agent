"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream scopes TERMINAL_CWD through the gateway's per-turn context. Noesek
has no terminal scope, so the process env is the scope.
"""
import os


def scope_terminal_cwd() -> str:
    return os.environ.get("TERMINAL_CWD", "")
