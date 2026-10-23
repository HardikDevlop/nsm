from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime

from backend.windows_monitoring.schemas import WindowsCredentialCreate, WindowsCredentialUpdate
from backend.windows_monitoring.service import WindowsCredentialService
from backend.windows_monitoring.winrm import WinRMConnectionDiagnostic


def query_result(obj):
    query = Mock()
    query.filter.return_value.first.return_value = obj
    return query


def db_for(*objects):
    db = Mock()
    db.query.side_effect = [query_result(obj) for obj in objects]
    return db


def test_create_encrypts_and_read_does_not_expose_secret(monkeypatch):
    encrypted = Mock(return_value="ciphertext")
    monkeypatch.setattr("backend.windows_monitoring.service.encrypt_secret", encrypted)
    device = SimpleNamespace(id=7, hostname="winhost", ip_address="10.0.0.7")
    db = db_for(device)
    db.flush.side_effect = lambda: setattr(db.add.call_args.args[0], "id", 1) or setattr(db.add.call_args.args[0], "is_verified", False) or setattr(db.add.call_args.args[0], "created_at", datetime.now()) or setattr(db.add.call_args.args[0], "updated_at", datetime.now())
    result = WindowsCredentialService().create(
        db, WindowsCredentialCreate(device_id=7, username="admin", secret="plain-password")
    )
    encrypted.assert_called_once_with("plain-password")
    saved = db.add.call_args.args[0]
    assert saved.encrypted_secret == "ciphertext"
    assert "secret" not in result.model_dump()
    assert "encrypted_secret" not in result.model_dump()


def test_update_rotates_password_and_invalidates_verification(monkeypatch):
    monkeypatch.setattr("backend.windows_monitoring.service.encrypt_secret", Mock(return_value="new-cipher"))
    credential = SimpleNamespace(id=3, device_id=7, auth_method="password", enabled=True,
                                 domain=None, encrypted_secret="old-cipher", is_verified=True,
                                 last_verified_at="old", created_at=datetime.now(), updated_at=datetime.now())
    db = db_for(credential)
    result = WindowsCredentialService().update(
        db, 3, WindowsCredentialUpdate(secret="new-password", username="new-admin")
    )
    assert credential.encrypted_secret == "new-cipher"
    assert credential.username == "new-admin"
    assert credential.is_verified is False
    assert credential.last_verified_at is None
    assert "new-password" not in str(result.model_dump())


def test_connection_decrypts_in_memory_and_marks_only_success(monkeypatch):
    credential = SimpleNamespace(
        id=3, device_id=7, enabled=True, encrypted_secret="cipher", is_verified=False, last_verified_at=None,
        username="admin", domain=None,
    )
    device = SimpleNamespace(id=7, hostname="winhost", ip_address="10.0.0.7")
    monkeypatch.setattr("backend.windows_monitoring.service.decrypt_secret", Mock(return_value="plain-password"))
    monkeypatch.setattr("backend.windows_monitoring.service.get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/winrm.pem"))
    monkeypatch.setattr("backend.windows_monitoring.service.Path.is_file", lambda self: True)
    monkeypatch.setattr("backend.windows_monitoring.service.Path.stat", lambda self: SimpleNamespace(st_size=1))
    adapter = Mock()
    adapter.return_value.test_connection.return_value = WinRMConnectionDiagnostic(True, "success", "ok")
    db = db_for(credential, device)
    result = WindowsCredentialService().test_connection(db, 3, adapter_factory=adapter)
    assert result.ok is True
    assert credential.is_verified is True
    assert adapter.call_args.args[:3] == ("winhost", "admin", "plain-password")
    assert adapter.call_args.kwargs["ca_trust_path"] == "/trusted/winrm.pem"
    assert adapter.call_args.kwargs["connect_timeout"] == 30
    assert adapter.call_args.kwargs["operation_timeout"] == 20


def test_connection_uses_domain_username_once_and_device_hostname(monkeypatch):
    credential = SimpleNamespace(
        id=2, device_id=311, enabled=True, encrypted_secret="cipher", is_verified=False,
        last_verified_at=None, username="nms_monitor_window", domain="DESKTOP-ENI0R6E",
    )
    device = SimpleNamespace(id=311, hostname="DESKTOP-ENI0R6E", ip_address="192.168.100.154")
    monkeypatch.setattr("backend.windows_monitoring.service.decrypt_secret", Mock(return_value="redacted-password"))
    monkeypatch.setattr("backend.windows_monitoring.service.get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/winrm.pem"))
    monkeypatch.setattr("backend.windows_monitoring.service.Path.is_file", lambda self: True)
    monkeypatch.setattr("backend.windows_monitoring.service.Path.stat", lambda self: SimpleNamespace(st_size=1))
    adapter = Mock()
    adapter.return_value.test_connection.return_value = WinRMConnectionDiagnostic(False, "protocol", "failed")

    WindowsCredentialService().test_connection(db_for(credential, device), 2, adapter_factory=adapter)

    assert adapter.call_args.args[:2] == ("DESKTOP-ENI0R6E", r"DESKTOP-ENI0R6E\nms_monitor_window")


