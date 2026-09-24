from datetime import datetime, timezone, timedelta
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .config import settings

class Base(DeclarativeBase): pass

def now(): return datetime.now(timezone.utc)

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    external_user_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_override: Mapped[str | None] = mapped_column(String(128), nullable=True)  # per-chat model (multi-model layer)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="note")  # note | fact | preference | episode | handoff | lesson
    content: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Provenance + invalidate-not-overwrite (v2 stage D)
    source: Mapped[str] = mapped_column(String(64), default="conversation")
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class BrowserStateRow(Base):
    """Singleton row: Fernet-encrypted Playwright storage_state (item 56)."""
    __tablename__ = "browser_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    blob: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class BrowserAuditRow(Base):
    """Append-only audit of browser-session operations (item 56).

    action/domain/detail only - cookie names and values are never recorded.
    """
    __tablename__ = "browser_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    action: Mapped[str] = mapped_column(String(32))
    domain: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(String(255), default="")

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    last_error: Mapped[str] = mapped_column(Text, default="")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    # Lease binding (v2 stage B): originating spine turn + canonical arguments
    # recorded at creation and re-verified at execution (tamper check).
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    canonical_args: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Trace(Base):
    """Append-only per-turn event log: the audit trail of what the agent did and why."""
    __tablename__ = "traces"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class Compaction(Base):
    """A persisted, visible context-compaction transition (v2 stage D)."""
    __tablename__ = "compactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    removed_count: Mapped[int] = mapped_column(Integer)
    budget_chars: Mapped[int] = mapped_column(Integer)
    oldest_dropped_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    newest_dropped_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class SteeringNote(Base):
    """Live steering: a user note injected into an in-flight turn (v2 stage H)."""
    __tablename__ = "steering_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TurnEvent(Base):
    """Durable turn spine: one typed, ordered event in one agent turn.

    Write-ahead kinds (see core.turn_spine) are flushed strictly before the
    side effect they announce; (turn_id, seq) is unique so postmortems replay
    deterministically.
    """
    __tablename__ = "turn_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    turn_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    __table_args__ = (UniqueConstraint("turn_id", "seq", name="uq_turn_events_turn_seq"),)


