"""Manifest-only plugin discovery. Plugin code is never imported during scanning."""
from pathlib import Path
import json, re
_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

def discover_plugins(roots: list[Path]) -> list[dict]:
    out = []
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir(): continue
        for f in sorted(root.glob("*/noesek-plugin.json")):
            resolved = f.resolve()
            if root not in resolved.parents: continue
            try: data = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): continue
            name = data.get("name", "")
            if not _NAME.fullmatch(name): continue
            capabilities = sorted(set(data.get("capabilities", [])) & {"tools","providers","channels","hooks","skills"})
            out.append({"name":name,"version":str(data.get("version","0")),"capabilities":capabilities,
                        "enabled":False,"reason":"third-party plugin execution requires an explicit trust policy",
                        "manifest":str(resolved)})
    return sorted(out, key=lambda x:x["name"])
