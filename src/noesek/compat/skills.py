"""Safe, deterministic SKILL.md discovery without executing skill contents."""
from dataclasses import asdict, dataclass
from pathlib import Path
import re

@dataclass(frozen=True)
class Skill:
    name: str
    path: str
    description: str

_VALID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
def discover_skills(roots: list[Path]) -> list[dict]:
    found: dict[str, Skill] = {}
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir(): continue
        for f in sorted(root.glob("*/SKILL.md")):
            name = f.parent.name
            if not _VALID.fullmatch(name) or name in found: continue
            resolved = f.resolve()
            if root not in resolved.parents: continue
            text = resolved.read_text(encoding="utf-8", errors="replace")
            description = next((x.strip("# ") for x in text.splitlines() if x.strip()), "")[:240]
            found[name] = Skill(name, str(resolved), description)
    return [asdict(found[k]) for k in sorted(found)]
