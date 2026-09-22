"""Fresh-Postgres schema boot regression (Sep 22 boot crash).

init_db ran Base.metadata.create_all and the SQLite-only FTS5 DDL in ONE
transaction. On Postgres the FTS statement fails, aborting the transaction, so
the following COMMIT silently rolled back every CREATE TABLE - init_db
returned 'successfully' with zero tables, and startup then died on
"relation tasks does not exist" (exit 3). This test boots init_db against a
real empty Postgres and asserts every ORM table exists. It runs only when
NOESEK_TEST_PG_URL is set (the eval-gate postgres-boot CI job); skipped locally.
"""
import os

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

PG_URL = os.environ.get("NOESEK_TEST_PG_URL", "")


@pytest.mark.skipif(not PG_URL, reason="NOESEK_TEST_PG_URL not set (CI Postgres job only)")
@pytest.mark.asyncio
async def test_init_db_creates_full_schema_on_empty_postgres():
    from noesek.db import Base, init_db

    eng = create_async_engine(PG_URL)
    try:
        await init_db(eng)
        async with eng.begin() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        missing = set(Base.metadata.tables) - tables
        assert not missing, f"tables missing after init_db on fresh Postgres: {sorted(missing)}"
    finally:
        await eng.dispose()
