import asyncio, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from sqlalchemy import text
import uvicorn
from . import __version__
from .channels import outbound
from .channels.whatsapp import router
from .channels.slack_router import router as slack_router
from .channels.telegram_router import router as telegram_router
from .config import settings
from .core.metrics import render_prometheus, snapshot
from .db import engine, init_db, migrate
from .jobs import task_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(); await migrate()
    from .core.skill_seed import seed_kwp_skills
    seeded = await seed_kwp_skills()
    if seeded: logging.getLogger("noesek").info("kwp skill seed: %d skills added", seeded)
    # Item 89: AST code-intel startup index behind the flag. Best-effort: a
    # failure here must never block boot. The log line doubles as the staging
    # validation signal (deploy shells are not always available).
    from .config import settings as _settings
    if _settings.code_intel_enabled:
        try:
            from .core.code_intel import default_root, index_root
            _root = _settings.code_intel_root or default_root()
            _stats = index_root(_root, _settings.code_intel_db)
            logging.getLogger("noesek").info(
                "code_intel index: %d files, %d symbols, %d edges (%d changed, root=%s)",
                _stats["files"], _stats["symbols"], _stats["edges"], _stats["changed"], _root)
        except Exception:
            logging.getLogger("noesek").exception("code_intel startup index failed (non-fatal)")
    stop = asyncio.Event()
    worker = asyncio.create_task(task_worker(stop, deliver=outbound.deliver))
    yield
    stop.set(); await worker

app = FastAPI(title="Noesek Agent", version=__version__, lifespan=lifespan)
app.include_router(router)
app.include_router(slack_router)
app.include_router(telegram_router)

@app.get("/healthz")
async def healthz():
    return {"ok": True, "version": __version__}

@app.get("/readyz")
async def readyz():
    try:
        async with engine.connect() as conn: await conn.execute(text("SELECT 1"))
    except Exception as e:
        return Response(f'{{"ok": false, "error": "{type(e).__name__}"}}', status_code=503, media_type="application/json")
    return {"ok": True}

@app.get("/metrics")
async def metrics():
    if not settings.metrics_enabled: return Response("metrics disabled", status_code=404)
    return Response(render_prometheus(), media_type="text/plain; version=0.0.4")

def run():
    logging.basicConfig(level=settings.log_level)
    uvicorn.run("noesek.main:app", host="0.0.0.0", port=8000)
