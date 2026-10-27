from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.cim import CIMError
from backend.windows_monitoring.api import router


def connection():
    return SimpleNamespace(host="registered-winhost", username="DOMAIN\\monitor", password="secret-value")


def test_winrm_diagnostic_success_is_explicitly_indeterminate_for_auth_split(monkeypatch):
    adapter = Mock()
    adapter._session.return_value = object()
    adapter._run_powershell.return_value = (b"", b"", 0)
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/ca.pem"))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=Mock(operating_system=Mock(return_value=[object()]))))

    stages = api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))

    assert [stage["status"] for stage in stages] == ["PASS", "PASS", "PASS"]
    assert stages[0]["category"] == "indeterminate"
    assert "secret-value" not in str(stages)
    adapter._run_powershell.assert_called_once_with(adapter._session.return_value, "$PSVersionTable.PSVersion.ToString()")


@pytest.mark.parametrize(
    ("error", "category"),
    [(api.CIMError("permission", "secret-value"), "cim_access_denied"),
     (api.CIMError("parsing", "secret-value"), "cim_query_failed")],
)
def test_winrm_diagnostic_classifies_cim_failures_and_skips_nothing_after_powershell(monkeypatch, error, category):
    adapter = Mock()
    adapter._session.return_value = object()
    adapter._run_powershell.return_value = (b"", b"", 0)
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=Mock(operating_system=Mock(side_effect=error))))

    stages = api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))

    assert stages[-1]["status"] == "FAIL"
    assert stages[-1]["category"] == category
    assert "secret-value" not in str(stages)


def test_winrm_diagnostic_auth_failure_skips_dependent_stages(monkeypatch):
    adapter = Mock()
    adapter._session.side_effect = RuntimeError("password-secret")
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    adapter_factory = Mock(return_value=adapter)
    adapter_factory._classify.return_value = SimpleNamespace(category="authentication")
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", adapter_factory)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))

    stages = api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))

    assert stages[0]["category"] == "authentication_denied"
    assert [stage["status"] for stage in stages[1:]] == ["SKIPPED", "SKIPPED"]
    assert "password-secret" not in str(stages)


def test_winrm_route_uses_registered_device_controls_and_audits(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    device = SimpleNamespace(id=7, site_id=10)
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "_winrm_diagnostic", Mock(return_value=[
        {"step": "winrm_authentication", "status": "PASS", "category": "indeterminate", "message": "ok", "duration_ms": 1.0},
        {"step": "powershell_authorization", "status": "PASS", "category": "success", "message": "ok", "duration_ms": 1.0},
        {"step": "cim_query", "status": "PASS", "category": "success", "message": "ok", "duration_ms": 1.0},
    ]))
    monkeypatch.setattr(api, "record_audit_event", Mock())

    result = api.diagnose_winrm(7, db, SimpleNamespace(id=1))

    assert result["device_id"] == 7
    assert len(result["stages"]) == 3
    db.commit.assert_called_once()


def test_winrm_route_preserves_device_denial_and_permission_dependency(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.diagnose_winrm(7, Mock(), SimpleNamespace(id=1))
    assert exc.value.status_code == 404

    route = next(route for route in router.routes if route.path.endswith("diagnostics/winrm"))
    checker = next(dep.call for dep in route.dependant.dependencies if dep.call.__name__ == "checker")
    assert any(cell.cell_contents == "devices:update" for cell in checker.__closure__)
