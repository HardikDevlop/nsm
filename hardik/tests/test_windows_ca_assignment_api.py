from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.ca_bundles_service import WindowsCABundleError


def _user():
    return SimpleNamespace(id=9)


def _device():
    return SimpleNamespace(id=7, site_id=10)


def _bundle():
    return SimpleNamespace(
        id=12, site_id=10, name="Corporate CA", sha256_fingerprint="SHA256-fingerprint",
        not_after=datetime(2027, 10, 26, tzinfo=timezone.utc), storage_key="ca-secret.pem",
    )


def _assignment():
    return SimpleNamespace(device_id=7, ca_bundle_id=12, unassigned_at=None)


def test_authorized_assignment_returns_metadata_only(monkeypatch):
    db = Mock()
    assignment, bundle = _assignment(), _bundle()
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=None))
    service = Mock()
    service.assign.return_value = assignment
    service.get.return_value = bundle
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    monkeypatch.setattr(api, "record_audit_event", Mock())

    result = api.assign_device_ca_bundle(7, 12, db, _user())

    assert result["bundle_id"] == 12
    assert result["fingerprint"] == "SHA256-fingerprint"
    assert "protected_path" not in result and "storage_key" not in result
    assert "pem" not in str(result).lower()
    db.commit.assert_called_once()


def test_unauthorized_assignment_uses_device_authorization(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.assign_device_ca_bundle(7, 12, Mock(), _user())
    assert exc.value.status_code == 404


@pytest.mark.parametrize("code", ["CA_BUNDLE_NOT_FOUND", "CA_BUNDLE_NOT_ASSIGNABLE", "CA_BUNDLE_EXPIRED"])
def test_assignment_rejects_cross_site_missing_revoked_or_expired(monkeypatch, code):
    db = Mock()
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=None))
    service = Mock()
    service.assign.side_effect = WindowsCABundleError(code, "safe failure")
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    with pytest.raises(HTTPException) as exc:
        api.assign_device_ca_bundle(7, 99, db, _user())
    assert exc.value.status_code in {404, 409}
    assert "safe failure" in exc.value.detail


def test_reassignment_unassigns_old_assignment_in_same_transaction(monkeypatch):
    db = Mock()
    old = _assignment()
    new = SimpleNamespace(device_id=7, ca_bundle_id=13, unassigned_at=None)
    bundle = _bundle()
    bundle.id = 13
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=old))
    service = Mock()
    service.assign.return_value = new
    service.get.return_value = bundle
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    monkeypatch.setattr(api, "record_audit_event", Mock())

    api.assign_device_ca_bundle(7, 13, db, _user())

    assert old.unassigned_at is not None
    db.flush.assert_called_once()
    db.commit.assert_called_once()


def test_unassignment_is_audited_without_sensitive_metadata(monkeypatch):
    db = Mock()
    assignment = _assignment()
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    service = Mock()
    service.unassign.return_value = assignment
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.unassign_device_ca_bundle(7, db, _user())

    assert result["trust_source"] == "global"
    assert "storage" not in str(result).lower()
    assert "path" not in str(result).lower()
    assert audit.call_args.kwargs["metadata"] == {"bundle_id": 12}


def test_get_assignment_does_not_expose_storage_reference(monkeypatch):
    db = Mock()
    monkeypatch.setattr(api, "_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=_assignment()))
    service = Mock()
    service.get.return_value = _bundle()
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    monkeypatch.setattr(api, "resolve_effective_windows_ca", Mock(return_value=SimpleNamespace()))

    result = api.get_device_ca_bundle(7, db, _user())

    assert result["bundle_name"] == "Corporate CA"
    assert "storage_key" not in result
    assert "ca-secret.pem" not in str(result)
