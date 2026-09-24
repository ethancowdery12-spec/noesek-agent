"""Regression: Neon URLs carry libpq params asyncpg rejects (Sep 22 startup crash)."""
import ssl

from noesek.db import _translate_database_url


def test_neon_sslmode_require_translated():
    url, args = _translate_database_url(
        "postgresql+asyncpg://user:pw@ep-x.us-east-2.aws.neon.tech/noesek?sslmode=require&channel_binding=require")
    assert "sslmode" not in url and "channel_binding" not in url
    assert url.startswith("postgresql+asyncpg://")
    ctx = args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE and ctx.check_hostname is False


def test_sslmode_verify_full_keeps_verification():
    _, args = _translate_database_url("postgresql+asyncpg://u:p@h/db?sslmode=verify-full")
    assert args["ssl"].verify_mode == ssl.CERT_REQUIRED and args["ssl"].check_hostname is True


def test_sslmode_disable_no_ssl():
    url, args = _translate_database_url("postgresql+asyncpg://u:p@h/db?sslmode=disable")
    assert "sslmode" not in url and "ssl" not in args


def test_postgres_without_sslmode_untouched():
    url, args = _translate_database_url("postgresql+asyncpg://u:p@h/db")
    assert url == "postgresql+asyncpg://u:p@h/db" and args == {}


def test_other_query_params_preserved():
    url, args = _translate_database_url("postgresql+asyncpg://u:p@h/db?sslmode=require&application_name=noesek")
    assert "application_name=noesek" in url and "ssl" in args


def test_sqlite_untouched():
    url, args = _translate_database_url("sqlite+aiosqlite:///./noesek.db")
    assert url == "sqlite+aiosqlite:///./noesek.db" and args == {}

def test_bare_postgres_scheme_promoted_to_asyncpg():
    # Render's provisioned DATABASE_URL is bare postgres:// (Sep 24 staging
    # boot crash: ModuleNotFoundError psycopg2 at db.py engine creation).
    url, args = _translate_database_url("postgres://u:p@dpg-x-a/dbname")
    assert url == "postgresql+asyncpg://u:p@dpg-x-a/dbname" and args == {}


def test_bare_postgresql_scheme_promoted_to_asyncpg():
    url, _ = _translate_database_url("postgresql://u:p@h/db")
    assert url.startswith("postgresql+asyncpg://")


def test_bare_scheme_with_sslmode_promoted_and_translated():
    url, args = _translate_database_url("postgres://u:p@h/db?sslmode=require")
    assert url.startswith("postgresql+asyncpg://") and "sslmode" not in url
    assert isinstance(args["ssl"], ssl.SSLContext)
