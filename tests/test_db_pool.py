"""Pool selection + echo adapter (lane 1 scale hardening)."""
import pytest

from noesek.config import settings
from noesek.core.llm import EchoLLM, configured_llm
from noesek.db import _engine_kwargs
from sqlalchemy.pool import NullPool


def test_sqlite_keeps_nullpool():
    kw = _engine_kwargs("sqlite+aiosqlite:///./x.db", {})
    assert kw.get("poolclass") is NullPool
    assert "pool_size" not in kw


def test_postgres_gets_bounded_queuepool():
    kw = _engine_kwargs("postgresql+asyncpg://u:p@ep-x.us-east-2.aws.neon.tech/db", {})
    assert kw.get("poolclass") is None  # QueuePool is the default
    assert kw["pool_size"] == settings.db_pool_size
    assert kw["max_overflow"] == settings.db_max_overflow
    assert kw["pool_pre_ping"] is True
    assert kw["pool_recycle"] == settings.db_pool_recycle_seconds


def test_pooler_host_disables_statement_cache():
    kw = _engine_kwargs("postgresql+asyncpg://u:p@ep-x-pooler.us-east-2.aws.neon.tech/db", {})
    assert kw["connect_args"]["statement_cache_size"] == 0


def test_direct_host_keeps_statement_cache():
    kw = _engine_kwargs("postgresql+asyncpg://u:p@ep-x.us-east-2.aws.neon.tech/db", {})
    assert "statement_cache_size" not in kw.get("connect_args", {})


@pytest.mark.asyncio
async def test_echo_llm_offline_reply():
    llm = EchoLLM()
    reply = await llm.complete(
        [{"role": "user", "content": "hello load test"}], [])
    assert reply.content == "[echo] hello load test"
    assert reply.tool_calls == []


def test_echo_provider_selected_by_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "echo")
    assert isinstance(configured_llm(), EchoLLM)
