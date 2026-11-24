"""Opt-in PostgreSQL execution test for migration 0076.

This deliberately does not fall back to SQLite: the migration uses PostgreSQL
DDL and must be checked on the project's disposable PostgreSQL fixture.
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.database.migrations import MIGRATIONS, run_migrations


TEST_DATABASE = "nms_test_migration_0075"
TEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
TEST_PORT = 55432
MIGRATION_ID = "20261123_0076_snmp_memory_source_metadata"
TABLES = ("latest_memory", "memory_statistics")
COLUMNS = {
    "memory_source": "VARCHAR(40)",
    "memory_semantic": "VARCHAR(100)",
    "memory_source_status": "VARCHAR(20)",
    "memory_source_error": "TEXT",
}


def _test_url():
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL migration test is opt-in")
    parsed = urlsplit(value)
    database = unquote(parsed.path.rsplit("/", 1)[-1])
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    if database != TEST_DATABASE or parsed.hostname not in TEST_HOSTS or parsed.port != TEST_PORT:
        pytest.fail("TEST_DATABASE_URL must target the verified disposable PostgreSQL instance")
    if not parsed.username or not parsed.password:
        pytest.fail("TEST_DATABASE_URL must use explicit test credentials")
    return value


def test_0076_executes_twice_preserves_rows_and_leaves_old_metadata_null():
    engine = create_engine(_test_url())
    try:
        with engine.connect() as connection:
            names = set(connection.execute(text(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = current_schema()"
            )).scalars())
            if names & {"devices", "latest_memory", "memory_statistics", "schema_migrations"}:
                pytest.fail("refusing pre-existing tables in disposable migration database")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE devices (id INTEGER PRIMARY KEY)"))
            connection.execute(text("""CREATE TABLE latest_memory (
                id SERIAL PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices(id),
                total_bytes DOUBLE PRECISION, used_bytes DOUBLE PRECISION,
                utilization_percent DOUBLE PRECISION, polled_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"""))
            connection.execute(text("""CREATE TABLE memory_statistics (
                id SERIAL PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices(id),
                total_bytes DOUBLE PRECISION, used_bytes DOUBLE PRECISION,
                utilization_percent DOUBLE PRECISION, created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL)"""))
            connection.execute(text("CREATE TABLE schema_migrations (migration_id VARCHAR(255) PRIMARY KEY, description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"))
            connection.execute(text("INSERT INTO devices VALUES (1)"))
            connection.execute(text("""INSERT INTO latest_memory
                (device_id,total_bytes,used_bytes,utilization_percent,polled_at,created_at,updated_at)
                VALUES (1,1000,400,40,'2026-01-01','2026-01-01','2026-01-01')"""))
            connection.execute(text("""INSERT INTO memory_statistics
                (device_id,total_bytes,used_bytes,utilization_percent,created_at,updated_at)
                VALUES (1,1000,400,40,'2026-01-01','2026-01-01')"""))
            for migration in MIGRATIONS:
                if migration.migration_id != MIGRATION_ID:
                    connection.execute(text("INSERT INTO schema_migrations VALUES (:id,:description,CURRENT_TIMESTAMP)"), {"id": migration.migration_id, "description": migration.description})

        assert run_migrations(engine) == [MIGRATION_ID]
        assert run_migrations(engine) == []
        inspector = inspect(engine)
        for table in TABLES:
            columns = {column["name"]: column for column in inspector.get_columns(table)}
            for name in COLUMNS:
                assert columns[name]["nullable"] is True
        with engine.connect() as connection:
            rows = connection.execute(text("""SELECT total_bytes, used_bytes, utilization_percent,
                polled_at, created_at, updated_at, memory_source, memory_semantic,
                memory_source_status, memory_source_error FROM latest_memory""")).one()
            assert tuple(rows[:6]) == (1000, 400, 40, rows[3], rows[4], rows[5])
            assert rows[6:] == (None, None, None, None)
    finally:
        with engine.begin() as connection:
            for table in ("latest_memory", "memory_statistics", "schema_migrations", "devices"):
                connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        engine.dispose()
