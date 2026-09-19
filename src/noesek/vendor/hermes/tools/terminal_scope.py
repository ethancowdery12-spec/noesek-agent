"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream scopes terminal env values per gateway turn. Noesek reads the process
environment directly.
"""
import os


def terminal_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
