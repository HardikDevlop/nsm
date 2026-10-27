from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.api import router


def test_tcp_diagnostic_success_with_mocked_listener(monkeypatch):
    socket_factory = Mock()
    socket_factory.return_value.__enter__ = Mock(return_value=socket_factory.return_value)
    socket_factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(api.socket, "create_connection", socket_factory)

    result = api._tcp_diagnostic("winhost")

    assert result["step"] == "tcp_connect"
    assert result["status"] == "PASS"
    assert result["category"] == "success"
    assert isinstance(result["duration_ms"], float)
    socket_factory.assert_called_once_with(("winhost", 5986), timeout=api.TCP_DIAGNOSTIC_TIMEOUT_SECONDS)


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (ConnectionRefusedError(), "refused"),
        (TimeoutError(), "timeout"),
        (api.socket.gaierror("dns failure"), "dns"),
        (OSError("network failure"), "network"),
    ],
)
def test_tcp_diagnostic_classifies_network_failures(monkeypatch, error, category):
    monkeypatch.setattr(api.socket, "create_connection", Mock(side_effect=error))

    result = api._tcp_diagnostic("winhost")

    assert result["status"] == "FAIL"
    assert result["category"] == category
    assert "dns failure" not in result["message"]


def test_tcp_diagnostic_rejects_invalid_registered_target(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(api.socket, "create_connection", connect)

    result = api._tcp_diagnostic("https://not-a-registered-host")

    assert result["status"] == "FAIL"
    assert result["category"] == "invalid_target"
    connect.assert_not_called()


def test_tcp_diagnostic_route_uses_registered_target_and_audits(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    device = SimpleNamespace(id=7, site_id=10)
    audit = Mock()
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "_windows_tcp_target", Mock(return_value="registered-winhost"))
    monkeypatch.setattr(api, "_tcp_diagnostic", Mock(return_value={
        "step": "tcp_connect", "status": "PASS", "category": "success",
        "message": "TCP connection to WinRM HTTPS succeeded", "duration_ms": 1.0,
    }))
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.diagnose_tcp(7, db, SimpleNamespace(id=1))

    assert result["status"] == "PASS"
    api._tcp_diagnostic.assert_called_once_with("registered-winhost", port=5986)
    audit.assert_called_once()
    assert "secret" not in str(audit.call_args).lower()
    db.commit.assert_called_once()


def test_tcp_diagnostic_route_preserves_unregistered_and_cross_site_denials(monkeypatch):
    for error in (
        HTTPException(status_code=404, detail="Device not found"),
        HTTPException(status_code=404, detail="Device not found"),
    ):
        monkeypatch.setattr(api, "_device", Mock(side_effect=error))
        with pytest.raises(HTTPException) as exc:
            api.diagnose_tcp(7, Mock(), SimpleNamespace(id=1))
        assert exc.value.status_code == 404


def test_tcp_diagnostic_route_requires_devices_update_permission():
    route = next(route for route in router.routes if route.path.endswith("diagnostics/tcp"))
    checker = next(dep.call for dep in route.dependant.dependencies if dep.call.__name__ == "checker")
    assert any(cell.cell_contents == "devices:update" for cell in checker.__closure__)
