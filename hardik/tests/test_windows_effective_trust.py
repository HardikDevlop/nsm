from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from backend.windows_monitoring import effective_trust
from backend.windows_monitoring.effective_trust import EffectiveTrustError, normalize_windows_timestamp, resolve_effective_windows_ca
from backend.windows_monitoring.models import WindowsCABundleStatus, WindowsDeviceCAAssignment


def _assignment(bundle_id=12):
    return WindowsDeviceCAAssignment(device_id=7, ca_bundle_id=bundle_id)


def _bundle(status=WindowsCABundleStatus.ACTIVE.value, expires=None):
    return SimpleNamespace(id=12, site_id=10, status=status, not_after=expires, storage_key="ca-deadbeef.pem", sha256_fingerprint="fp")


def _db():
    db = Mock()
    db.get.return_value = SimpleNamespace(id=7, site_id=10)
    return db


def test_per_device_assignment_overrides_global(monkeypatch):
    db = _db()
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(return_value=_assignment()))
    monkeypatch.setattr(effective_trust, "get_ca_bundle", Mock(return_value=_bundle()))
    monkeypatch.setattr(effective_trust, "resolve_storage_path", Mock(return_value="/protected/ca.pem"))

    result = resolve_effective_windows_ca(7, db, global_ca_path="/global.pem")

    assert result.source == "per_device"
    assert result.bundle_id == 12
    assert result.protected_path == "/protected/ca.pem"


def test_global_and_system_fallbacks(monkeypatch):
    db = _db()
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(return_value=None))
    assert resolve_effective_windows_ca(7, db, global_ca_path="/global.pem").source == "global"
    result = resolve_effective_windows_ca(7, db, global_ca_path="")
    assert result.source == "system" and result.protected_path == ""


@pytest.mark.parametrize("bundle", [
    _bundle(status=WindowsCABundleStatus.REVOKED.value),
    _bundle(status=WindowsCABundleStatus.INVALID.value),
    _bundle(expires=datetime.now(timezone.utc) - timedelta(days=1)),
])
def test_invalid_explicit_assignment_fails_closed(monkeypatch, bundle):
    db = _db()
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(return_value=_assignment()))
    monkeypatch.setattr(effective_trust, "get_ca_bundle", Mock(return_value=bundle))
    with pytest.raises(EffectiveTrustError):
        resolve_effective_windows_ca(7, db, global_ca_path="/global.pem")


def test_missing_or_unsafe_assigned_storage_fails_closed(monkeypatch):
    db = _db()
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(return_value=_assignment()))
    monkeypatch.setattr(effective_trust, "get_ca_bundle", Mock(return_value=_bundle()))
    monkeypatch.setattr(effective_trust, "resolve_storage_path", Mock(side_effect=effective_trust.CABundleStorageError("unsafe")))
    with pytest.raises(EffectiveTrustError):
        resolve_effective_windows_ca(7, db, global_ca_path="/global.pem")


def test_unrelated_database_error_is_not_treated_as_missing_migration(monkeypatch):
    db = _db()
    error = RuntimeError("database unavailable")
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(side_effect=error))
    with pytest.raises(RuntimeError, match="database unavailable"):
        resolve_effective_windows_ca(7, db, global_ca_path="/global.pem")


def test_trust_object_contains_no_secret_material():
    result = effective_trust.EffectiveWindowsCATrust("global", None, "fp", "/protected/ca.pem", None)
    assert result.bundle_id is None
    assert "password" not in str(result).lower()
    assert "private" not in str(result).lower()


@pytest.mark.parametrize("value", [
    datetime(2026, 10, 26, 12, 0, 0),
    datetime(2026, 10, 26, 6, 30, 0, tzinfo=timezone.utc),
    datetime(2026, 10, 26, 14, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
])
def test_timestamp_normalization_produces_aware_utc(value):
    result = normalize_windows_timestamp(value)
    assert result.tzinfo == timezone.utc


def test_timestamp_normalization_rejects_invalid_values():
    with pytest.raises(EffectiveTrustError):
        normalize_windows_timestamp("not-a-timestamp")


def test_naive_expired_assignment_fails_closed(monkeypatch):
    db = _db()
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(return_value=_assignment()))
    monkeypatch.setattr(effective_trust, "get_ca_bundle", Mock(return_value=_bundle(expires=datetime(2020, 1, 1))))
    with pytest.raises(EffectiveTrustError):
        resolve_effective_windows_ca(7, db, global_ca_path="/global.pem")


def test_exact_expiry_boundary_is_expired(monkeypatch):
    db = _db()
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    monkeypatch.setattr(effective_trust, "windows_now", lambda: now)
    monkeypatch.setattr(effective_trust, "get_active_device_ca_assignment", Mock(return_value=_assignment()))
    monkeypatch.setattr(effective_trust, "get_ca_bundle", Mock(return_value=_bundle(expires=now)))
    with pytest.raises(EffectiveTrustError):
        resolve_effective_windows_ca(7, db, global_ca_path="/global.pem")
