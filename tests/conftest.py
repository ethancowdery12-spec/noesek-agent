import sys, pathlib
# Full vendored upstream tree (v3): expose its top-level packages (agent,
# tools, hermes_cli, gateway, cron, plugins, ...) to adopted upstream tests.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Repo root FIRST so our own evals/ package beats the vendored evals/ that the
# editable install's .pth puts on sys.path; vendored tree appended LAST.
sys.path.insert(0, str(_ROOT))
sys.path.append(str(_ROOT / "vendor/hermes-agent"))
# Pin OUR evals package in sys.modules before collection; without this the
# vendored evals/ (regular package on the editable .pth path) gets cached first.
import evals, evals.injection_suite  # noqa: F401,E402

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
