from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.cim import CIMError
from backend.windows_monitoring.api import router


def connection():
    return SimpleNamespace(host="registered-winhost", username="DOMAIN\\monitor", password="secret-value")


def test_winrm_diagnostic_success_preserves_process_path(monkeypatch):
    adapter = Mock()
    adapter._session.return_value = object()
    adapter._run_powershell.return_value = (b"", b"", 0)
    client = Mock(operating_system=Mock(return_value=[object()]), processes=Mock(return_value=[]))
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/ca.pem"))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    stages = api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))
    assert [stage["step"] for stage in stages] == ["winrm_authentication", "powershell_authorization", "cim_query", "process_query"]
    assert all(stage["status"] == "PASS" for stage in stages)
    assert stages[0]["category"] == "indeterminate"
    assert "secret-value" not in str(stages)
    assert client.processes.called


def test_process_query_diagnostic_uses_bounded_process_limit(monkeypatch):
    adapter = Mock(); adapter._session.return_value = object(); adapter._run_powershell.return_value = (b"", b"", 0)
    client = Mock(operating_system=Mock(return_value=[object()]), processes=Mock(return_value=[]))
    factory = Mock(return_value=client)
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))
    monkeypatch.setattr(api, "WindowsCIMClient", factory)
    api._winrm_diagnostic(Mock(), 361, SimpleNamespace(id=1))
    assert factory.call_args_list[0].kwargs.get("limits") is None
    assert factory.call_args_list[1].kwargs["limits"].max_items == api.PROCESS_CIM_MAX_ITEMS


@pytest.mark.parametrize(("error", "category"), [(api.CIMError("permission", "secret-value"), "cim_access_denied"), (api.CIMError("parsing", "secret-value"), "cim_query_failed")])
def test_winrm_diagnostic_classifies_cim_failures(monkeypatch, error, category):
    adapter = Mock(); adapter._session.return_value = object(); adapter._run_powershell.return_value = (b"", b"", 0)
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=Mock(operating_system=Mock(side_effect=error), processes=Mock(return_value=[]))))
    stages = api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))
    stage = next(item for item in stages if item["step"] == "cim_query")
    assert stage["status"] == "FAIL" and stage["category"] == category
    assert "secret-value" not in str(stages)


@pytest.mark.parametrize(("message", "classification"), [("WSMan returned a SOAP fault", "soap_fault"), ("WSMan response omitted enumeration context", "invalid_enumeration_context"), ("Malformed WSMan enumeration response", "malformed_response"), ("WSMan item limit exceeded", "item_limit_exceeded"), ("WSMan response exceeded the configured limit", "response_size_exceeded"), ("WSMan page limit exceeded", "pagination_limit"), ("permission denied", "permission_denied"), ("WSMan operation timed out", "timeout")])
def test_task_manager_cim_failure_classification_is_sanitized(message, classification):
    error = api.CIMError("protocol", message) if "limit" in message else api.CIMError("timeout", message) if "timed out" in message else api.CIMError("permission", message)
    category, result = api._task_manager_cim_failure(error)
    assert result == classification and category in {"protocol", "timeout", "permission"}


def test_process_query_failure_is_independent(monkeypatch):
    adapter = Mock(); adapter._session.return_value = object(); adapter._run_powershell.return_value = (b"", b"", 0)
    client = Mock(operating_system=Mock(return_value=[object()]), processes=Mock(side_effect=api.CIMError("protocol", "WSMan item limit exceeded")))
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    stages = api._winrm_diagnostic(Mock(), 361, SimpleNamespace(id=1))
    assert stages[-1]["classification"] == "item_limit_exceeded" and stages[-1]["status"] == "FAIL"
    assert "WSMan item limit exceeded" not in str(stages)


def test_task_manager_diagnostic_logs_sanitized_cim_failure(caplog):
    with caplog.at_level("WARNING", logger="backend.windows_monitoring.api"):
        result = api._task_manager_query_stage("process_query", lambda: (_ for _ in ()).throw(CIMError("protocol", "secret SOAP payload")), 0.0)
    assert result["classification"] == "protocol_error"
    assert "step=process_query" in caplog.text and "secret SOAP payload" not in caplog.text


def test_winrm_diagnostic_auth_failure_skips_dependent_stages(monkeypatch):
    adapter = Mock(); adapter._session.side_effect = RuntimeError("password-secret")
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection()))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path=""))
    stages = api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))
    assert stages[0]["category"] == "indeterminate"
    assert [stage["status"] for stage in stages[1:]] == ["SKIPPED", "SKIPPED"]
    assert "password-secret" not in str(stages)


def test_winrm_route_uses_registered_device_controls_and_audits(monkeypatch):
    db = Mock(); db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=SimpleNamespace(id=7, site_id=10)))
    monkeypatch.setattr(api, "_winrm_diagnostic", Mock(return_value=[{"step": "winrm_authentication", "status": "PASS", "category": "indeterminate", "message": "ok", "duration_ms": 1.0}, {"step": "powershell_authorization", "status": "PASS", "category": "success", "message": "ok", "duration_ms": 1.0}, {"step": "cim_query", "status": "PASS", "category": "success", "message": "ok", "duration_ms": 1.0}, {"step": "process_query", "status": "PASS", "category": "success", "message": "ok", "duration_ms": 1.0}]))
    monkeypatch.setattr(api, "record_audit_event", Mock())
    result = api.diagnose_winrm(7, db, SimpleNamespace(id=1))
    assert result["device_id"] == 7 and len(result["stages"]) == 4
    db.commit.assert_called_once()


def test_winrm_route_preserves_device_denial_and_permission_dependency(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.diagnose_winrm(7, Mock(), SimpleNamespace(id=1))
    assert exc.value.status_code == 404
    route = next(route for route in router.routes if route.path.endswith("diagnostics/winrm"))
    checker = next(dep.call for dep in route.dependant.dependencies if dep.call.__name__ == "checker")
    assert any(cell.cell_contents == "devices:update" for cell in checker.__closure__)
