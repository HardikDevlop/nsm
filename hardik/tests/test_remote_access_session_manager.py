from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models import Base, Device, RemoteAccessCredential, RemoteAccessSession
from backend.services.remote_access_credentials import RemoteAccessCredentialService
from backend.services.remote_access.session_manager import SessionManager
from backend.services.remote_access.test_connection import TestConnectionRequest, TestConnectionService


class Adapter:
    instances = []
    def __init__(self, host, port, username, secret, **kwargs):
        self.host, self.port, self.username, self.secret = host, port, username, secret
        self.connected = False
        self.closed = 0
        self.__class__.instances.append(self)
    def connect(self): self.connected = True; return self
    def is_alive(self): return self.connected and self.closed == 0
    def disconnect(self): self.closed += 1; self.connected = False


class FailingAdapter(Adapter):
    def connect(self): raise ConnectionError("private-secret")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Device.__table__, RemoteAccessCredential.__table__, RemoteAccessSession.__table__])
    with Session(engine) as session:
        session.add(Device(id=1, hostname="edge-1", ip_address="192.0.2.10", created_at=datetime.utcnow()))
        session.commit()
        yield session


def manager(db, factory=Adapter, **kwargs):
    Adapter.instances.clear()
    return SessionManager(db, adapter_factories={"ssh": factory, "telnet": factory}, **kwargs)


def test_ssh_telnet_custom_ports_unique_and_same_adapter(db):
    m = manager(db)
    ssh = m.create_session(device_id=1, user_id=7, protocol="ssh", username="u", secret="ssh-secret", port=2201)
    telnet = m.create_session(device_id=1, user_id=8, protocol="telnet", username="u", secret="telnet-secret", port=2323)
    assert ssh.status == telnet.status == "connected"
    assert ssh.port == 2201 and telnet.port == 2323 and ssh.session_uuid != telnet.session_uuid
    assert m.get_session(ssh.session_uuid).adapter is Adapter.instances[0]
    assert m.list_active_sessions(user_id=7) == [ssh]
    assert m.is_alive(ssh.session_uuid)
    assert all(secret not in repr(row) for row, secret in [(ssh, "ssh-secret"), (telnet, "telnet-secret")])


def test_saved_verified_credential_and_ownership(db):
    credential = RemoteAccessCredentialService(db).create(device_id=1, protocol="ssh", username="saved", secret="hidden")
    RemoteAccessCredentialService(db).mark_verified(credential.id)
    session = manager(db).create_session(device_id=1, user_id=42, protocol="ssh", credential_id=credential.id)
    assert session.credential_id == credential.id and session.user_id == 42
    assert "hidden" not in repr(session)


def test_same_user_cannot_create_second_protocol_session_for_same_device(db):
    m = manager(db)
    active = m.create_session(device_id=1, user_id=42, protocol="ssh", username="u", secret="s")

    with pytest.raises(Exception) as duplicate:
        m.create_session(device_id=1, user_id=42, protocol="telnet", username="u", secret="s")

    assert getattr(duplicate.value, "code", None) == "DEVICE_ALREADY_CONNECTED"
    assert getattr(duplicate.value, "protocol", None) == "ssh"
    assert db.query(RemoteAccessSession).count() == 1
    assert len(Adapter.instances) == 1
    assert m.get_session(active.session_uuid).adapter.is_alive()


def test_connect_can_remember_credential_after_successful_handshake(db):
    m = manager(db)

    session = m.create_session(
        device_id=1,
        user_id=42,
        protocol="ssh",
        username="remembered-user",
        secret="remembered-secret",
        remember_credential=True,
    )
    credential = db.query(RemoteAccessCredential).one()

    assert session.credential_id == credential.id
    assert credential.is_verified is True
    assert credential.username == "remembered-user"
    assert Adapter.instances[0].connected is True


def test_saved_credential_device_mismatch_is_reported_before_adapter_connect(db, caplog):
    db.add(Device(id=2, hostname="edge-2", ip_address="192.0.2.11", created_at=datetime.utcnow()))
    db.commit()
    credential = RemoteAccessCredentialService(db).create(device_id=1, protocol="ssh", username="saved", secret="hidden")
    RemoteAccessCredentialService(db).mark_verified(credential.id)

    with caplog.at_level("INFO"):
        with pytest.raises(Exception) as raised:
            manager(db).create_session(device_id=2, user_id=42, protocol="ssh", credential_id=credential.id)

    assert getattr(raised.value, "code", None) == "CREDENTIAL_NOT_FOUND"
    assert "adapter connection failed" not in caplog.text.lower()
    assert "credential_device_matches=False" in caplog.text


