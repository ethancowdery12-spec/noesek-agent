"""ofx_import tool (batch 4 tranche 2, item 87)."""
import pytest
from sqlalchemy import select

from noesek.db import Memory
from noesek.db import Session
from noesek.tools.ofx_import import OfxImportInput, ofx_import_handler

# Small OFX 1.x (SGML) statement, written for this test - two debits, one credit.
OFX_SAMPLE = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STMTRS>
<CURDEF>USD
<BANKACCTFROM>
<BANKID>111000025
<ACCTID>9999
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260901000000
<DTEND>20260920000000
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260902120000
<TRNAMT>-42.50
<FITID>20260902001
<NAME>GROCER MARKET
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260905120000
<TRNAMT>-12.00
<FITID>20260905001
<NAME>COFFEE PLACE
<MEMO>latte
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260910120000
<TRNAMT>1500.00
<FITID>20260910001
<NAME>PAYROLL
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


@pytest.fixture()
def ofx_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    (tmp_path / "sept.ofx").write_text(OFX_SAMPLE, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_import_parses_and_stores_expenses(db, ofx_file):
    out = await ofx_import_handler(1)(OfxImportInput(file="sept.ofx"))
    assert out["ok"] and out["imported"] == 3 and out["skipped_duplicates"] == 0
    assert out["date_range"] == ["2026-09-02", "2026-09-10"]
    assert out["statement_total"] == 1445.50
    async with Session() as s:
        rows = (await s.execute(select(Memory).where(Memory.conversation_id == 1,
                                                     Memory.kind == "expense"))).scalars().all()
    assert len(rows) == 3
    body = " ".join(r.content for r in rows)
    assert "GROCER MARKET" in body and "PAYROLL" in body and "latte" in body
    assert "9999:20260902001" in body  # fitid carries account scope
    assert all(r.source == "ofx_import" for r in rows)
    assert "not financial advice" in out["note"]


@pytest.mark.asyncio
async def test_reimport_dedupes_by_fitid(db, ofx_file):
    first = await ofx_import_handler(1)(OfxImportInput(file="sept.ofx"))
    second = await ofx_import_handler(1)(OfxImportInput(file="sept.ofx"))
    assert first["imported"] == 3
    assert second["imported"] == 0 and second["skipped_duplicates"] == 3
    async with Session() as s:
        n = len((await s.execute(select(Memory).where(Memory.conversation_id == 1,
                                                      Memory.kind == "expense"))).scalars().all())
    assert n == 3


@pytest.mark.asyncio
async def test_missing_file_and_bad_name(db, ofx_file):
    from noesek.filestore import FileStoreError
    with pytest.raises(FileStoreError):
        await ofx_import_handler(1)(OfxImportInput(file="nope.ofx"))
    with pytest.raises(FileStoreError):
        await ofx_import_handler(1)(OfxImportInput(file="../secret.ofx"))


@pytest.mark.asyncio
async def test_non_statement_file_errors_cleanly(db, ofx_file):
    (ofx_file / "notes.ofx").write_text("just some text", encoding="utf-8")
    out = await ofx_import_handler(1)(OfxImportInput(file="notes.ofx"))
    assert out["ok"] is False and "error" in out
