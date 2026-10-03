from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models import Base, Device, RemoteAccessCredential
from backend.services.remote_access.test_connection import TestConnectionRequest, TestConnectionService
from backend.services.remote_access.ssh_service import SSHConnectionError
from backend.services.remote_access import ssh_service


class FakeAdapter:
    def __init__(self, host, port, username, secret, **kwargs):
        self.host, self.port, self.username = host, port, username
        self.secret = secret
        self.disconnected = False

    def connect(self):
        return self

    def disconnect(self):
        self.disconnected = True


class FailingAdapter(FakeAdapter):
    def connect(self):
        raise ConnectionError("secret must not escape")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Device.__table__, RemoteAccessCredential.__table__])
    with Session(engine) as session:
        session.add(Device(id=1, hostname="edge-1", ip_address="192.0.2.10", created_at=datetime.utcnow()))
        session.commit()
        yield session


def request(**overrides):
    values = dict(device_id=1, protocol="ssh", username="admin", secret="top-secret")
    values.update(overrides)
    return TestConnectionRequest(**values)


def test_success_custom_port_remember_and_cleanup(db):
    instances = []

    def factory(*args, **kwargs):
        item = FakeAdapter(*args, **kwargs)
        instances.append(item)
        return item

    result = TestConnectionService(db, adapter_factories={"ssh": factory, "telnet": factory}).test_connection(
        request(port=2201, remember_credential=True)
    )
    saved = db.query(RemoteAccessCredential).one()
    assert result["success"] is True and result["port"] == 2201
    assert result["connection_metadata"]["shell_validated"] is True
    assert saved.port == 2201 and saved.is_verified is True
    assert instances[0].disconnected is True
    assert "top-secret" not in repr(result)
    assert result["credential_id"] == saved.id


def test_success_with_verified_credential_returns_only_id(db):
    service = TestConnectionService(db, adapter_factories={"ssh": FakeAdapter})
    first = service.test_connection(request(remember_credential=True))
    result = service.test_connection(request(remember_credential=False))

    assert result["success"] is True
    assert result["credential_id"] == first["credential_id"]
    assert "top-secret" not in repr(result)


def test_remember_false_does_not_save(db):
    result = TestConnectionService(db, adapter_factories={"telnet": FakeAdapter}).test_connection(
        request(protocol="telnet", remember_credential=False)
    )
    assert result["success"] is True
    assert db.query(RemoteAccessCredential).count() == 0


def test_failure_marks_existing_unverified_and_cleans_up(db):
    existing = RemoteAccessCredential(device_id=1, protocol="ssh", port=22, username="old",
                                      auth_type="password", encrypted_secret="encrypted", is_verified=True)
    db.add(existing)
    db.commit()
    instances = []

    def factory(*args, **kwargs):
        item = FailingAdapter(*args, **kwargs)
        instances.append(item)
        return item

    result = TestConnectionService(db, adapter_factories={"ssh": factory}).test_connection(request())
    assert result["success"] is False and result["error_code"] == "CONNECTION_FAILED"
    assert existing.is_verified is False
    assert instances[0].disconnected is True
    assert "top-secret" not in repr(result)


@pytest.mark.parametrize("code,stage", [("TCP_TIMEOUT", "TCP_CONNECT"), ("SSH_AUTH_FAILED", "SSH_TRANSPORT_AUTH"), ("PTY_OPEN_FAILED", "PTY_OPEN")])
def test_stage_specific_ssh_failure_is_returned_safely(db, code, stage):
    class StageFailingAdapter(FakeAdapter):
        def connect(self):
            raise SSHConnectionError("safe failure", code, stage)

    result = TestConnectionService(db, adapter_factories={"ssh": StageFailingAdapter}).test_connection(request())
    assert result["success"] is False
    assert result["error_code"] == code
    assert result["stage"] == stage
    assert result["message"] == "safe failure"


@pytest.mark.parametrize("field,value,code", [("protocol", "ftp", "INVALID_PROTOCOL"), ("port", 0, "INVALID_PORT"),
                                                ("username", "", "INVALID_USERNAME"), ("secret", "", "SECRET_REQUIRED")])
def test_input_validation(db, field, value, code):
    result = TestConnectionService(db).test_connection(request(**{field: value}))
    assert result["success"] is False and result["error_code"] == code


