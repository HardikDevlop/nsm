from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.schemas import WindowsThresholdConfigBase


def _device(device_id=7, device_type="Windows Server", deleted_at=None):
    device_type_value = None if device_type is None else SimpleNamespace(name=device_type)
    return SimpleNamespace(id=device_id, site_id=10, device_type=device_type_value, deleted_at=deleted_at)


def _config(device_id=7):
    now = datetime(2026, 1, 1)
    return SimpleNamespace(
        id=11, device_id=device_id, cpu_threshold=45, memory_threshold=55,
        disk_threshold=65, enabled=True, created_at=now, updated_at=now,
    )


def test_get_thresholds_returns_effective_defaults_without_writing(monkeypatch):
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    device = _device()
    monkeypatch.setattr(api, "_windows_device", Mock(return_value=device))

    result = api.get_thresholds(device.id, db, SimpleNamespace())

    assert result.device_id == device.id
    assert result.cpu_threshold == 40
    assert result.memory_threshold == 40
    assert result.disk_threshold == 40
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_get_thresholds_returns_saved_device_scoped_values(monkeypatch):
    db = Mock()
    saved = _config(device_id=8)
    db.query.return_value.filter.return_value.first.return_value = saved
    monkeypatch.setattr(api, "_windows_device", Mock(return_value=_device(device_id=8)))

    result = api.get_thresholds(8, db, SimpleNamespace())

    assert result is saved
    assert result.cpu_threshold == 45


def test_threshold_routes_reject_non_windows_devices(monkeypatch):
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(api, "_device", Mock(return_value=_device(device_type="Linux")))
    with pytest.raises(HTTPException) as error:
        api._windows_device(db, 7, SimpleNamespace())
    assert error.value.status_code == 404


def test_windows_device_with_null_type_and_credential_is_accepted(monkeypatch):
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(device_id=356, enabled=False)
    device = _device(device_id=356, device_type=None)
    monkeypatch.setattr(api, "_device", Mock(return_value=device))

    assert api._windows_device(db, 356, SimpleNamespace()) is device


def test_deleted_device_keeps_device_helper_404(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as error:
        api._windows_device(Mock(), 7, SimpleNamespace())
    assert error.value.status_code == 404


def test_unauthorized_site_keeps_device_helper_404(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as error:
        api._windows_device(Mock(), 7, SimpleNamespace())
    assert error.value.status_code == 404


def test_put_thresholds_uses_device_scoped_upsert_and_commits(monkeypatch):
    class Insert:
        def values(self, **values):
            self.values_payload = values
            return self

        def on_conflict_do_update(self, **kwargs):
            self.conflict = kwargs
            return self

        def returning(self, column):
            return self

    insert = Insert()
    db = Mock()
    db.execute.return_value.scalar_one.return_value = 11
    db.query.return_value.filter.return_value.one.return_value = _config()
    monkeypatch.setattr(api, "_windows_device", Mock(return_value=_device()))
    monkeypatch.setattr(api, "pg_insert", Mock(return_value=insert))
    monkeypatch.setattr(api, "record_audit_event", Mock())

    result = api.put_thresholds(
        7,
        WindowsThresholdConfigBase(cpu_threshold=41, memory_threshold=42, disk_threshold=43),
        db,
        SimpleNamespace(id=1),
    )

    assert result.device_id == 7
    assert insert.values_payload["device_id"] == 7
    assert insert.values_payload["cpu_threshold"] == 41
    db.commit.assert_called_once()


def test_threshold_schema_rejects_invalid_values():
    with pytest.raises(ValueError):
        WindowsThresholdConfigBase(cpu_threshold=0)
