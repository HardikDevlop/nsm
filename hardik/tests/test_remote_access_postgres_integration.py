"""Opt-in PostgreSQL integration coverage for Remote Access.

Run with a disposable database, for example::

    TEST_DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/nms_test \
        pytest -q tests/test_remote_access_postgres_integration.py

This module deliberately does not fall back to DATABASE_URL.  It must never
connect to the application's normal database.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from urllib.parse import urlsplit

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.database.migrations import run_migrations
from backend.models import (
    Base,
    Device,
    RemoteAccessCredential,
    RemoteAccessSession,
    SSHHostKey,
    User,
)
from backend.services.remote_access.session_manager import SessionManager
from backend.services.remote_access.test_connection import TestConnectionRequest, TestConnectionService
from backend.services.remote_access_credentials import RemoteAccessCredentialError, RemoteAccessCredentialService


def _test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL integration tests are opt-in")
    parsed = urlsplit(value)
    database = parsed.path.rsplit("/", 1)[-1]
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL (postgresql or postgresql+psycopg)")
    if database != "nms_test" and not database.startswith("nms_test_"):
        pytest.fail("Refusing integration tests: TEST_DATABASE_URL database must be nms_test or nms_test_*")
    return value


class FakeAdapter:
    instances: list["FakeAdapter"] = []
    should_fail = False

    def __init__(self, host, port, username, secret, **kwargs):
        self.host, self.port, self.username, self.secret = host, port, username, secret
        self.connected = False
        self.closed = 0
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    def connect(self):
        if self.should_fail:
            raise ConnectionError("simulated adapter failure")
        self.connected = True
        return self

    def disconnect(self):
        self.closed += 1
        self.connected = False

    def is_alive(self):
        return self.connected and self.closed == 0


@pytest.fixture(scope="module")
def postgres_engine():
    url = _test_database_url()
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        # The application bootstrap order is intentional: mapped tables first,
        # then the project's idempotent migration registry.
        import backend.models  # noqa: F401
        Base.metadata.create_all(engine)
        run_migrations(engine)
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")
    yield engine
    engine.dispose()


@pytest.fixture
def postgres_db(postgres_engine):
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    db = factory()
    suffix = uuid.uuid4().hex[:12]
    # Keep every value unique across repeated runs against the same database.
    # The address is from TEST-NET-2 and is derived from the per-fixture UUID.
    device_octet = (uuid.UUID(suffix + "0" * 20).int % 254) + 1
    device_ip = f"198.51.100.{device_octet}"
    device_prefix = f"remote-access-{suffix}"
    user = User(
        name=f"Remote Access Test {suffix}",
        email=f"remote-access-{suffix}@example.invalid",
        password_hash="not-a-real-password",
        status="active",
    )
    device = Device(
        hostname=device_prefix,
        ip_address=device_ip,
        created_at=datetime.utcnow(),
    )
    db.add_all([user, device])
    db.commit()
    try:
        yield db, user, device
    finally:
        # Delete only rows owned by this fixture, in FK-safe order.  Include
        # every device with this fixture's hostname prefix because tests may
        # create a second device.  Never truncate or reset shared tables.
        db.rollback()
        owned_device_ids = list(db.scalars(
            select(Device.id).where(Device.hostname.like(f"{device_prefix}%"))
        ))
        if owned_device_ids:
            db.execute(delete(RemoteAccessSession).where(
                (RemoteAccessSession.user_id == user.id)
                | RemoteAccessSession.device_id.in_(owned_device_ids)
            ))
            db.execute(delete(SSHHostKey).where(SSHHostKey.device_id.in_(owned_device_ids)))
            db.execute(delete(RemoteAccessCredential).where(
                RemoteAccessCredential.device_id.in_(owned_device_ids)
            ))
            db.execute(delete(Device).where(Device.id.in_(owned_device_ids)))
        db.execute(delete(User).where(User.id == user.id))
        db.commit()
        db.close()


def _manager(db, *, failing=False):
    FakeAdapter.instances.clear()
    FakeAdapter.should_fail = failing
    return SessionManager(db, adapter_factories={"ssh": FakeAdapter, "telnet": FakeAdapter})


def _fixture_username(device):
    """Return a unique, fixture-owned username derived from the device."""
    return f"nms-{device.hostname.rsplit('-', 1)[-1]}"


def test_postgres_remote_access_lifecycle_and_persistence(postgres_db):
    db, user, device = postgres_db
    validation = TestConnectionService(db, adapter_factories={"ssh": FakeAdapter})
    result = validation.test_connection(TestConnectionRequest(
        device_id=device.id, protocol="ssh", username=_fixture_username(device), secret="temporary-secret",
        remember_credential=True,
    ))
    assert result["success"] is True
    assert result["credential_id"] is not None
    db.commit()
    credential_id = result["credential_id"]
    assert db.get(RemoteAccessCredential, credential_id).is_verified is True

    manager = _manager(db)
    session = manager.create_session(device_id=device.id, user_id=user.id, protocol="ssh", credential_id=credential_id)
    assert session.status == "connected"
    db.commit()
    persisted = db.scalar(select(RemoteAccessSession).where(RemoteAccessSession.id == session.id))
    assert persisted.status == "connected"

    manager.disconnect_session(session.session_uuid)
    db.commit()
    assert db.get(RemoteAccessSession, session.id).status == "disconnected"
    assert FakeAdapter.instances[-1].closed == 1


def test_postgres_remote_access_failed_connection_persists_failed(postgres_db):
    db, user, device = postgres_db
    manager = _manager(db, failing=True)
    with pytest.raises(ConnectionError):
        manager.create_session(device_id=device.id, user_id=user.id, protocol="ssh", username=_fixture_username(device), secret="secret")
    db.commit()
    row = db.scalar(select(RemoteAccessSession).where(RemoteAccessSession.user_id == user.id))
    assert row.status == "failed"
    assert FakeAdapter.instances[-1].closed == 1


def test_postgres_constraints_mismatch_and_trusted_host_key(postgres_db):
    db, user, device = postgres_db
    credentials = RemoteAccessCredentialService(db)
    credential = credentials.create(device_id=device.id, protocol="ssh", username=_fixture_username(device), secret="secret")
    credentials.mark_verified(credential.id)
    db.commit()
    with pytest.raises(RemoteAccessCredentialError) as duplicate:
        credentials.create(device_id=device.id, protocol="ssh", username="duplicate", secret="secret")
    assert duplicate.value.code == "CREDENTIAL_EXISTS"
    # The service's savepoint catches the database violation and exposes it as
    # a domain error.  Its cause proves PostgreSQL rejected the duplicate on
    # the real (device_id, protocol) unique constraint.
    assert isinstance(duplicate.value.__cause__, IntegrityError)
    assert duplicate.value.__cause__.orig.diag.constraint_name == "uq_remote_access_credential_device_protocol"
    assert duplicate.value.__cause__.orig.diag.message_detail is not None
    assert "(device_id, protocol)" in duplicate.value.__cause__.orig.diag.message_detail
    # The savepoint rollback must not poison the caller's session: subsequent
    # SQL and writes in this test continue without an explicit session rollback.
    assert db.get(RemoteAccessCredential, credential.id).is_verified is True

    other_suffix = uuid.uuid4().hex[:12]
    other_octet = (uuid.UUID(other_suffix + "0" * 20).int % 254) + 1
    other = Device(
        hostname=f"{device.hostname}-other-{other_suffix}",
        ip_address=f"203.0.113.{other_octet}",
        created_at=datetime.utcnow(),
    )
    db.add(other)
    db.flush()
    manager = _manager(db)
    with pytest.raises(Exception) as mismatch:
        manager.create_session(device_id=other.id, user_id=user.id, protocol="ssh", credential_id=credential.id)
    assert getattr(mismatch.value, "code", None) == "CREDENTIAL_NOT_FOUND"

    host_key = SSHHostKey(device_id=device.id, host=device.ip_address, port=22, key_type="ssh-ed25519",
                          public_host_key="key", fingerprint="SHA256:test", status="TRUSTED")
    db.add(host_key)
    db.commit()
    manager.create_session(device_id=device.id, user_id=user.id, protocol="ssh", credential_id=credential.id)
    assert FakeAdapter.instances[-1].kwargs["expected_host_key_fingerprint"] == "SHA256:test"
    db.rollback()


def test_postgres_application_rollback_removes_uncommitted_session(postgres_db):
    db, user, device = postgres_db
    manager = _manager(db)
    session = manager.create_session(device_id=device.id, user_id=user.id, protocol="telnet", username=_fixture_username(device), secret="secret")
    session_id = session.id
    db.rollback()
    assert db.get(RemoteAccessSession, session_id) is None
    manager.disconnect_session(session.session_uuid)
    assert FakeAdapter.instances[-1].closed == 1
