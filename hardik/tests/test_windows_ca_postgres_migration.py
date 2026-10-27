"""Host-only validation for Windows CA migrations 0066 and 0067.

This test is intentionally opt-in by requiring TEST_DATABASE_URL.  It never
falls back to the application's DATABASE_URL and it does not clean the test
database, so results remain available for inspection after pytest exits.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.database.migrations import MIGRATIONS, run_migrations
from backend.database.session import Base


EXPECTED_TABLES = {"windows_ca_bundles", "windows_device_ca_assignments"}
EXPECTED_MIGRATIONS = {
    "20261026_0066_windows_ca_bundle_foundation",
    "20261026_0067_windows_ca_bundle_index_reconciliation",
}


def _required_test_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.fail("TEST_DATABASE_URL is required; refusing to use DATABASE_URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    database = parsed.path.rsplit("/", 1)[-1]
    if database != "nms_test_windows_ca":
        pytest.fail("TEST_DATABASE_URL must target database nms_test_windows_ca")
    if database == "postgres":
        pytest.fail("Refusing to connect to the application database postgres")
    return value


def test_windows_ca_migrations_on_dedicated_database() -> None:
    engine = create_engine(_required_test_url(), pool_pre_ping=True)

    # These imports register every mapped table/FK on the shared metadata
    # before DDL compilation; importing the application does not occur.
    import backend.models  # noqa: F401
    import backend.windows_monitoring.models  # noqa: F401

    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        before = set(connection.scalars(text("SELECT migration_id FROM schema_migrations"))) if inspect(engine).has_table("schema_migrations") else set()
    first_applied = set(run_migrations(engine))
    second_applied = set(run_migrations(engine))

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES <= tables
    assert EXPECTED_MIGRATIONS <= before | first_applied
    assert second_applied == set(), "migration runner is not idempotent"

    with engine.connect() as connection:
        tracked = set(connection.scalars(text("SELECT migration_id FROM schema_migrations")))
        assert EXPECTED_MIGRATIONS <= tracked
        assert connection.scalar(text("SELECT current_database()")) == "nms_test_windows_ca"

    bundle_indexes = {item["name"] for item in inspector.get_indexes("windows_ca_bundles")}
    assignment_indexes = {item["name"] for item in inspector.get_indexes("windows_device_ca_assignments")}
    assert {
        "ix_windows_ca_bundles_site_status",
        "ix_windows_ca_bundles_site_id",
    } <= bundle_indexes
    assert {
        "uq_windows_device_ca_active",
        "ix_windows_device_ca_assignments_bundle",
        "ix_windows_device_ca_assignments_device_id",
    } <= assignment_indexes

    bundle_uniques = {item["name"] for item in inspector.get_unique_constraints("windows_ca_bundles")}
    assert "uq_windows_ca_bundles_site_fingerprint" in bundle_uniques

    bundle_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("windows_ca_bundles")}
    assignment_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("windows_device_ca_assignments")}
    assert {"sites", "users"} <= bundle_fks
    assert {"devices", "users", "windows_ca_bundles"} <= assignment_fks
    assert {
        ("site_id", "sha256_fingerprint"),
    } <= {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("windows_ca_bundles")
    }
    active_index = next(
        item for item in inspector.get_indexes("windows_device_ca_assignments")
        if item["name"] == "uq_windows_device_ca_active"
    )
    assert active_index["unique"] is True
    assert active_index["column_names"] == ["device_id"]
    assert "unassigned_at IS NULL" in str(active_index["dialect_options"].get("postgresql_where", ""))

    checks = {
        check["name"]
        for table in EXPECTED_TABLES
        for check in inspector.get_check_constraints(table)
    }
    assert {"ck_windows_ca_bundles_status", "ck_windows_ca_bundles_trust_type"} <= checks
    engine.dispose()
