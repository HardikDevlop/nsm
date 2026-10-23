import base64
import logging

import pytest
from requests.exceptions import SSLError
from winrm.exceptions import AuthenticationError, WinRMOperationTimeoutError, WinRMTransportError, WSManFaultError

from backend.windows_monitoring.winrm import WinRMHTTPSAdapter


class FakeSession:
    def __init__(self, result=None, error=None, protocol=None):
        self.result = result
        self.error = error
        self.calls = []
        self.protocol = protocol


class FakeProtocol:
    def __init__(self, output=(b"", b"", 0), error=None, cleanup_error=None):
        self.output = output
        self.error = error
        self.cleanup_error = cleanup_error
        self.calls = []

    def open_shell(self, **kwargs):
        self.calls.append(("open_shell", kwargs))
        if self.error:
            raise self.error
        return "shell-1"

    def run_command(self, shell_id, command, args):
        self.calls.append(("run_command", shell_id, command, args))
        return "command-1"

    def get_command_output(self, shell_id, command_id):
        self.calls.append(("get_command_output", shell_id, command_id))
        if self.error:
            raise self.error
        return self.output

    def cleanup_command(self, shell_id, command_id):
        self.calls.append(("cleanup_command", shell_id, command_id))
        if self.cleanup_error:
            raise self.cleanup_error

    def close_shell(self, shell_id):
        self.calls.append(("close_shell", shell_id))


def adapter(fake):
    return WinRMHTTPSAdapter(
        "winhost.example", "admin", "secret-value", ca_trust_path="/tmp/ca.pem", session_factory=fake
    )


def test_success_uses_https_ntlm_and_read_only_command():
    protocol = FakeProtocol(output=(b"10.0", b"", 0))
    fake = FakeSession(protocol=protocol)
    captured = {}

    def factory(endpoint, **kwargs):
        captured.update(endpoint=endpoint, kwargs=kwargs)
        return fake

    result = WinRMHTTPSAdapter("winhost.example", "admin", "secret-value", session_factory=factory).test_connection()
    assert result == result.__class__(True, "success", "WinRM HTTPS connection succeeded")
    assert captured["endpoint"] == "https://winhost.example:5986/wsman"
    assert captured["kwargs"]["transport"] == "ntlm"
    assert captured["kwargs"]["server_cert_validation"] == "validate"
    assert protocol.calls[0] == ("open_shell", {"noprofile": True})
    run_call = protocol.calls[1]
    assert run_call[0:3] == ("run_command", "shell-1", "powershell.exe")
    assert run_call[3][0:3] == ["-NoProfile", "-NonInteractive", "-EncodedCommand"]
    assert base64.b64decode(run_call[3][3]).decode("utf-16le") == "$PSVersionTable.PSVersion.ToString()"
    assert protocol.calls[-2:] == [("cleanup_command", "shell-1", "command-1"), ("close_shell", "shell-1")]


def test_default_timeouts_are_compatible_with_pywinrm():
    captured = {}

    def factory(endpoint, **kwargs):
        captured.update(endpoint=endpoint, kwargs=kwargs)
        return FakeSession(protocol=FakeProtocol())

    WinRMHTTPSAdapter("winhost.example", "admin", "secret-value", session_factory=factory)._session()
    assert captured["kwargs"]["read_timeout_sec"] == 30
    assert captured["kwargs"]["operation_timeout_sec"] == 20
    assert captured["kwargs"]["read_timeout_sec"] > captured["kwargs"]["operation_timeout_sec"]


def test_session_normalizes_cim_timeout_pair_for_pywinrm():
    captured = {}

    def factory(endpoint, **kwargs):
        captured.update(endpoint=endpoint, kwargs=kwargs)
        return FakeSession(protocol=FakeProtocol())

    WinRMHTTPSAdapter(
        "winhost.example",
        "admin",
        "secret-value",
        connect_timeout=10,
        operation_timeout=20,
        session_factory=factory,
    )._session()

    assert captured["kwargs"]["read_timeout_sec"] == 21
    assert captured["kwargs"]["operation_timeout_sec"] == 20


def test_session_preserves_larger_configured_read_timeout():
    captured = {}

    def factory(endpoint, **kwargs):
        captured.update(endpoint=endpoint, kwargs=kwargs)
        return FakeSession(protocol=FakeProtocol())

    WinRMHTTPSAdapter(
        "winhost.example",
        "admin",
        "secret-value",
        connect_timeout=30,
        operation_timeout=20,
        session_factory=factory,
    )._session()

    assert captured["kwargs"]["read_timeout_sec"] == 30


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (WinRMOperationTimeoutError("timeout"), "timeout"),
        (SSLError("certificate secret-value"), "tls"),
        (AuthenticationError("password secret-value"), "authentication"),
        (WinRMTransportError("connection refused"), "network"),
        (WSManFaultError(1, "message", "response", "reason"), "protocol"),
    ],
)
def test_failures_are_classified_without_secrets(error, category):
    protocol = FakeProtocol(error=error)
    result = adapter(lambda *args, **kwargs: FakeSession(protocol=protocol)).test_connection()
    assert not result.ok
    assert result.category == category
    assert "secret-value" not in result.message


@pytest.mark.parametrize("hostname", ["http://host", "host/path", "host:5985", "bad host"])
def test_rejects_non_bare_targets(hostname):
    with pytest.raises(ValueError):
        WinRMHTTPSAdapter(hostname, "admin", "secret")


