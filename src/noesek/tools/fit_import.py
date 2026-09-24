"""fit_import: Garmin/wearable .FIT activity files -> workout memories.

Batch 4 tranche 3 (roadmap item 87). The parser is fitparse (MIT, (c) 2011-2020
David Cooper, (c) 2017-2020 Carey Metcalfe), pinned as the optional [fitness]
extra - the dependency is the only thing taken; all code here is ours.
Degrades cleanly when the extra is not installed. OAuth wearable accounts
(Garmin Connect, Strava) are a later tranche; this is the file-upload path.

Guardrails (batch-4 brief): informational-only health tooling. This logs what
the file contains; it is not medical advice.
"""
from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import Memory, Session
from ..filestore import FileStoreError, files_dir

_MAX_BYTES = 20 * 1024 * 1024
_NAME_RE = re.compile(r"^[^/\\]+$")
_FITHASH_RE = re.compile(r'"fithash":\s*"([^"]+)"')


class FitImportInput(BaseModel):
    file: str = Field(min_length=1, max_length=200,
                      description="File-store name of the .FIT activity file the user uploaded")
    note: str = Field(default="", max_length=200,
                      description="Optional note to attach to the workout entry")


def _session_fields(fit) -> dict:
    """Pull the summary fields from the first session record (own mapping)."""
    out: dict = {}
    for rec in fit.get_messages("session"):
        for f in rec.fields:
            if f.name in ("sport", "start_time", "total_elapsed_time", "total_distance",
                          "total_calories", "avg_heart_rate", "max_heart_rate") and f.value is not None:
                out.setdefault(f.name, f.value)
        break
    return out


def fit_import_handler(conversation_id: int):
    async def f(inp: FitImportInput) -> dict:
        if not _NAME_RE.match(inp.file):
            raise FileStoreError("file must be a plain file-store name (no path separators)")
        path = files_dir() / inp.file
        if not path.is_file():
            raise FileStoreError(f"no such file in the file store: {inp.file}")
        if path.stat().st_size > _MAX_BYTES:
            return {"ok": False, "error": "activity file too large (>20MB)"}
        try:
            from fitparse import FitFile
        except ImportError:
            return {"ok": False,
                    "error": "fitparse is not installed in this deployment - add the [fitness] extra (fitparse==1.2.0, MIT)"}

        raw = path.read_bytes()
        fithash = hashlib.sha256(raw).hexdigest()[:16]
        try:
            fit = FitFile(raw)
            fields = _session_fields(fit)
        except Exception:
            return {"ok": False,
                    "error": "could not parse this file as .FIT - export the activity from the device/app as .fit and try again"}
        if not fields:
            return {"ok": False, "error": "no session record found - is this a recorded activity file?"}

        async with Session() as s:
            existing = (await s.execute(
                select(Memory.content).where(Memory.conversation_id == conversation_id,
                                             Memory.kind == "workout", Memory.active))).scalars().all()
        if any(m and m.group(1) == fithash for c in existing for m in [_FITHASH_RE.search(c)]):
            return {"ok": True, "imported": 0, "skipped_duplicates": 1,
                    "note": "This exact file was already imported."}

        start = fields.get("start_time")
        entry = {"date": start.date().isoformat() if hasattr(start, "date") else None,
                 "activity": str(fields.get("sport", "unknown")),
                 "duration_min": round(fields["total_elapsed_time"] / 60, 1) if "total_elapsed_time" in fields else None,
                 "distance_km": round(fields["total_distance"] / 1000, 2) if "total_distance" in fields else None,
                 "calories": fields.get("total_calories"),
                 "avg_hr": fields.get("avg_heart_rate"),
                 "max_hr": fields.get("max_heart_rate"),
                 "note": inp.note, "fithash": fithash}
        async with Session() as s:
            s.add(Memory(conversation_id=conversation_id, kind="workout",
                         content=json.dumps(entry, ensure_ascii=False), source="fit_import"))
            await s.commit()
        return {"ok": True, "imported": 1, "skipped_duplicates": 0,
                "workout": {k: v for k, v in entry.items() if v not in (None, "")},
                "note": "Logged as a workout memory (recall 'workouts' to review). "
                        "Informational only - not medical advice."}
    return f
