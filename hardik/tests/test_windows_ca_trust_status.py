import pytest
from types import SimpleNamespace
from unittest.mock import Mock

pytest.importorskip("pypsrp")

from backend.windows_monitoring import api
from backend.windows_monitoring.effective_trust import EffectiveTrustError


def _device():
    return SimpleNamespace(id=7, site_id=10)


def _setup(monkeypatch, resolved):
    db = Mock()
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=None))
    monkeypatch.setattr(api, "resolve_effective_windows_ca", Mock(return_value=resolved))
    return db


def test_empty_global_configuration_reports_system(monkeypatch):
    db = _setup(monkeypatch, SimpleNamespace(source="system", protected_path="", expires_at=None))
    result = api.get_device_ca_bundle(7, db, SimpleNamespace(id=1))
    assert result["trust_source"] == "system"


def test_valid_global_ca_reports_global(monkeypatch, tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----\n")
    # The API validates through ssl; use a mocked successful context here to
    # isolate response semantics from certificate fixture generation.
    monkeypatch.setattr(api.ssl, "create_default_context", Mock())
    db = _setup(monkeypatch, SimpleNamespace(source="global", protected_path=str(ca), expires_at=None))
    result = api.get_device_ca_bundle(7, db, SimpleNamespace(id=1))
    assert result["trust_source"] == "global"


def test_missing_or_invalid_global_ca_reports_unavailable(monkeypatch, tmp_path):
    missing = tmp_path / "missing.pem"
    db = _setup(monkeypatch, SimpleNamespace(source="global", protected_path=str(missing), expires_at=None))
    assert api.get_device_ca_bundle(7, db, SimpleNamespace(id=1))["trust_source"] == "unavailable"

    invalid = tmp_path / "invalid.pem"
    invalid.write_text("not a certificate")
    db = _setup(monkeypatch, SimpleNamespace(source="global", protected_path=str(invalid), expires_at=None))
    assert api.get_device_ca_bundle(7, db, SimpleNamespace(id=1))["trust_source"] == "unavailable"


def test_resolver_failure_reports_safe_unavailable(monkeypatch):
    db = Mock()
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=None))
    monkeypatch.setattr(api, "resolve_effective_windows_ca", Mock(side_effect=EffectiveTrustError("private path")))
    result = api.get_device_ca_bundle(7, db, SimpleNamespace(id=1))
    assert result["trust_source"] == "unavailable"
    assert "private" not in str(result).lower()
