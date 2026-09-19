import os, tempfile
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from noesek.db import migrate

async def test_migrate_adds_missing_columns_to_old_schema():
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    eng = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with eng.begin() as conn:
        await conn.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY, conversation_id INTEGER, title VARCHAR(256), status VARCHAR(24), payload JSON, run_after DATETIME, attempts INTEGER, created_at DATETIME)"))
        await conn.execute(text("CREATE TABLE approvals (id INTEGER PRIMARY KEY, conversation_id INTEGER, tool_name VARCHAR(128), arguments JSON, rationale TEXT, status VARCHAR(24), created_at DATETIME)"))
    await migrate(eng)
    async with eng.connect() as conn:
        cols = await conn.run_sync(lambda sc: {c["name"] for c in inspect(sc).get_columns("tasks")})
        acols = await conn.run_sync(lambda sc: {c["name"] for c in inspect(sc).get_columns("approvals")})
    assert {"result", "last_error", "max_attempts", "finished_at"} <= cols
    assert {"expires_at", "decided_at"} <= acols
    # Idempotent: a second run must not fail.
    await migrate(eng)
    await eng.dispose()
