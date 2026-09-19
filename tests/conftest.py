import os, tempfile
os.environ.setdefault("NOESEK_DATABASE_URL", "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(prefix="noesek-test-"), "test.db"))

import pytest_asyncio

@pytest_asyncio.fixture
async def db():
    from noesek.db import Base, engine, init_db
    await init_db()
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
