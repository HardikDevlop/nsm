from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.api import router


class _Context:
    check_hostname = False
    verify_mode = None

    def __init__(self, certificate=None, error=None):
        self.certificate = certificate
        self.error = error

    def wrap_socket(self, _raw, server_hostname=None):
        if self.error:
            raise self.error
        return _TLS(self.certificate)


class _TLS:
    def __init__(self, certificate):
        self.certificate = certificate

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getpeercert(self):
        return self.certificate


class _Raw:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _certificate(expires_at):
    return {
        "subject": (("commonName", "winhost.example"),),
        "issuer": (("commonName", "Example Internal CA"),),
        "notAfter": expires_at.strftime("%b %d %H:%M:%S %Y GMT"),
        "subjectAltName": (("DNS", "winhost.example"),),
    }


def _patch_tls(monkeypatch, certificate=None, error=None):
    monkeypatch.setattr(api.ssl, "create_default_context", lambda cafile=None: _Context(certificate, error))
    monkeypatch.setattr(api.socket, "create_connection", lambda address, timeout: _Raw())


def test_tls_diagnostic_returns_verified_certificate_metadata(monkeypatch):
    _patch_tls(monkeypatch, _certificate(datetime.now(timezone.utc) + timedelta(days=365)))

    result = api._tls_diagnostic("winhost.example", ca_trust_path="/trusted/ca.pem")

    assert result["status"] == "PASS"
    assert result["category"] == "success"
    assert result["certificate"]["subject"] == "winhost.example"
    assert result["certificate"]["issuer"] == "Example Internal CA"
    assert result["certificate"]["san_match"] is True


def test_tls_diagnostic_marks_certificate_expiring_soon(monkeypatch):
    _patch_tls(monkeypatch, _certificate(datetime.now(timezone.utc) + timedelta(days=10)))

    result = api._tls_diagnostic("winhost.example")

    assert result["status"] == "PASS"
    assert result["category"] == "expiring_soon"
    assert result["certificate"]["days_remaining"] <= 30


@pytest.mark.parametrize(
    ("verify_code", "category"),
    [(20, "untrusted_certificate"), (21, "untrusted_certificate"), (10, "expired_certificate"), (9, "certificate_not_yet_valid"), (62, "hostname_mismatch")],
)
def test_tls_diagnostic_classifies_verified_ssl_failures(monkeypatch, verify_code, category):
    error = api.ssl.SSLCertVerificationError(verify_code, "secret-password")
    error.verify_code = verify_code
    _patch_tls(monkeypatch, error=error)

    result = api._tls_diagnostic("winhost.example")

    assert result["status"] == "FAIL"
    assert result["category"] == category
    assert "secret-password" not in str(result)
    assert "certificate" not in result


def test_tls_diagnostic_classifies_handshake_timeout_and_invalid_target(monkeypatch):
    _patch_tls(monkeypatch, error=api.ssl.SSLError("private-key-secret"))
    result = api._tls_diagnostic("winhost.example")
    assert result["category"] == "tls_handshake_failed"
    assert "private-key-secret" not in str(result)

    monkeypatch.setattr(api.socket, "create_connection", Mock(side_effect=api.socket.timeout()))
    result = api._tls_diagnostic("winhost.example")
    assert result["category"] == "timeout"

    result = api._tls_diagnostic("https://not-a-host")
    assert result["category"] == "invalid_target"


def test_tls_diagnostic_requires_matching_ip_san(monkeypatch):
    cert = _certificate(datetime.now(timezone.utc) + timedelta(days=365))
    cert["subjectAltName"] = (("DNS", "winhost.example"),)
    _patch_tls(monkeypatch, cert)

    result = api._tls_diagnostic("10.0.0.7")

    assert result["status"] == "FAIL"
    assert result["category"] == "hostname_mismatch"
    assert result["certificate"]["san_match"] is False


def test_tls_route_uses_registered_target_and_existing_controls(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    device = SimpleNamespace(id=7, site_id=10)
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "_windows_tcp_target", Mock(return_value="registered-winhost"))
    tls = Mock(return_value={"step": "tls_certificate", "status": "PASS", "category": "success", "message": "ok", "duration_ms": 1.0})
    monkeypatch.setattr(api, "_tls_diagnostic", tls)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/ca.pem"))
    monkeypatch.setattr(api, "record_audit_event", Mock())

    result = api.diagnose_tls(7, db, SimpleNamespace(id=1))

    assert result["status"] == "PASS"
    tls.assert_called_once_with("registered-winhost", ca_trust_path="/trusted/ca.pem", port=5986)
    db.commit.assert_called_once()


def test_tls_route_preserves_device_denial(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.diagnose_tls(7, Mock(), SimpleNamespace(id=1))
    assert exc.value.status_code == 404


def test_tls_route_requires_devices_update_permission():
    route = next(route for route in router.routes if route.path.endswith("diagnostics/tls"))
    checker = next(dep.call for dep in route.dependant.dependencies if dep.call.__name__ == "checker")
    assert any(cell.cell_contents == "devices:update" for cell in checker.__closure__)