def test_legacy_rsa_is_scoped_to_remote_access_transport(monkeypatch):
    transport = object.__new__(ssh_service._RemoteAccessTransport)
    options = type("Options", (), {"key_types": ("ssh-ed25519",)})()

    monkeypatch.setattr(ssh_service.paramiko.Transport, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(ssh_service._RemoteAccessTransport, "get_security_options",
                        lambda self: options)
    # The production class appends rsa only; dss must never be introduced.
    ssh_service._RemoteAccessTransport.__init__(transport)
    assert "ssh-rsa" in options.key_types
    assert "ssh-dss" not in options.key_types


def test_handshake_logs_original_sanitized_paramiko_exception(caplog, monkeypatch):
    class FakeClient:
        def load_system_host_keys(self): pass
        def set_missing_host_key_policy(self, policy): pass
        def close(self): pass

    monkeypatch.setattr(ssh_service.paramiko, "SSHClient", FakeClient)
    monkeypatch.setattr(ssh_service.socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(
        ssh_service.paramiko.SSHException(
            "Could not agree on a host key algorithm (ssh-rsa) for 192.168.100.2 secret"
        )
    ))
    adapter = ssh_service.SSHConnectionAdapter("192.168.100.2", 22, "admin", "secret")
    with pytest.raises(SSHConnectionError):
        adapter.connect()
    record = next(r for r in caplog.records if "exception_type=SSHException" in r.message)
    assert "Could not agree on a host key algorithm (ssh-rsa)" in record.message
    assert "secret" not in record.message
    assert "192.168.100.2" not in record.message


def test_live_connect_constructs_scoped_transport_and_starts_it(monkeypatch):
    events = []

    class FakeSocket:
        def close(self): pass

    class FakeTransport:
        def __init__(self, sock):
            events.append("transport_init")
            self.remote_version = "SSH-2.0-OpenSSH_6.2"
            self.remote_kex = self.remote_cipher = self.remote_mac = "UNAVAILABLE"
            self.local_kex = self.local_cipher = self.host_key_type = "UNAVAILABLE"
            self._options = type("Options", (), {
                "key_types": ("ssh-rsa",), "kex": (), "ciphers": (), "digests": ()
            })()
        def get_security_options(self): return self._options
        def start_client(self, timeout=None): events.append("start_client")
        def get_remote_server_key(self):
            return type("Key", (), {"get_name": lambda self: "ssh-rsa"})()
        def auth_password(self, username, password): events.append("auth_password")
        def open_session(self): raise AssertionError("not part of handshake regression")

    class FakeClient:
        _system_host_keys = {}
        _host_keys = {}
        _policy = type("Policy", (), {"missing_host_key": lambda *args: None})()
        _transport = None
        def load_system_host_keys(self): pass
        def set_missing_host_key_policy(self, policy): pass
        def get_transport(self): return self._transport
        def close(self): pass

    monkeypatch.setattr(ssh_service.paramiko, "SSHClient", FakeClient)
    monkeypatch.setattr(ssh_service.socket, "create_connection", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(ssh_service, "_RemoteAccessTransport", FakeTransport)
    # Stop after auth so this test is specifically about the handshake path.
    class StopAfterAuth(ssh_service.SSHConnectionAdapter):
        pass
    adapter = ssh_service.SSHConnectionAdapter("192.168.100.2", 22, "admin", "secret")
    with pytest.raises((AssertionError, AttributeError, ssh_service.SSHConnectionError)):
        adapter.connect()
    assert events[:3] == ["transport_init", "start_client", "auth_password"]


class _BootstrapChannel:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
    def recv_ready(self): return bool(self.chunks)
    def recv(self, _size): return self.chunks.pop(0)
    def sendall(self, data): self.sent.append(data)


def test_cli_bootstrap_answers_bounded_prompts_without_forwarding_password():
    channel = _BootstrapChannel([b"Username:", b"admin\r\nPassword:", b"secret\r\ncore#"])
    adapter = ssh_service.SSHConnectionAdapter("192.0.2.1", 22, "admin", "secret", timeout=0.2)
    adapter._bootstrap_cli_login(channel)
    assert channel.sent == [b"admin\r", b"secret\r"]
    assert b"secret" not in bytes(adapter._pending_output)


def test_cli_bootstrap_preserves_non_login_banner():
    channel = _BootstrapChannel([b"Welcome to core#"])
    adapter = ssh_service.SSHConnectionAdapter("192.0.2.1", 22, "admin", "secret", timeout=0.2)
    adapter._bootstrap_cli_login(channel)
    assert adapter.read() == b"Welcome to core#"
    assert channel.sent == []


def test_cli_bootstrap_times_out_after_recognized_username_prompt():
    channel = _BootstrapChannel([b"Login:"])
    adapter = ssh_service.SSHConnectionAdapter("192.0.2.1", 22, "admin", "secret", timeout=0.1)
    with pytest.raises(ssh_service.SSHConnectionError, match="timed out"):
        adapter._bootstrap_cli_login(channel)
