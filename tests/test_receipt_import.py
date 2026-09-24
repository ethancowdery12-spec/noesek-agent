"""receipt_import tool (batch 4 tranche 7, item 87)."""
import sys
import types

import pytest
from sqlalchemy import select

from noesek.db import Memory, Session
from noesek.tools.receipt_import import ReceiptImportInput, parse_receipt, receipt_import_handler

RECEIPT = """CORNER GROCERY
123 MAIN ST
SPRINGFIELD
09/20/2026 6:42 PM
MILK 1QT            $3.49
SOURDOUGH           $4.25
EGGS DOZ            $5.19
SUBTOTAL           $12.93
TAX                 $1.07
TOTAL              $14.00
VISA ****1234      $14.00
"""


def test_parse_receipt_fields():
    p = parse_receipt(RECEIPT)
    assert p["merchant"] == "CORNER GROCERY"
    assert p["date"] == "09/20/2026"
    assert p["total"] == 14.00 and p["currency"] == "USD"


def test_parse_receipt_ignores_subtotal():
    p = parse_receipt(RECEIPT)
    assert p["total"] != 12.93


def test_parse_receipt_falls_back_to_largest_amount():
    p = parse_receipt("CAFE NORD\n2026-09-21\nCOFFEE 4.50\nTIP 1.00\nCARD 5.50\n")
    assert p["total"] == 5.50 and p["date"] == "2026-09-21"


@pytest.fixture()
def receipt_photo(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    (tmp_path / "receipt.jpg").write_bytes(b"\xff\xd8" + b"jpeg-bytes" * 20)
    return tmp_path


def _fake_ocr_module(text=RECEIPT, exc=None):
    mod = types.ModuleType("pytesseract")
    class TesseractNotFoundError(Exception):
        pass
    mod.TesseractNotFoundError = TesseractNotFoundError
    def image_to_string(_path):
        if exc is not None:
            raise exc
        return text
    mod.image_to_string = image_to_string
    return mod


@pytest.mark.asyncio
async def test_text_path_imports_and_dedupes(db):
    out = await receipt_import_handler(1)(ReceiptImportInput(text=RECEIPT, note="weekly shop"))
    assert out["ok"] and out["imported"] == 1
    e = out["expense"]
    assert e["merchant"] == "CORNER GROCERY" and e["total"] == 14.00 and e["note"] == "weekly shop"
    async with Session() as s:
        rows = (await s.execute(select(Memory).where(Memory.conversation_id == 1,
                                                     Memory.kind == "expense"))).scalars().all()
    assert len(rows) == 1 and rows[0].source == "receipt_import"
    assert "not financial advice" in out["note"]
    second = await receipt_import_handler(1)(ReceiptImportInput(text=RECEIPT))
    assert second["imported"] == 0 and second["skipped_duplicates"] == 1


@pytest.mark.asyncio
async def test_photo_path_uses_ocr(db, receipt_photo, monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", _fake_ocr_module())
    out = await receipt_import_handler(2)(ReceiptImportInput(file="receipt.jpg"))
    assert out["ok"] and out["imported"] == 1
    assert out["expense"]["merchant"] == "CORNER GROCERY" and out["expense"]["source"] == "receipt.jpg"


@pytest.mark.asyncio
async def test_missing_extra_and_missing_binary_fall_back(db, receipt_photo, monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", None)  # import raises ImportError
    out = await receipt_import_handler(3)(ReceiptImportInput(file="receipt.jpg"))
    assert out["ok"] is False and "paste the receipt text" in out["error"]
    fake = _fake_ocr_module(exc=_fake_ocr_module().TesseractNotFoundError("no binary"))
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    out = await receipt_import_handler(3)(ReceiptImportInput(file="receipt.jpg"))
    assert out["ok"] is False and "paste the receipt text" in out["error"]


@pytest.mark.asyncio
async def test_exactly_one_of_file_or_text(db):
    out = await receipt_import_handler(4)(ReceiptImportInput())
    assert out["ok"] is False
    out = await receipt_import_handler(4)(ReceiptImportInput(file="receipt.jpg", text=RECEIPT))
    assert out["ok"] is False


@pytest.mark.asyncio
async def test_unreadable_content_errors_cleanly(db):
    out = await receipt_import_handler(5)(ReceiptImportInput(text="\x00\x01\x02"))
    assert out["ok"] is False and "error" in out
