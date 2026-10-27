from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.effective_trust import EffectiveTrustError
from backend.windows_monitoring.winrm import WinRMConnectionDiagnostic


TRUST = SimpleNamespace(source="per_device", bundle_id=12, fingerprint="fp", protected_path="/protected/device-ca.pem")


def _connection():
    return api._WindowsConnectionContext(
        device=SimpleNamespace(id=7, site_id=10),
        credential=SimpleNamespace(id=3), host="winhost", username="DOMAIN\\admin", password="secret",
    )


def test_metric_client_passes_resolved_device_ca(monkeypatch):
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=_connection()))
    monkeypatch.setattr(api, "_effective_ca_path", Mock(return_value=TRUST.protected_path))
    factory = Mock(return_value="client")
    monkeypatch.setattr(api, "WindowsCIMClient", factory)

    api._metric_client(Mock(), 7, SimpleNamespace(id=1))

    assert factory.call_args.kwargs["trusted_ca_path"] == "/protected/device-ca.pem"


def test_winrm_diagnostic_passes_resolved_device_ca(monkeypatch):
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=_connection()))
    monkeypatch.setattr(api, "_effective_ca_path", Mock(return_value=TRUST.protected_path))
    adapter = Mock()
    adapter._session.return_value = object()
    adapter._run_powershell.return_value = (b"", b"", 0)
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock(return_value=adapter))
    cim = Mock(operating_system=Mock(return_value=[object()]))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=cim))

    api._winrm_diagnostic(Mock(), 7, SimpleNamespace(id=1))

    assert api.WinRMHTTPSAdapter.call_args.kwargs["ca_trust_path"] == "/protected/device-ca.pem"
    assert api.WindowsCIMClient.call_args.kwargs["trusted_ca_path"] == "/protected/device-ca.pem"


def test_tls_route_passes_resolved_device_ca(monkeypatch):
    db = Mock()
    device = SimpleNamespace(id=7, site_id=10)
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    monkeypatch.setattr(api, "_windows_tcp_target", Mock(return_value="winhost"))
    monkeypatch.setattr(api, "_effective_ca_path", Mock(return_value=TRUST.protected_path))
    tls = Mock(return_value={"status": "PASS", "category": "success", "step": "tls_certificate"})
    monkeypatch.setattr(api, "_tls_diagnostic", tls)
    monkeypatch.setattr(api, "record_audit_event", Mock())

    api.diagnose_tls(7, db, SimpleNamespace(id=1))

    assert tls.call_args.kwargs["ca_trust_path"] == "/protected/device-ca.pem"


def test_invalid_explicit_trust_prevents_transport_construction(monkeypatch):
    monkeypatch.setattr(api, "_effective_ca_path", Mock(side_effect=HTTPException(status_code=502, detail="Windows CA trust configuration is unavailable")))
    factory = Mock()
    monkeypatch.setattr(api, "WindowsCIMClient", factory)
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=_connection()))

    with pytest.raises(HTTPException):
        api._metric_client(Mock(), 7, SimpleNamespace(id=1))
    factory.assert_not_called()


def test_connection_test_passes_resolved_ca_without_exposing_it(monkeypatch):
    db = Mock()
    credential = SimpleNamespace(id=3)
    device = SimpleNamespace(id=7, site_id=10)
    db.query.return_value.filter.return_value.first.return_value = credential
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "_effective_ca_path", Mock(return_value=TRUST.protected_path))
    test = Mock(return_value=WinRMConnectionDiagnostic(True, "success", "ok"))
    monkeypatch.setattr(api.service, "test_connection", test)
    monkeypatch.setattr(api, "_audit", Mock())

    result = api.test_connection(7, db, SimpleNamespace(id=1))

    assert result["ok"] is True
    assert "/protected/device-ca.pem" not in str(result)
    assert test.call_args.kwargs["ca_trust_path"] == "/protected/device-ca.pem"


@pytest.mark.parametrize("client_path", ["/protected/device-ca.pem"])
def test_system_fetch_uses_resolved_ca_for_cim(monkeypatch, client_path):
    device = SimpleNamespace(id=7, site_id=10)
    connection = _connection()
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection))
    monkeypatch.setattr(api, "_effective_ca_path", Mock(return_value=client_path))
    client = Mock(operating_system=Mock(return_value=[SimpleNamespace(hostname="WIN")]))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    monkeypatch.setattr(api, "_upsert_system_snapshot", Mock(return_value=SimpleNamespace(id=1, device_id=7, collected_at=None, system_info={}, cpu={}, memory={}, disks=[])))
    monkeypatch.setattr(api, "record_audit_event", Mock())
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True

    api.fetch_system_info(7, db, SimpleNamespace(id=1))

    assert api.WindowsCIMClient.call_args.kwargs["trusted_ca_path"] == client_path


def test_internal_cim_fallback_receives_existing_trust_path(monkeypatch):
    source = open("hardik/backend/windows_monitoring/cim.py", encoding="utf-8").read()
    assert "ca_trust_path=self.trusted_ca_path" in source
    assert "trusted_ca_path=_effective_ca_path" in open("hardik/backend/windows_monitoring/api.py", encoding="utf-8").read()
