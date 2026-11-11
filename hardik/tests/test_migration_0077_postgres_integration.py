"""Opt-in PostgreSQL verification for migration 0077 and lifecycle transitions."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.database import migrate_0077
from backend.windows_monitoring.collection_lifecycle import (
    CollectionLifecycleError, CollectionState, expire_collection, fail_collection,
    finalize_collection, get_active_collection, mark_collecting, reserve_collection,
    supersede_collection,
)

TEST_DATABASE = "nms_test_migration_0075"
TEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
TEST_PORT = 55432
FORBIDDEN_USERS = {"postgres", "production", "nms", "nms_prod", "nms_production"}


def _test_url():
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL integration is opt-in")
    parsed = urlsplit(value)
    database = unquote(parsed.path.rsplit("/", 1)[-1])
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    if database != TEST_DATABASE or parsed.hostname not in TEST_HOSTS or parsed.port != TEST_PORT:
        pytest.fail("TEST_DATABASE_URL must target the verified disposable PostgreSQL instance")
    if parsed.username in {None, "", *FORBIDDEN_USERS} or parsed.password in {None, ""}:
        pytest.fail("TEST_DATABASE_URL must use explicit non-production test credentials")
    app_url = os.getenv("DATABASE_URL", "").strip()
    if app_url:
        app = urlsplit(app_url)
        if value == app_url or (parsed.username == app.username and parsed.password == app.password):
            pytest.fail("TEST_DATABASE_URL must not reuse application credentials")
    return value


def _assert_empty(connection):
    names = set(connection.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = current_schema()")).scalars())
    forbidden = {"sites", "devices", "schema_migrations", migrate_0077.TABLE}
    if names & forbidden:
        raise RuntimeError(f"refusing pre-existing test tables: {', '.join(sorted(names & forbidden))}")


@pytest.fixture(scope="module")
def engine():
    value = _test_url()
    target = create_engine(value, pool_pre_ping=True)
    owned = False
    try:
        with target.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != TEST_DATABASE:
                pytest.fail("connected database identity mismatch")
            _assert_empty(connection)
        with target.begin() as connection:
            connection.execute(text("CREATE TABLE sites (id INTEGER PRIMARY KEY)"))
            connection.execute(text("""
                CREATE TABLE devices (
                    id INTEGER PRIMARY KEY,
                    site_id INTEGER REFERENCES sites(id),
                    hostname VARCHAR(160) NOT NULL,
                    ip_address VARCHAR(45) NOT NULL UNIQUE,
                    mac_address VARCHAR(32),
                    vendor_id INTEGER,
                    device_type_id INTEGER,
                    serial_number VARCHAR(120),
                    model VARCHAR(120),
                    firmware_version VARCHAR(120),
                    status VARCHAR(30) NOT NULL,
                    monitoring_status BOOLEAN NOT NULL,
                    last_seen TIMESTAMP,
                    last_icmp_attempt_at TIMESTAMP,
                    last_icmp_status VARCHAR(20),
                    created_at TIMESTAMP NOT NULL,
                    uptime_seconds INTEGER NOT NULL,
                    downtime_seconds INTEGER NOT NULL,
                    last_status_change TIMESTAMP,
                    deleted_at TIMESTAMP,
                    topology_metadata JSON
                )
            """))
            connection.execute(text("CREATE TABLE schema_migrations (migration_id VARCHAR(255) PRIMARY KEY, description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"))
            connection.execute(text("INSERT INTO sites VALUES (1), (2)"))
            connection.execute(text("""
                INSERT INTO devices
                    (id, site_id, hostname, ip_address, status, monitoring_status, created_at,
                     uptime_seconds, downtime_seconds)
                VALUES
                    (101, 1, 'test-device-101', '192.0.2.101', 'unknown', TRUE, CURRENT_TIMESTAMP, 0, 0),
                    (202, 2, 'test-device-202', '192.0.2.202', 'unknown', TRUE, CURRENT_TIMESTAMP, 0, 0)
            """))
        owned = True
        yield target
    except OperationalError as exc:
        pytest.skip(f"verified disposable PostgreSQL instance unavailable: {exc}")
    finally:
        if owned:
            with target.begin() as connection:
                connection.execute(text(f"DROP TABLE IF EXISTS {migrate_0077.TABLE}"))
                connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
                connection.execute(text("DROP TABLE IF EXISTS devices"))
                connection.execute(text("DROP TABLE IF EXISTS sites"))
        target.dispose()


@pytest.fixture(autouse=True)
def clean(engine):
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {migrate_0077.TABLE}"))
        connection.execute(text("DELETE FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0077.MIGRATION_ID})
    yield


def test_apply_schema_constraints_rerun_and_tracking(engine):
    migrate_0077.apply_0077(engine)
    inspector = inspect(engine)
    assert migrate_0077.TABLE in inspector.get_table_names()
    assert inspector.get_pk_constraint(migrate_0077.TABLE)["constrained_columns"] == ["id"]
    assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints(migrate_0077.TABLE)} >= {("collection_id",)}
    fks = {(fk["constrained_columns"][0], fk["referred_table"], (fk.get("options") or {}).get("ondelete")) for fk in inspector.get_foreign_keys(migrate_0077.TABLE)}
    assert {("device_id", "devices", "CASCADE"), ("site_id", "sites", "CASCADE")} <= fks
    with pytest.raises(RuntimeError, match="already applied"):
        migrate_0077.apply_0077(engine)


def test_lifecycle_transitions_binding_and_terminal_rejection(engine):
    migrate_0077.apply_0077(engine)
    with Session(engine) as db:
        row = reserve_collection(db, 101, site_id=1, now=datetime.now(timezone.utc))
        db.commit()
        assert get_active_collection(db, 101) is not None
        mark_collecting(db, row.collection_id); db.commit()
        finalize_collection(db, row.collection_id); db.commit()
        assert get_active_collection(db, 101) is None
        with pytest.raises(CollectionLifecycleError):
            finalize_collection(db, row.collection_id)
        with pytest.raises(CollectionLifecycleError):
            reserve_collection(db, 101, site_id=2)


def test_supersession_failure_expiry_and_duplicate_collection(engine):
    migrate_0077.apply_0077(engine)
    with Session(engine) as db:
        first = reserve_collection(db, 101, site_id=1, collection_id=uuid4()); db.commit()
        supersede_collection(db, first.collection_id); db.commit()
        with pytest.raises(CollectionLifecycleError): mark_collecting(db, first.collection_id)
        failed = reserve_collection(db, 101, site_id=1, collection_id=uuid4()); db.commit()
        fail_collection(db, failed.collection_id); db.commit()
        expired = reserve_collection(db, 101, site_id=1, collection_id=uuid4(), ttl_seconds=1, now=datetime.now(timezone.utc) - timedelta(minutes=2)); db.commit()
        expire_collection(db, expired.collection_id, now=datetime.now(timezone.utc)); db.commit()
        with pytest.raises(IntegrityError):
            reserve_collection(db, 101, site_id=1, collection_id=first.collection_id)
            db.flush()
        db.rollback()


def test_migration_rollback_after_validation_failure(engine, monkeypatch):
    def fail(_connection): raise RuntimeError("injected lifecycle validation failure")
    monkeypatch.setattr(migrate_0077, "_validate", fail)
    with pytest.raises(RuntimeError, match="injected"):
        migrate_0077.apply_0077(engine)
    assert migrate_0077.TABLE not in inspect(engine).get_table_names()
