"""fit_import tool (batch 4 tranche 3, item 87)."""
import pytest
from sqlalchemy import select

from noesek.db import Memory, Session
from noesek.tools.fit_import import FitImportInput, fit_import_handler


class _Field:
    def __init__(self, name, value):
        self.name, self.value = name, value


class _Rec:
    def __init__(self, fields):
        self.fields = fields


class _FakeFit:
    def __init__(self, raw):
        pass

    def get_messages(self, kind):
        import datetime
        if kind != "session":
            return []
        yield _Rec([_Field("sport", "running"),
                    _Field("start_time", datetime.datetime(2026, 9, 20, 7, 30)),
                    _Field("total_elapsed_time", 1530.0),
                    _Field("total_distance", 5000.0),
                    _Field("total_calories", 320),
                    _Field("avg_heart_rate", 148)])


@pytest.fixture()
def fit_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    (tmp_path / "run.fit").write_bytes(b"\x0e\x10" + b"fit-bytes" * 10)
    return tmp_path


@pytest.fixture()
def real_parser(monkeypatch):
    import fitparse
    monkeypatch.setattr(fitparse, "FitFile", _FakeFit)
    # the tool imports the symbol locally; patch the module attribute it will get
    monkeypatch.setattr("fitparse.FitFile", _FakeFit)
    return fitparse


@pytest.mark.asyncio
async def test_import_maps_session_to_workout(db, fit_file, real_parser):
    out = await fit_import_handler(1)(FitImportInput(file="run.fit", note="morning run"))
    assert out["ok"] and out["imported"] == 1
    w = out["workout"]
    assert w["activity"] == "running" and w["date"] == "2026-09-20"
    assert w["duration_min"] == 25.5 and w["distance_km"] == 5.0 and w["avg_hr"] == 148
    async with Session() as s:
        rows = (await s.execute(select(Memory).where(Memory.conversation_id == 1,
                                                     Memory.kind == "workout"))).scalars().all()
    assert len(rows) == 1 and "morning run" in rows[0].content and rows[0].source == "fit_import"
    assert "not medical advice" in out["note"]


@pytest.mark.asyncio
async def test_reimport_same_file_dedupes(db, fit_file, real_parser):
    first = await fit_import_handler(1)(FitImportInput(file="run.fit"))
    second = await fit_import_handler(1)(FitImportInput(file="run.fit"))
    assert first["imported"] == 1
    assert second["imported"] == 0 and second["skipped_duplicates"] == 1
    async with Session() as s:
        n = len((await s.execute(select(Memory).where(Memory.conversation_id == 1,
                                                      Memory.kind == "workout"))).scalars().all())
    assert n == 1


@pytest.mark.asyncio
async def test_missing_file_and_bad_name(db, fit_file):
    from noesek.filestore import FileStoreError
    with pytest.raises(FileStoreError):
        await fit_import_handler(1)(FitImportInput(file="nope.fit"))
    with pytest.raises(FileStoreError):
        await fit_import_handler(1)(FitImportInput(file="../secret.fit"))


@pytest.mark.asyncio
async def test_garbage_file_errors_cleanly(db, fit_file):
    # real parser (no monkeypatch) must fail gracefully on non-FIT bytes
    out = await fit_import_handler(1)(FitImportInput(file="run.fit"))
    assert out["ok"] is False and "error" in out