def test_connection_host_overrides_inventory_hostname_without_changing_device(monkeypatch):
    credential = SimpleNamespace(
        id=2, device_id=311, enabled=True, encrypted_secret="cipher", is_verified=False,
        last_verified_at=None, username="nms_monitor_window", domain="DESKTOP-ENI0R6E",
        connection_host="DESKTOP-ENI0R6E",
    )
    device = SimpleNamespace(id=311, hostname="device-192-168-100-154", ip_address="192.168.100.154")
    monkeypatch.setattr("backend.windows_monitoring.service.decrypt_secret", Mock(return_value="redacted-password"))
    monkeypatch.setattr("backend.windows_monitoring.service.get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/winrm.pem"))
    monkeypatch.setattr("backend.windows_monitoring.service.Path.is_file", lambda self: True)
    monkeypatch.setattr("backend.windows_monitoring.service.Path.stat", lambda self: SimpleNamespace(st_size=1))
    adapter = Mock()
    adapter.return_value.test_connection.return_value = WinRMConnectionDiagnostic(False, "protocol", "failed")

    WindowsCredentialService().test_connection(db_for(credential, device), 2, adapter_factory=adapter)

    assert adapter.call_args.args[0] == "DESKTOP-ENI0R6E"
    assert device.hostname == "device-192-168-100-154"


def test_failed_authentication_does_not_mark_verified_or_leak_secret(monkeypatch):
    credential = SimpleNamespace(
        id=3, device_id=7, enabled=True, encrypted_secret="cipher", is_verified=False, last_verified_at=None,
        username="admin", domain=None,
    )
    device = SimpleNamespace(id=7, hostname="winhost", ip_address="10.0.0.7")
    monkeypatch.setattr("backend.windows_monitoring.service.decrypt_secret", Mock(return_value="plain-password"))
    monkeypatch.setattr("backend.windows_monitoring.service.get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/winrm.pem"))
    monkeypatch.setattr("backend.windows_monitoring.service.Path.is_file", lambda self: True)
    monkeypatch.setattr("backend.windows_monitoring.service.Path.stat", lambda self: SimpleNamespace(st_size=1))
    adapter = Mock()
    adapter.return_value.test_connection.return_value = WinRMConnectionDiagnostic(False, "authentication", "failed")
    db = db_for(credential, device)
    result = WindowsCredentialService().test_connection(db, 3, adapter_factory=adapter)
    assert result.category == "authentication"
    assert credential.is_verified is False
    assert "plain-password" not in result.message


def test_missing_trust_configuration_does_not_attempt_connection(monkeypatch):
    credential = SimpleNamespace(id=3, device_id=7, enabled=True, encrypted_secret="cipher", is_verified=False, last_verified_at=None)
    monkeypatch.setattr("backend.windows_monitoring.service.decrypt_secret", Mock(return_value="plain-password"))
    monkeypatch.setattr("backend.windows_monitoring.service.get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))
    adapter = Mock()
    result = WindowsCredentialService().test_connection(db_for(credential, SimpleNamespace(id=7, hostname="winhost", ip_address="10.0.0.7")), 3, adapter_factory=adapter)
    assert result == WinRMConnectionDiagnostic(False, "tls", "Windows CA trust is not configured")
    adapter.assert_not_called()


def test_invalid_trust_configuration_does_not_attempt_connection(monkeypatch):
    credential = SimpleNamespace(id=3, device_id=7, enabled=True, encrypted_secret="cipher", is_verified=False, last_verified_at=None)
    monkeypatch.setattr("backend.windows_monitoring.service.decrypt_secret", Mock(return_value="plain-password"))
    monkeypatch.setattr("backend.windows_monitoring.service.get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/missing/winrm.pem"))
    monkeypatch.setattr("backend.windows_monitoring.service.Path.is_file", lambda self: False)
    adapter = Mock()
    result = WindowsCredentialService().test_connection(db_for(credential, SimpleNamespace(id=7, hostname="winhost", ip_address="10.0.0.7")), 3, adapter_factory=adapter)
    assert result == WinRMConnectionDiagnostic(False, "tls", "Windows CA trust configuration is invalid")
    adapter.assert_not_called()
