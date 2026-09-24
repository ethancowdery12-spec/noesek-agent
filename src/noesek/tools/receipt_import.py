"""receipt_import: receipt photos (or pasted receipt text) -> expense memories.

Batch 4 tranche 7 (roadmap item 87). OCR is pytesseract (Apache-2.0,
(c) Samuel Hoffstaetter), pinned as the optional [ocr] extra; it drives the
tesseract binary (Apache-2.0) installed in the image. The dependency is the
only thing taken; all parsing code here is ours. Degrades cleanly: without
the extra, without the binary, or on OCR failure the tool tells the user to
paste the receipt text and structures that instead (the text= path never
touches OCR).

Guardrails (batch-4 brief): informational-only money tooling. This records
what the receipt says; it does not move money or give financial advice.
"""
from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import Memory, Session
from ..filestore import FileStoreError, files_dir

_MAX_BYTES = 10 * 1024 * 1024
_NAME_RE = re.compile(r"^[^/\\]+$")
_HASH_RE = re.compile(r'"receipthash":\s*"([^"]+)"')
_AMOUNT_RE = re.compile(r"([$€£])?\s*(\d{1,5}[.,]\d{2})")
_DATE_RES = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),                        # 2026-09-24
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"),                  # 09/24/2026
    re.compile(r"\b(\d{1,2}-[A-Za-z]{3}-\d{2,4})\b"),              # 24-Sep-2026
    re.compile(r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b"),        # Sep 24, 2026
]
_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}


class ReceiptImportInput(BaseModel):
    file: str = Field(default="", max_length=200,
                      description="File-store name of the uploaded receipt photo (jpg/png). Omit when pasting text.")
    text: str = Field(default="", max_length=8000,
                      description="Pasted receipt text - use when there is no photo or OCR is unavailable.")
    note: str = Field(default="", max_length=200,
                      description="Optional note to attach to the expense entry")


def _parse_amounts(text: str) -> list[tuple[str, float]]:
    out = []
    for sym, num in _AMOUNT_RE.findall(text):
        try:
            out.append((_CURRENCY.get(sym, "USD"), float(num.replace(",", "."))))
        except ValueError:
            continue
    return out


def parse_receipt(text: str) -> dict:
    """Own-words heuristics: merchant (first alpha line), date (first plausible
    date), total (TOTAL line amount, else the largest amount on the ticket)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    merchant = ""
    for l in lines[:8]:
        if re.search(r"[A-Za-z]{3}", l) and not re.search(
                r"\b(st|ave|rd|blvd|road|street|avenue|suite|ste|phone|tel)\b", l, re.I):
            merchant = l[:80]
            break
    date = ""
    for l in lines:
        for rx in _DATE_RES:
            m = rx.search(l)
            if m:
                date = m.group(1)
                break
        if date:
            break
    total, currency = None, "USD"
    for l in lines:
        if re.search(r"\btotal\b", l, re.I) and not re.search(r"sub\s*total|subtotal", l, re.I):
            amts = _parse_amounts(l)
            if amts:
                currency, total = amts[-1][0], amts[-1][1]
    if total is None:
        amts = _parse_amounts(text)
        if amts:
            currency = amts[-1][0]
            total = max(a for _, a in amts)
    return {"merchant": merchant, "date": date, "total": total, "currency": currency}


def receipt_import_handler(conversation_id: int):
    async def f(inp: ReceiptImportInput) -> dict:
        if bool(inp.file) == bool(inp.text):
            return {"ok": False, "error": "give exactly one of: file (receipt photo in the file store) or text (pasted receipt)"}
        if inp.file:
            if not _NAME_RE.match(inp.file):
                raise FileStoreError("file must be a plain file-store name (no path separators)")
            path = files_dir() / inp.file
            if not path.is_file():
                raise FileStoreError(f"no such file in the file store: {inp.file}")
            if path.stat().st_size > _MAX_BYTES:
                return {"ok": False, "error": "receipt image too large (>10MB)"}
            raw = path.read_bytes()
            source_desc = inp.file
            try:
                import pytesseract
            except ImportError:
                return {"ok": False,
                        "error": "OCR is not installed in this deployment - add the [ocr] extra (pytesseract, Apache-2.0). "
                                 "You can still paste the receipt text and I will log that."}
            try:
                text = pytesseract.image_to_string(str(path))
            except pytesseract.TesseractNotFoundError:
                return {"ok": False,
                        "error": "the tesseract OCR binary is missing in this deployment. "
                                 "You can still paste the receipt text and I will log that."}
            except Exception:
                return {"ok": False,
                        "error": "OCR could not read this image - try a sharper, flatter photo, or paste the receipt text."}
            if not text.strip():
                return {"ok": False,
                        "error": "OCR read no text from this image - try a sharper photo, or paste the receipt text."}
        else:
            raw = inp.text.encode("utf-8")
            text = inp.text
            source_desc = "pasted text"

        rhash = hashlib.sha256(raw).hexdigest()[:16]
        parsed = parse_receipt(text)
        if parsed["total"] is None and not parsed["merchant"]:
            return {"ok": False,
                    "error": "could not make out a merchant or total - paste the receipt text and I will structure it."}

        async with Session() as s:
            existing = (await s.execute(
                select(Memory.content).where(Memory.conversation_id == conversation_id,
                                             Memory.kind == "expense", Memory.active))).scalars().all()
        if any(m and m.group(1) == rhash for c in existing for m in [_HASH_RE.search(c)]):
            return {"ok": True, "imported": 0, "skipped_duplicates": 1,
                    "note": "This exact receipt was already imported."}

        entry = {"date": parsed["date"] or None, "merchant": parsed["merchant"] or None,
                 "total": parsed["total"], "currency": parsed["currency"],
                 "source": source_desc, "note": inp.note, "receipthash": rhash}
        async with Session() as s:
            s.add(Memory(conversation_id=conversation_id, kind="expense",
                         content=json.dumps(entry, ensure_ascii=False), source="receipt_import"))
            await s.commit()
        return {"ok": True, "imported": 1, "skipped_duplicates": 0,
                "expense": {k: v for k, v in entry.items() if v not in (None, "")},
                "note": "Logged as an expense memory (recall 'expenses' to review). "
                        "Informational only - not financial advice."}
    return f
