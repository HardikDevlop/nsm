"""Opt-in PostgreSQL integration tests for migration 0076.

This module is deliberately stricter than ordinary integration tests. It only
accepts the disposable loopback PostgreSQL target used for migration testing,
never falls back to application configuration, and never runs migrations via
application startup.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.database import migrate_0076


TEST_DATABASE = "nms_test_migration_0075"
TEST_HOSTS = {"127.0.0.1", "localhost", "::1"}
TEST_PORT = 55432
PRODUCTION_USERS = {"postgres", "production", "nms", "nms_prod", "nms_production"}


def _required_test_url() -> str:
    """Validate the target entirely in memory before any connection attempt."""
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL integration is opt-in")

    parsed = urlsplit(value)
    database = unquote(parsed.path.rsplit("/", 1)[-1])
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    if database != TEST_DATABASE:
        pytest.fail(f"TEST_DATABASE_URL must target database {TEST_DATABASE}")
    if parsed.hostname not in TEST_HOSTS:
        pytest.fail("TEST_DATABASE_URL must target a loopback host")
    if parsed.port != TEST_PORT:
        pytest.fail(f"TEST_DATABASE_URL must use disposable test port {TEST_PORT}")
    if parsed.username in {None, "", *PRODUCTION_USERS}:
        pytest.fail("TEST_DATABASE_URL must use an explicit non-production test user")
    if parsed.password in {None, ""}:
        pytest.fail("TEST_DATABASE_URL must include an explicit test password")

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
        connection.execute(text("INSERT INTO sites (id) VALUES (1), (2)"))
        connection.execute(text("INSERT INTO devices (id) VALUES (101), (202)"))


def _assert_target_is_empty(connection) -> None:
    existing = set(connection.execute(text(
        "SELECT tablename FROM pg_catalog.pg_tables "
        "WHERE schemaname = current_schema()"
    )).scalars())
    forbidden = {"sites", "devices", "schema_migrations", migrate_0076.CHALLENGE_TABLE}
    overlap = sorted(existing & forbidden)
    if overlap:
        raise RuntimeError(f"refusing test setup; pre-existing tables found: {', '.join(overlap)}")


def _remove_migration_objects(engine: Engine) -> None:
    """Remove only the challenge table and tracking row owned by this test."""
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {migrate_0076.CHALLENGE_TABLE}"))
        connection.execute(
            text("DELETE FROM schema_migrations WHERE migration_id = :id"),
            {"id": migrate_0076.MIGRATION_ID},
        )


def _ensure_parent_records(engine: Engine) -> None:
    """Restore only the parent rows owned by this disposable fixture."""
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO sites (id) VALUES (1), (2) ON CONFLICT (id) DO NOTHING"))
        connection.execute(text("INSERT INTO devices (id) VALUES (101), (202) ON CONFLICT (id) DO NOTHING"))


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    url = _required_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    setup_owned = False
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != TEST_DATABASE:
                pytest.fail("connected database is not the dedicated migration test database")
            _assert_target_is_empty(connection)
        _create_parent_schema(engine)
        setup_owned = True
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"dedicated PostgreSQL test instance is unavailable: {exc}")
    except BaseException:
        engine.dispose()
        raise
    try:
        yield engine
    finally:
        if setup_owned:
            with engine.begin() as connection:
                connection.execute(text(f"DROP TABLE IF EXISTS {migrate_0076.CHALLENGE_TABLE}"))
                connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
                connection.execute(text("DROP TABLE IF EXISTS devices"))
                connection.execute(text("DROP TABLE IF EXISTS sites"))
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_migration_objects(postgres_engine: Engine):
    _ensure_parent_records(postgres_engine)
    _remove_migration_objects(postgres_engine)
    yield
    _remove_migration_objects(postgres_engine)


def _insert_challenge(engine: Engine, *, challenge_id=None, device_id=101, collection_id=None):
    challenge_id = challenge_id or uuid4()
    collection_id = collection_id or uuid4()
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(text(f"""
            INSERT INTO {migrate_0076.CHALLENGE_TABLE}
                (challenge_id, device_id, site_id, collection_id, purpose, nonce_hash,
                 issued_at, expires_at)
            VALUES (:challenge_id, :device_id, :site_id, :collection_id, :purpose, :nonce_hash,
                    :issued_at, :expires_at)
        """), {
            "challenge_id": challenge_id,
            "device_id": device_id,
            "site_id": 1,
            "collection_id": collection_id,
            "purpose": "windows_helper_evidence",
            "nonce_hash": "a" * 64,
            "issued_at": now,
            "expires_at": now + timedelta(minutes=1),
        })
    return challenge_id, collection_id


def test_apply_reflects_complete_schema_and_tracks_migration(postgres_engine: Engine):
    migrate_0076.apply_0076(postgres_engine)
    inspector = inspect(postgres_engine)
    assert migrate_0076.CHALLENGE_TABLE in inspector.get_table_names()
    columns = {item["name"]: item for item in inspector.get_columns(migrate_0076.CHALLENGE_TABLE)}
    assert columns["id"]["type"].__class__.__name__ == "INTEGER"
    assert columns["id"]["default"] and "nextval(" in columns["id"]["default"].lower()
    assert columns["challenge_id"]["type"].__class__.__name__ == "UUID"
    assert columns["collection_id"]["type"].__class__.__name__ == "UUID"
    assert columns["purpose"]["type"].length == 64
    assert columns["nonce_hash"]["type"].length == 64
    assert columns["issued_at"]["type"].timezone is True
    assert columns["expires_at"]["type"].timezone is True
    assert columns["consumed_at"]["type"].timezone is True
    assert columns["cancelled_at"]["type"].timezone is True
    assert inspector.get_pk_constraint(migrate_0076.CHALLENGE_TABLE)["constrained_columns"] == ["id"]
    uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(migrate_0076.CHALLENGE_TABLE)}
    assert {("challenge_id",), ("device_id", "collection_id")} <= uniques

    foreign_keys = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete"))
        for fk in inspector.get_foreign_keys(migrate_0076.CHALLENGE_TABLE)
    }
    assert (("device_id",), "devices", ("id",), "CASCADE") in foreign_keys
    assert (("site_id",), "sites", ("id",), "CASCADE") in foreign_keys

    indexes = {item["name"]: item for item in inspector.get_indexes(migrate_0076.CHALLENGE_TABLE)}
    assert indexes["ix_windows_helper_challenges_device_expiry"]["column_names"] == ["device_id", "expires_at"]
    assert indexes["ix_windows_helper_challenges_collection"]["column_names"] == ["collection_id"]
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0076.MIGRATION_ID}) == 1


def test_safe_rerun_rejection(postgres_engine: Engine):
    migrate_0076.apply_0076(postgres_engine)
    with pytest.raises(RuntimeError, match="already applied"):
        migrate_0076.apply_0076(postgres_engine)


def test_injected_failure_rolls_back_table_and_tracking(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    def fail_after_ddl(_connection):
        raise RuntimeError("injected validator failure")

    monkeypatch.setattr(migrate_0076, "_validate_created_schema", fail_after_ddl)
    with pytest.raises(RuntimeError, match="injected validator failure"):
        migrate_0076.apply_0076(postgres_engine)
    assert migrate_0076.CHALLENGE_TABLE not in inspect(postgres_engine).get_table_names()
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = :id"), {"id": migrate_0076.MIGRATION_ID}) == 0


def test_invalid_parent_schema_is_rejected_without_commit(postgres_engine: Engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("ALTER TABLE schema_migrations RENAME TO schema_migrations_invalid"))
            connection.execute(text("CREATE TABLE schema_migrations (migration_id INTEGER PRIMARY KEY)"))
            with pytest.raises(RuntimeError, match="schema_migrations"):
                migrate_0076._validate_parents(connection)
        finally:
            transaction.rollback()


def test_duplicate_challenge_and_device_collection_are_rejected(postgres_engine: Engine):
    migrate_0076.apply_0076(postgres_engine)
    challenge_id, collection_id = _insert_challenge(postgres_engine)
    with pytest.raises(IntegrityError):
        _insert_challenge(postgres_engine, challenge_id=challenge_id, collection_id=uuid4())
    with pytest.raises(IntegrityError):
        _insert_challenge(postgres_engine, collection_id=collection_id)


def test_foreign_keys_and_cascade_rules_are_enforced(postgres_engine: Engine):
    migrate_0076.apply_0076(postgres_engine)
    _insert_challenge(postgres_engine, device_id=101)
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM devices WHERE id = 101"))
        assert connection.scalar(text(f"SELECT COUNT(*) FROM {migrate_0076.CHALLENGE_TABLE}")) == 0
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(text(f"""
                INSERT INTO {migrate_0076.CHALLENGE_TABLE}
                    (challenge_id, device_id, site_id, collection_id, purpose, nonce_hash, issued_at, expires_at)
                VALUES (:challenge_id, 999, 1, :collection_id, 'windows_helper_evidence', :nonce_hash, :issued_at, :expires_at)
            """), {"challenge_id": uuid4(), "collection_id": uuid4(), "nonce_hash": "b" * 64, "issued_at": datetime.now(timezone.utc), "expires_at": datetime.now(timezone.utc) + timedelta(minutes=1)})


def test_atomic_conditional_consumption_allows_only_one_concurrent_claim(postgres_engine: Engine):
    migrate_0076.apply_0076(postgres_engine)
    challenge_id, _ = _insert_challenge(postgres_engine)
    first = postgres_engine.connect()
    second = postgres_engine.connect()
    first_transaction = None
    second_transaction = None
    try:
        first_transaction = first.begin()
        second_transaction = second.begin()
        second.execute(text("SET LOCAL lock_timeout = '2s'"))
        second.execute(text("SET LOCAL statement_timeout = '5s'"))
        sql = text(f"""
            UPDATE {migrate_0076.CHALLENGE_TABLE}
            SET consumed_at = :now
            WHERE challenge_id = :challenge_id
              AND consumed_at IS NULL
              AND cancelled_at IS NULL
              AND expires_at > :now
        """)
        now = datetime.now(timezone.utc)
        assert first.execute(sql, {"challenge_id": challenge_id, "now": now}).rowcount == 1
        first_transaction.commit()
        assert second.execute(sql, {"challenge_id": challenge_id, "now": now}).rowcount == 0
        second_transaction.commit()
    finally:
        if first_transaction is not None and first_transaction.is_active:
            first_transaction.rollback()
        if second_transaction is not None and second_transaction.is_active:
            second_transaction.rollback()
        first.close()
        second.close()


def test_overlapping_consumption_commit_and_rollback_paths(postgres_engine: Engine):
    """Verify a blocked claimant resolves correctly after commit or rollback."""
    migrate_0076.apply_0076(postgres_engine)
    claim_sql = text(f"""
        UPDATE {migrate_0076.CHALLENGE_TABLE}
        SET consumed_at = :now
        WHERE challenge_id = :challenge_id
          AND consumed_at IS NULL
          AND cancelled_at IS NULL
          AND expires_at > :now
    """)

    def run_blocked_claim(challenge_id, started, result):
        connection = postgres_engine.connect()
        transaction = None
        try:
            transaction = connection.begin()
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            started.set()
            now = datetime.now(timezone.utc)
            result.append(connection.execute(claim_sql, {"challenge_id": challenge_id, "now": now}).rowcount)
            transaction.commit()
        except BaseException as exc:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            result.append(exc)
        finally:
            connection.close()

    # Commit path: B must begin its update while A still owns the row lock.
    challenge_id, _ = _insert_challenge(postgres_engine)
    first = postgres_engine.connect()
    first_transaction = first.begin()
    try:
        now = datetime.now(timezone.utc)
        assert first.execute(claim_sql, {"challenge_id": challenge_id, "now": now}).rowcount == 1
        b_started = threading.Event()
        b_result = []
        b_thread = threading.Thread(target=run_blocked_claim, args=(challenge_id, b_started, b_result), daemon=True)
        b_thread.start()
        assert b_started.wait(timeout=2), "Transaction B did not reach its claim attempt"
        first_transaction.commit()
        b_thread.join(timeout=5)
        assert not b_thread.is_alive(), "Transaction B did not finish within the bounded timeout"
        assert b_result == [0]
        with postgres_engine.connect() as connection:
            assert connection.scalar(text(f"SELECT COUNT(*) FROM {migrate_0076.CHALLENGE_TABLE} WHERE challenge_id = :id AND consumed_at IS NOT NULL"), {"id": challenge_id}) == 1
    finally:
        if first_transaction.is_active:
            first_transaction.rollback()
        first.close()

    # Rollback path: B must become the sole successful claimant after A rolls back.
    challenge_id, _ = _insert_challenge(postgres_engine)
    first = postgres_engine.connect()
    first_transaction = first.begin()
    try:
        now = datetime.now(timezone.utc)
        assert first.execute(claim_sql, {"challenge_id": challenge_id, "now": now}).rowcount == 1
        b_started = threading.Event()
        b_result = []
        b_thread = threading.Thread(target=run_blocked_claim, args=(challenge_id, b_started, b_result), daemon=True)
        b_thread.start()
        assert b_started.wait(timeout=2), "Transaction B did not reach its rollback-path claim attempt"
        first_transaction.rollback()
        b_thread.join(timeout=5)
        assert not b_thread.is_alive(), "Transaction B did not finish within the bounded rollback timeout"
        assert b_result == [1]
        with postgres_engine.connect() as connection:
            assert connection.scalar(text(f"SELECT COUNT(*) FROM {migrate_0076.CHALLENGE_TABLE} WHERE challenge_id = :id AND consumed_at IS NOT NULL"), {"id": challenge_id}) == 1
    finally:
        if first_transaction.is_active:
            first_transaction.rollback()
        first.close()


def test_no_unrelated_tables_are_created(postgres_engine: Engine):
    before = set(inspect(postgres_engine).get_table_names())
    migrate_0076.apply_0076(postgres_engine)
    after = set(inspect(postgres_engine).get_table_names())
    assert after - before <= {migrate_0076.CHALLENGE_TABLE}
