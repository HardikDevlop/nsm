from datetime import datetime

import pytest
from pydantic import ValidationError

from backend.windows_monitoring.models import WindowsThresholdConfig
from backend.windows_monitoring.schemas import (
    WindowsThresholdConfigCreate,
    WindowsThresholdConfigRead,
    WindowsThresholdConfigUpdate,
)


def test_threshold_defaults_are_40_and_enabled():
    payload = WindowsThresholdConfigCreate(device_id=315)

    assert payload.cpu_threshold == 40
    assert payload.memory_threshold == 40
    assert payload.disk_threshold == 40
    assert payload.enabled is True
    assert WindowsThresholdConfig.__table__.c.cpu_threshold.default.arg == 40
    assert WindowsThresholdConfig.__table__.c.memory_threshold.default.arg == 40
    assert WindowsThresholdConfig.__table__.c.disk_threshold.default.arg == 40
    assert WindowsThresholdConfig.__table__.c.enabled.default.arg is True


@pytest.mark.parametrize("field", ["cpu_threshold", "memory_threshold", "disk_threshold"])
@pytest.mark.parametrize("value", [1, 100])
def test_threshold_boundaries_are_valid(field, value):
    payload = WindowsThresholdConfigCreate(device_id=1, **{field: value})
    assert getattr(payload, field) == value


@pytest.mark.parametrize("field", ["cpu_threshold", "memory_threshold", "disk_threshold"])
@pytest.mark.parametrize("value", [0, 100.1])
def test_threshold_values_outside_range_are_rejected(field, value):
    with pytest.raises(ValidationError):
        WindowsThresholdConfigCreate(device_id=1, **{field: value})


def test_update_schema_validates_partial_updates():
    assert WindowsThresholdConfigUpdate(cpu_threshold=55).cpu_threshold == 55
    with pytest.raises(ValidationError):
        WindowsThresholdConfigUpdate(disk_threshold=0)


def test_threshold_model_has_device_foreign_key_and_unique_constraint():
    column = WindowsThresholdConfig.__table__.c.device_id
    assert any(fk.target_fullname == "devices.id" for fk in column.foreign_keys)
    assert any(
        constraint.columns.keys() == ["device_id"]
        for constraint in WindowsThresholdConfig.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_read_schema_supports_orm_objects():
    class Config:
        id = 1
        device_id = 2
        cpu_threshold = 40
        memory_threshold = 50
        disk_threshold = 60
        enabled = True
        created_at = datetime(2026, 1, 1)
        updated_at = datetime(2026, 1, 2)

    result = WindowsThresholdConfigRead.model_validate(Config())
    assert result.device_id == 2
    assert result.disk_threshold == 60
