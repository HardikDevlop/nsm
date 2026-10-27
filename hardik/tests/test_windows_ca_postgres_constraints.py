"""Transactional PostgreSQL behavior checks for the Windows CA schema.

Run only after the schema migration test has been approved and executed on the
dedicated test database.  No application startup or migration is performed.
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _required_test_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.fail("TEST_DATABASE_URL is required; refusing to use DATABASE_URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    if parsed.path.rsplit("/", 1)[-1] != "nms_test_windows_ca":
        pytest.fail("TEST_DATABASE_URL must target database nms_test_windows_ca")
    return value


@pytest.fixture
def db():
    engine = create_engine(_required_test_url(), pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    suffix = uuid.uuid4().hex[:12]
    try:
        organization_id = connection.scalar(
            text("INSERT INTO organizations (name, created_at) VALUES (:name, CURRENT_TIMESTAMP) RETURNING id"),
            {"name": f"CA behavior org {suffix}"},
        )
        site_id = connection.scalar(
            text("INSERT INTO sites (organization_id, name) VALUES (:org, :name) RETURNING id"),
            {"org": organization_id, "name": f"CA behavior site {suffix}"},
        )
        device_id = connection.scalar(
            text("""
                INSERT INTO devices
                    (site_id, hostname, ip_address, status, monitoring_status,
                     created_at, uptime_seconds, downtime_seconds)
                VALUES
                    (:site, :hostname, :ip, 'unknown', TRUE,
                     CURRENT_TIMESTAMP, 0, 0)
                RETURNING id
            """),
            {"site": site_id, "hostname": f"ca-behavior-{suffix}", "ip": f"198.51.100.{int(suffix[:2], 16) % 254 + 1}"},
        )
        user_id = connection.scalar(
            text("""
                INSERT INTO users
                    (uuid, name, email, password_hash, status,
                     failed_login_attempts, max_concurrent_sessions, created_at)
                VALUES
                    (:uuid, :name, :email, 'synthetic-test-hash', 'active',
                     0, 1, CURRENT_TIMESTAMP)
                RETURNING id
            """),
            {
                "uuid": str(uuid.uuid4()),
                "name": f"CA behavior user {suffix}",
                "email": f"ca-behavior-{suffix}@example.invalid",
            },
        )
        yield connection, site_id, device_id, user_id, suffix
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def _bundle(db, *, site_id, user_id, suffix, **overrides):
    values = {
        "site_id": site_id,
        "name": f"Synthetic CA {suffix}",
        "storage_key": f"synthetic/{suffix}.pem",
        "fingerprint": f"fingerprint-{suffix}",
        "content": f"content-{suffix}",
        "trust_type": "enterprise_ca",
        "status": "active",
        "created_by": user_id,
        "revoked_by": None,
        "overrides": overrides,
    }
    values.update(overrides)
    return db[0].scalar(text("""
        INSERT INTO windows_ca_bundles
            (site_id, name, storage_key, sha256_fingerprint, content_sha256,
             trust_type, status, created_by, created_at, updated_at, revoked_by)
        VALUES
            (:site_id, :name, :storage_key, :fingerprint, :content,
             :trust_type, :status, :created_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :revoked_by)
        RETURNING id
    """), values)


def _assignment(db, *, device_id, bundle_id, user_id, unassigned_at=None):
    return db[0].scalar(text("""
        INSERT INTO windows_device_ca_assignments
            (device_id, ca_bundle_id, assigned_by, assigned_at, unassigned_at)
        VALUES (:device_id, :bundle_id, :user_id, CURRENT_TIMESTAMP, :unassigned_at)
        RETURNING id
    """), {"device_id": device_id, "bundle_id": bundle_id, "user_id": user_id, "unassigned_at": unassigned_at})


def test_valid_bundle_and_assignment_insert(db):
    connection, site_id, device_id, user_id, suffix = db
    bundle_id = _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix)
    assignment_id = _assignment(db, device_id=device_id, bundle_id=bundle_id, user_id=user_id)
    assert bundle_id and assignment_id


@pytest.mark.parametrize("field", ["storage_key", "fingerprint"])
def test_duplicate_bundle_keys_are_rejected(db, field):
    connection, site_id, _device_id, user_id, suffix = db
    _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix)
    with pytest.raises(IntegrityError), connection.begin_nested():
        _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix, **{field: f"synthetic/{suffix}.pem" if field == "storage_key" else f"fingerprint-{suffix}"})


def test_multiple_active_assignments_are_rejected_but_history_is_allowed(db):
    connection, site_id, device_id, user_id, suffix = db
    first = _bundle(db, site_id=site_id, user_id=user_id, suffix=f"{suffix}-one")
    second = _bundle(db, site_id=site_id, user_id=user_id, suffix=f"{suffix}-two")
    _assignment(db, device_id=device_id, bundle_id=first, user_id=user_id, unassigned_at="2026-01-01")
    _assignment(db, device_id=device_id, bundle_id=second, user_id=user_id)
    with pytest.raises(IntegrityError), connection.begin_nested():
        _assignment(db, device_id=device_id, bundle_id=first, user_id=user_id)


@pytest.mark.parametrize("field,value", [("status", "bogus"), ("trust_type", "bogus")])
def test_invalid_enum_like_values_are_rejected(db, field, value):
    connection, site_id, _device_id, user_id, suffix = db
    with pytest.raises(IntegrityError), connection.begin_nested():
        _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix, **{field: value})


def test_invalid_foreign_keys_are_rejected(db):
    connection, site_id, _device_id, user_id, suffix = db
    with pytest.raises(IntegrityError), connection.begin_nested():
        _bundle(db, site_id=999999999, user_id=user_id, suffix=suffix)


def test_device_delete_cascades_assignments(db):
    connection, site_id, device_id, user_id, suffix = db
    bundle_id = _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix)
    _assignment(db, device_id=device_id, bundle_id=bundle_id, user_id=user_id)
    connection.execute(text("DELETE FROM devices WHERE id = :id"), {"id": device_id})
    assert connection.scalar(text("SELECT COUNT(*) FROM windows_device_ca_assignments WHERE device_id = :id"), {"id": device_id}) == 0


def test_bundle_delete_is_restricted_while_assigned(db):
    connection, site_id, device_id, user_id, suffix = db
    bundle_id = _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix)
    _assignment(db, device_id=device_id, bundle_id=bundle_id, user_id=user_id)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text("DELETE FROM windows_ca_bundles WHERE id = :id"), {"id": bundle_id})


def test_nullable_and_required_columns(db):
    connection, site_id, _device_id, user_id, suffix = db
    optional_id = _bundle(db, site_id=site_id, user_id=user_id, suffix=suffix, description=None)
    assert optional_id
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text("""
            INSERT INTO windows_ca_bundles
                (site_id, name, storage_key, sha256_fingerprint, content_sha256,
                 trust_type, status, created_at, updated_at)
            VALUES (:site, NULL, :storage, :fingerprint, :content,
                    'enterprise_ca', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {"site": site_id, "storage": f"required/{suffix}", "fingerprint": f"required-{suffix}", "content": f"required-{suffix}"})