def _translate_database_url(url: str) -> tuple[str, dict]:
    """Translate libpq-style query params into asyncpg connect_args.

    Neon (and other Postgres providers) hand out URLs carrying
    ?sslmode=require&channel_binding=require. SQLAlchemy passes unknown query
    params straight to asyncpg's connect(), which rejects them - this shipped
    as a startup crash (Sep 22). sslmode maps to an explicit SSL context:
    require = encrypt without verification, verify-ca/verify-full verify.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    if not url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        return url, {}
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = (params.pop("sslmode", "") or "").lower()
    params.pop("channel_binding", None)  # libpq-only; asyncpg rejects it
    connect_args: dict = {}
    if sslmode in ("require", "verify-ca", "verify-full"):
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        if sslmode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
        elif sslmode == "verify-ca":
            ctx.check_hostname = False
        connect_args["ssl"] = ctx
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))
    return clean, connect_args


def _engine_kwargs(url: str, connect_args: dict) -> dict:
    """Pool selection (lane 1). Postgres gets a bounded QueuePool so one
    instance never exceeds pool_size + max_overflow connections; sqlite keeps
    NullPool (file DB, pooling buys nothing). A Neon *pooled* endpoint
    (-pooler host, pgBouncer transaction mode) additionally needs asyncpg's
    prepared-statement cache off - statements are per-connection there."""
    if not url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        return {"poolclass": NullPool}
    from urllib.parse import urlsplit
    if "-pooler" in urlsplit(url).netloc:
        connect_args = {**connect_args, "statement_cache_size": 0}
    return {"pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout_seconds,
            "pool_recycle": settings.db_pool_recycle_seconds,
            "pool_pre_ping": True,
            "connect_args": connect_args}


_db_url, _db_connect_args = _translate_database_url(settings.database_url)
engine = create_async_engine(_db_url, **_engine_kwargs(_db_url, _db_connect_args))
Session = async_sessionmaker(engine, expire_on_commit=False)

_FTS_DDL = "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(memory_id UNINDEXED, content)"

async def init_db(eng: AsyncEngine | None = None):
    e = eng or engine
    try:
        async with e.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        raise RuntimeError(
            "Database init failed. Check NOESEK_DATABASE_URL: Postgres needs the "
            "postgresql+asyncpg:// prefix and the .[postgres] extra installed; any "
            "Neon/libpq query params (sslmode, channel_binding) are handled "
            "automatically. Original error: " + str(exc)[:300]
        ) from exc
    # FTS5 is SQLite-only, and it MUST run in its own transaction: on Postgres a
    # failed statement aborts the whole transaction, so the old single-block
    # version silently rolled back create_all (the Sep 22 "relation tasks does
    # not exist" boot crash on fresh Neon - init_db returned 'successfully'
    # with zero tables created).
    if e.dialect.name == "sqlite":
        try:
            async with e.begin() as conn:
                await conn.execute(text(_FTS_DDL))
        except Exception: pass  # SQLite build without FTS5: keyword fallback stays in place

# Columns added after v0.1, applied to pre-existing databases by migrate().
_COLUMN_UPGRADES = {
    "conversations": {
        "title": "VARCHAR(200)",
        "model_override": "VARCHAR(128)",
    },
    "memories": {
        "source": "VARCHAR(64) NOT NULL DEFAULT 'conversation'",
        "superseded_by": "INTEGER",
    },
    "tasks": {
        "result": "JSON",
        "last_error": "TEXT NOT NULL DEFAULT ''",
        "max_attempts": "INTEGER NOT NULL DEFAULT 3",
        "finished_at": "TIMESTAMP",
    },
    "approvals": {
        "expires_at": "TIMESTAMP",
        "decided_at": "TIMESTAMP",
        "turn_id": "VARCHAR(36)",
        "canonical_args": "TEXT NOT NULL DEFAULT ''",
    },
}

async def migrate(eng: AsyncEngine | None = None):
    """Idempotent in-place schema upgrade for databases created by older releases."""
    e = eng or engine
    async with e.begin() as conn:
        def _apply(sync_conn):
            insp = inspect(sync_conn)
            tables = set(insp.get_table_names())
            for table, cols in _COLUMN_UPGRADES.items():
                if table not in tables: continue
                existing = {c["name"] for c in insp.get_columns(table)}
                for col, ddl in cols.items():
                    if col not in existing:
                        sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        await conn.run_sync(_apply)

async def get_or_create_conversation(session: AsyncSession, channel: str, external_user_id: str) -> Conversation:
    row = (await session.execute(select(Conversation).where(Conversation.channel==channel, Conversation.external_user_id==external_user_id))).scalar_one_or_none()
    if row: return row
    row = Conversation(channel=channel, external_user_id=external_user_id); session.add(row); await session.flush(); return row

async def pool_conversation_ids(session: AsyncSession, conversation_id: int) -> list[int] | None:
    """Memory-pool scope for this conversation (item 68, multi-user seam).
    None = deployment-wide pool (single-user default, unchanged behavior).
    In 'user' mode: all conversations sharing this conversation's
    (channel, external_user_id) form the pool."""
    from .config import settings as _s
    if _s.memory_pool_mode != "user":
        return None
    row = (await session.execute(select(Conversation.channel, Conversation.external_user_id)
                                 .where(Conversation.id == conversation_id))).first()
    if not row:
        return [conversation_id]
    ids = (await session.execute(select(Conversation.id).where(
        Conversation.channel == row[0], Conversation.external_user_id == row[1]))).scalars().all()
    return list(ids)

async def record_trace(conversation_id: int, event: str, detail: dict | None = None):
    """Best-effort audit write; tracing must never break a user turn."""
    try:
        async with Session() as s:
            s.add(Trace(conversation_id=conversation_id, event=event, detail=detail or {})); await s.commit()
    except Exception:
        pass
