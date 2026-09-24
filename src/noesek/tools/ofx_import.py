"""ofx_import: bank/credit-card OFX/QFX statement files -> expense memories.

Batch 4 tranche 2 (roadmap item 87). The parser is ofxparse (MIT, (c) 2009
Jerry Seutter), pinned as the optional [finance] extra - the dependency is
the only thing taken; all code here is ours. Degrades cleanly when the extra
is not installed.

Guardrails (batch-4 brief): informational-only money tooling. This tool only
reads a statement file the user uploaded and logs what it contains. It never
moves money and gives no financial advice.
"""
from __future__ import annotations

import io
import json
import re

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import Memory, Session
from ..filestore import FileStoreError, files_dir

_MAX_BYTES = 5 * 1024 * 1024
_NAME_RE = re.compile(r"^[^/\\]+$")
_FITID_RE = re.compile(r'"fitid":\s*"([^"]+)"')


class OfxImportInput(BaseModel):
    file: str = Field(min_length=1, max_length=200,
                      description="File-store name of the OFX/QFX statement the user uploaded")
    default_category: str = Field(default="uncategorized", max_length=60,
                                  description="Category to stamp on imported rows; the user can re-categorize later")
    limit: int = Field(default=500, ge=1, le=2000,
                       description="Max transactions to import in one pass")


def ofx_import_handler(conversation_id: int):
    async def f(inp: OfxImportInput) -> dict:
        if not _NAME_RE.match(inp.file):
            raise FileStoreError("file must be a plain file-store name (no path separators)")
        path = files_dir() / inp.file
        if not path.is_file():
            raise FileStoreError(f"no such file in the file store: {inp.file}")
        if path.stat().st_size > _MAX_BYTES:
            return {"ok": False,
                    "error": "statement too large (>5MB) - split it and import in parts"}
        try:
            from ofxparse import OfxParser
        except ImportError:
            return {"ok": False,
                    "error": "ofxparse is not installed in this deployment - add the [finance] extra (ofxparse==0.21, MIT)"}

        try:
            ofx = OfxParser.parse(io.BytesIO(path.read_bytes()))
        except Exception:
            return {"ok": False,
                    "error": "could not parse this file as OFX/QFX - export the statement from the bank as .ofx or .qfx and try again"}
        txns, seen = [], set()
        accounts = [a for a in ([getattr(ofx, "account", None)] + list(getattr(ofx, "accounts", None) or [])) if a]
        for acct in accounts:
            stmt = getattr(acct, "statement", None)
            if stmt is None:
                continue
            acct_id = getattr(acct, "account_id", "") or ""
            for t in stmt.transactions or []:
                fid = getattr(t, "id", "") or ""
                key = (acct_id, fid)
                if fid and key in seen:
                    continue
                seen.add(key)
                posted = getattr(t, "date", None)
                txns.append({
                    "date": posted.date().isoformat() if posted else None,
                    "amount": float(getattr(t, "amount", 0) or 0),
                    "payee": ((getattr(t, "payee", "") or "") + " " + (getattr(t, "memo", "") or "")).strip(),
                    "fitid": f"{acct_id}:{fid}" if fid else "",
                })
        if not txns:
            return {"ok": False, "error": "no transactions found - is this an OFX/QFX bank statement?"}
        txns = txns[: inp.limit]

        async with Session() as s:
            existing = (await s.execute(
                select(Memory.content).where(Memory.conversation_id == conversation_id,
                                             Memory.kind == "expense", Memory.active))).scalars().all()
        have = {m.group(1) for c in existing for m in [_FITID_RE.search(c)] if m}

        added = 0
        async with Session() as s:
            for t in txns:
                if t["fitid"] and t["fitid"] in have:
                    continue
                s.add(Memory(conversation_id=conversation_id, kind="expense",
                             content=json.dumps({"date": t["date"], "amount": t["amount"],
                                                 "category": inp.default_category, "note": t["payee"],
                                                 "fitid": t["fitid"]}, ensure_ascii=False),
                             source="ofx_import"))
                added += 1
            await s.commit()

        dates = sorted(d for d in (t["date"] for t in txns) if d)
        return {"ok": True, "imported": added, "skipped_duplicates": len(txns) - added,
                "transactions_found": len(txns),
                "date_range": [dates[0], dates[-1]] if dates else None,
                "statement_total": round(sum(t["amount"] for t in txns), 2),
                "note": "Logged as expense memories (recall 'expenses' to review and re-categorize). "
                        "Informational only - this never moves money and is not financial advice."}
    return f
