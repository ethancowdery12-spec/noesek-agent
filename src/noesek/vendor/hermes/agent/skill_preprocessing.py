"""Noesek-authored bridge (NOT upstream Hermes source).

Template/inline-shell preprocessing of skill bodies is not vendored in this
tranche; content passes through unchanged. Listed in the next-stage ledger.
"""
from pathlib import Path


def preprocess_skill_content(content: str, skill_dir: Path | None, session_id: str | None = None,
                             skills_cfg: dict | None = None) -> str:
    return content