def test_touch_disconnect_is_idempotent_and_updates_activity(db):
    m = manager(db)
    session = m.create_session(device_id=1, user_id=1, protocol="ssh", username="u", secret="s")
    before = session.last_activity_at
    m.touch(session.session_uuid)
    assert session.last_activity_at >= before
    m.disconnect_session(session.session_uuid, reason="user request")
    assert session.status == "disconnected" and session.ended_at is not None
    assert Adapter.instances[0].closed == 1
    with Session(db.get_bind()) as history_db:
        persisted = history_db.query(RemoteAccessSession).filter_by(session_uuid=session.session_uuid).one()
        assert persisted.status == "disconnected"
        assert persisted.ended_at is not None
    m.disconnect_session(session.session_uuid, reason="again")
    assert m.list_active_sessions() == []


def test_failed_connection_cleans_adapter_and_persists_failure(db):
    m = manager(db, FailingAdapter)
    with pytest.raises(ConnectionError):
        m.create_session(device_id=1, user_id=1, protocol="ssh", username="u", secret="private-secret")
    row = db.query(RemoteAccessSession).one()
    assert row.status == "failed" and row.ended_at is not None
    assert Adapter.instances[0].closed == 1 and "private-secret" not in repr(row)


def test_test_connection_success_uses_equivalent_session_adapter(db):
    factory = Adapter
    validation = TestConnectionService(db, adapter_factories={"ssh": factory, "telnet": factory})
    result = validation.test_connection(TestConnectionRequest(
        device_id=1, protocol="ssh", username="u", secret="session-secret", port=2201,
    ))

    assert result["success"] is True
    m = manager(db, factory)
    session = m.create_session(
        device_id=1, user_id=7, protocol="ssh", username="u", secret="session-secret", port=2201,
    )
    assert session.status == "connected"
    assert m.get_session(session.session_uuid).adapter.connected is True


def test_remembered_test_connection_hands_off_same_credential_id(db):
    factory = Adapter
    validation = TestConnectionService(db, adapter_factories={"ssh": factory})
    result = validation.test_connection(TestConnectionRequest(
        device_id=1, protocol="ssh", username="u", secret="session-secret",
        port=22, remember_credential=True,
    ))
    assert result["success"] is True and result["credential_id"] is not None

    m = manager(db, factory)
    session = m.create_session(
        device_id=1, user_id=7, protocol="ssh", port=22,
        credential_id=result["credential_id"],
    )
    assert session.status == "connected"
    assert session.credential_id == result["credential_id"]


def test_idle_timeout_cleanup(db):
    m = manager(db, idle_timeout=timedelta(seconds=30))
    session = m.create_session(device_id=1, user_id=1, protocol="telnet", username="u", secret="s")
    session.last_activity_at = datetime.utcnow() - timedelta(minutes=2)
    expired = m.cleanup_expired_sessions()
    assert expired == [session.session_uuid]
    assert session.status == "timeout" and session.disconnect_reason == "Idle timeout"
    assert Adapter.instances[0].closed == 1 and m.get_session(session.session_uuid) is None


def test_transport_reconciliation_is_idempotent_and_stops_duration(db):
    m = manager(db)
    session = m.create_session(device_id=1, user_id=1, protocol="ssh", username="u", secret="s")
    ended = m.reconcile_transport(session.session_uuid, reason="Session disconnected by device").ended_at
    assert session.status == "disconnected"
    assert session.disconnect_reason == "Session disconnected by device"
    assert session.ended_at == ended
    assert Adapter.instances[0].closed == 1
    with Session(db.get_bind()) as history_db:
        persisted = history_db.query(RemoteAccessSession).filter_by(session_uuid=session.session_uuid).one()
        assert persisted.status == "disconnected"
        assert persisted.ended_at == ended
    m.reconcile_transport(session.session_uuid, reason="WebSocket/remote transport failure")


def test_auth_failure_persists_safe_human_reason(db):
    class AuthFailure(Adapter):
        def connect(self):
            error = ConnectionError("secret should not persist")
            error.code = "SSH_AUTH_FAILED"
            raise error

    m = manager(db, AuthFailure)
    with pytest.raises(ConnectionError):
        m.create_session(device_id=1, user_id=1, protocol="ssh", username="u", secret="secret")
    row = db.query(RemoteAccessSession).one()
    assert row.disconnect_reason == "Authentication failed"
    assert "secret" not in repr(row)