def test_rejects_invalid_ports_and_never_returns_password():
    with pytest.raises(ValueError):
        WinRMHTTPSAdapter("host", "admin", "secret", port=0)
    result = adapter(lambda *args, **kwargs: FakeSession(error=RuntimeError("secret-value"))).test_connection()
    assert result.category == "protocol"
    assert "secret-value" not in result.message


def test_access_denied_is_classified_and_shell_is_cleaned_up():
    protocol = FakeProtocol(error=PermissionError("access denied secret-value"))
    result = adapter(lambda *args, **kwargs: FakeSession(protocol=protocol)).test_connection()
    assert result.category == "protocol"
    assert "secret-value" not in result.message
    assert protocol.calls == [("open_shell", {"noprofile": True})]


def test_timeout_cleans_up_command_and_shell():
    protocol = FakeProtocol(error=WinRMOperationTimeoutError("timeout"))
    result = adapter(lambda *args, **kwargs: FakeSession(protocol=protocol)).test_connection()
    assert result.category == "timeout"
    assert protocol.calls == [("open_shell", {"noprofile": True})]


def test_command_failure_after_shell_creation_cleans_up_command_and_shell():
    protocol = FakeProtocol()
    protocol.output = (b"", b"", 1)
    result = adapter(lambda *args, **kwargs: FakeSession(protocol=protocol)).test_connection()
    assert result.category == "protocol"
    assert protocol.calls[-2:] == [("cleanup_command", "shell-1", "command-1"), ("close_shell", "shell-1")]


def test_cleanup_failure_is_classified_without_leaking_details():
    protocol = FakeProtocol(cleanup_error=RuntimeError("cleanup secret-value"))
    result = adapter(lambda *args, **kwargs: FakeSession(protocol=protocol)).test_connection()
    assert result.category == "success"
    assert "secret-value" not in result.message
    assert protocol.calls[-2:] == [("cleanup_command", "shell-1", "command-1"), ("close_shell", "shell-1")]


def test_system_event_failure_logs_safe_stage_and_category(caplog):
    protocol = FakeProtocol(error=WinRMOperationTimeoutError("secret-value"))
    instance = adapter(lambda *args, **kwargs: FakeSession(protocol=protocol))
    instance._run_event_powershell = lambda command: (_ for _ in ()).throw(WinRMOperationTimeoutError("secret-value"))

    with caplog.at_level(logging.WARNING, logger="backend.windows_monitoring.winrm"):
        with pytest.raises(WinRMOperationTimeoutError):
            instance.query_system_events(
                start_time="2026-10-17T00:00:00+00:00",
                end_time="2026-10-17T01:00:00+00:00",
                event_ids=(),
                max_records=10,
            )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == (
        "windows_system_event_failure stage=event_query "
        "host=winhost.example exception_type=WinRMOperationTimeoutError category=timeout fault_code=None numeric_code=500 reason=unknown"
    )
    assert "secret-value" not in record.message


def test_system_event_session_failure_logs_safe_metadata(caplog):
    def failing_factory(*args, **kwargs):
        raise WSManFaultError(1, "secret-value", "response", "reason")

    instance = adapter(failing_factory)
    instance._run_event_powershell = lambda command: (_ for _ in ()).throw(WSManFaultError(1, "secret-value", "response", "reason"))
    with caplog.at_level(logging.WARNING, logger="backend.windows_monitoring.winrm"):
        with pytest.raises(WSManFaultError):
            instance.query_system_events(
                start_time="2026-10-17T00:00:00+00:00",
                end_time="2026-10-17T01:00:00+00:00",
                event_ids=(),
                max_records=10,
            )

    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        "windows_system_event_failure stage=event_query "
        "host=winhost.example exception_type=WSManFaultError category=protocol fault_code=None numeric_code=1 reason=reason"
    )
    assert "secret-value" not in caplog.records[0].message


class FakeRunspace:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.closed = False

    def open(self):
        return None

    def close(self):
        self.closed = True


class FakePowerShell:
    def __init__(self, pool):
        self.streams = type("Streams", (), {"error": []})()

    def add_script(self, command):
        self.command = command

    def invoke(self):
        return ['{"events":[],"truncated":false}']


def test_event_pypsrp_uses_configured_ca_bundle(monkeypatch):
    captured = {}

    def wsman(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("backend.windows_monitoring.winrm.WSMan", wsman)
    monkeypatch.setattr("backend.windows_monitoring.winrm.RunspacePool", FakeRunspace)
    monkeypatch.setattr("backend.windows_monitoring.winrm.PowerShell", FakePowerShell)

    instance = WinRMHTTPSAdapter("DESKTOP-USVQ0RO", "admin", "secret", ca_trust_path="/etc/nms/windows-ca.pem")
    stdout, stderr, status = instance._run_event_powershell("'ok'")

    assert captured["ssl"] is True
    assert captured["auth"] == "ntlm"
    assert captured["cert_validation"] == "/etc/nms/windows-ca.pem"
    assert status == 0 and stderr == b""


def test_event_pypsrp_defaults_to_system_ca_validation(monkeypatch):
    captured = {}
    monkeypatch.setattr("backend.windows_monitoring.winrm.WSMan", lambda *args, **kwargs: captured.update(kwargs) or object())
    monkeypatch.setattr("backend.windows_monitoring.winrm.RunspacePool", FakeRunspace)
    monkeypatch.setattr("backend.windows_monitoring.winrm.PowerShell", FakePowerShell)

    instance = WinRMHTTPSAdapter("DESKTOP-USVQ0RO", "admin", "secret")
    instance._run_event_powershell("'ok'")

    assert captured["cert_validation"] is True
