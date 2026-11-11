"""Opt-in PostgreSQL reflection tests for migration 0075.

This module is deliberately stricter than the application's integration tests.
It will only use a disposable PostgreSQL instance bound to 127.0.0.1:55432
and database nms_test_migration_0075.  It never falls back to DATABASE_URL,
and all URL checks happen before SQLAlchemy is allowed to connect.

Example (the disposable PostgreSQL instance must already be running)::

    TEST_DATABASE_URL=postgresql+psycopg://test_user:test_password@127.0.0.1:55432/nms_test_migration_0075 \
        pytest -q tests/test_migration_0075_postgres_integration.py
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from backend.database import migrate_0075


TEST_DATABASE = "nms_test_migration_0075"
TEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
TEST_PORT = 55432


def _required_test_url() -> str:
    """Validate the target without opening a database connection."""
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL integration is opt-in")

    parsed = urlsplit(value)
    database = unquote(parsed.path.rsplit("/", 1)[-1])
    host = parsed.hostname
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    if database != TEST_DATABASE:
        pytest.fail(f"TEST_DATABASE_URL must target database {TEST_DATABASE}")
    if database == "postgres":
        pytest.fail("refusing the postgres database")
    if host not in TEST_HOSTS:
        pytest.fail("TEST_DATABASE_URL must target a loopback host")
    if parsed.port != TEST_PORT:
        pytest.fail(f"TEST_DATABASE_URL must use disposable test port {TEST_PORT}")
    if parsed.username in {None, "", "postgres"}:
        pytest.fail("TEST_DATABASE_URL must use an explicit non-production test user")

    # Do not allow an application credential to be reused accidentally.  The
    # comparison is performed in memory and neither URL is printed.
    application_url = os.getenv("DATABASE_URL", "").strip()
    if application_url:
        application = urlsplit(application_url)
        if value == application_url or (
            parsed.username == application.username
            and parsed.password == application.password
            and parsed.username is not None
        ):
            pytest.fail("TEST_DATABASE_URL must use credentials distinct from DATABASE_URL")
    return value


def _create_parent_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sites (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE devices (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE schema_migrations ("
            "migration_id VARCHAR(255) PRIMARY KEY, "
            "description VARCHAR(255) NOT NULL, "
            "applied_at TIMESTAMP NOT NULL)"
        ))


def _remove_migration_objects(engine: Engine) -> None:
    """Remove only objects owned by this dedicated test database."""
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS windows_helper_submissions"))
        connection.execute(text("DROP TABLE IF EXISTS windows_helper_credentials"))
        connection.execute(text("DELETE FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0075.MIGRATION_ID})


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    # URL validation is intentionally before create_engine and before any
    # connection attempt.  create_engine itself is lazy; the first connect is
    # guarded and unavailable instances are skipped.
    url = _required_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != TEST_DATABASE:
                pytest.fail("connected database is not the dedicated migration test database")
        _create_parent_schema(engine)
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"dedicated PostgreSQL test instance is unavailable: {exc}")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS windows_helper_submissions"))
            connection.execute(text("DROP TABLE IF EXISTS windows_helper_credentials"))
            connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
            connection.execute(text("DROP TABLE IF EXISTS devices"))
            connection.execute(text("DROP TABLE IF EXISTS sites"))
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_migration_objects(postgres_engine: Engine):
    _remove_migration_objects(postgres_engine)
    yield
    _remove_migration_objects(postgres_engine)


def test_apply_reflects_complete_helper_schema_and_tracks_migration(postgres_engine: Engine):
    migrate_0075.apply_0075(postgres_engine)
    inspector = inspect(postgres_engine)
    assert {"devices", "sites", "schema_migrations", *migrate_0075.HELPER_TABLES} <= set(inspector.get_table_names())

    columns = {
        table: {item["name"]: item for item in inspector.get_columns(table)}
        for table in migrate_0075.HELPER_TABLES
    }
    assert isinstance(columns["windows_helper_credentials"]["id"]["type"], migrate_0075.Integer)
    assert columns["windows_helper_credentials"]["id"]["default"] and "nextval(" in columns["windows_helper_credentials"]["id"]["default"].lower()
    assert columns["windows_helper_credentials"]["token_prefix"]["type"].length == 16
    assert columns["windows_helper_credentials"]["token_hash"]["type"].length == 64
    assert columns["windows_helper_submissions"]["collection_id"]["type"].__class__.__name__ == "UUID"
    assert columns["windows_helper_submissions"]["evidence"]["type"].__class__.__name__ == "JSON"
    assert columns["windows_helper_submissions"]["collected_at"]["type"].timezone is True
    assert columns["windows_helper_submissions"]["expires_at"]["type"].timezone is False

    for table in migrate_0075.HELPER_TABLES:
        assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]
    assert {tuple(u["column_names"]) for u in inspector.get_unique_constraints("windows_helper_credentials")} >= {("token_prefix",)}
    assert {tuple(u["column_names"]) for u in inspector.get_unique_constraints("windows_helper_submissions")} >= {("collection_id",)}

    foreign_keys = {
        (table, tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete"))
        for table in migrate_0075.HELPER_TABLES
        for fk in inspector.get_foreign_keys(table)
    }
    assert ("windows_helper_credentials", ("device_id",), "devices", ("id",), "CASCADE") in foreign_keys
    assert ("windows_helper_credentials", ("site_id",), "sites", ("id",), "CASCADE") in foreign_keys
    assert ("windows_helper_submissions", ("device_id",), "devices", ("id",), "CASCADE") in foreign_keys

    expected_indexes = {
        "ix_windows_helper_credentials_device_active": (["device_id", "is_active"], False),
        "ix_windows_helper_credentials_site_id": (["site_id"], False),
        "ix_windows_helper_credentials_expires_at": (["expires_at"], False),
        "ix_windows_helper_submissions_device_id": (["device_id"], False),
        "ix_windows_helper_submission_expiry": (["expires_at"], False),
    }
    indexes = {index["name"]: index for table in migrate_0075.HELPER_TABLES for index in inspector.get_indexes(table)}
    for name, (index_columns, unique) in expected_indexes.items():
        assert indexes[name]["column_names"] == index_columns
        assert bool(indexes[name]["unique"]) is unique
        assert (indexes[name].get("dialect_options") or {}).get("postgresql_where") is None

    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0075.MIGRATION_ID}) == 1


def test_already_applied_validation_is_safe_and_does_not_duplicate(postgres_engine: Engine):
    migrate_0075.apply_0075(postgres_engine)
    with pytest.raises(RuntimeError, match="already applied"):
        migrate_0075.apply_0075(postgres_engine)
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0075.MIGRATION_ID}) == 1


def test_injected_validation_failure_rolls_back_schema_and_tracking(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    def fail_after_ddl(_connection):
        raise RuntimeError("injected validator failure")

    monkeypatch.setattr(migrate_0075, "_validate_created_schema", fail_after_ddl)
    with pytest.raises(RuntimeError, match="injected validator failure"):
        migrate_0075.apply_0075(postgres_engine)
    inspector = inspect(postgres_engine)
    assert not (set(migrate_0075.HELPER_TABLES) & set(inspector.get_table_names()))
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0075.MIGRATION_ID}) == 0


def test_no_unrelated_tables_are_created(postgres_engine: Engine):
    before = set(inspect(postgres_engine).get_table_names())
    migrate_0075.apply_0075(postgres_engine)
    after = set(inspect(postgres_engine).get_table_names())
    assert after - before <= set(migrate_0075.HELPER_TABLES)
