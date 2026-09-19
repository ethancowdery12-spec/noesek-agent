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
    kind: Mapped[str] = mapped_column(String(32), default="note")  # note | fact | preference | episode
    content: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Provenance + invalidate-not-overwrite (v2 stage D)
    source: Mapped[str] = mapped_column(String(64), default="conversation")
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

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


engine = create_async_engine(settings.database_url, poolclass=NullPool)
Session = async_sessionmaker(engine, expire_on_commit=False)

_FTS_DDL = "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(memory_id UNINDEXED, content)"

async def init_db(eng: AsyncEngine | None = None):
    e = eng or engine
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try: await conn.execute(text(_FTS_DDL))
        except Exception: pass  # SQLite build without FTS5: keyword fallback stays in place

# Columns added after v0.1, applied to pre-existing databases by migrate().
_COLUMN_UPGRADES = {
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

async def record_trace(conversation_id: int, event: str, detail: dict | None = None):
    """Best-effort audit write; tracing must never break a user turn."""
    try:
        async with Session() as s:
            s.add(Trace(conversation_id=conversation_id, event=event, detail=detail or {})); await s.commit()
    except Exception:
        pass
