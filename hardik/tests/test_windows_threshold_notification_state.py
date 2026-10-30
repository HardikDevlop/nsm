from datetime import datetime

from backend.database.migrations import MIGRATIONS
from backend.windows_monitoring.models import WindowsThresholdNotificationState
from backend.windows_monitoring.schemas import WindowsThresholdNotificationStateRead


def test_notification_state_model_is_independent_and_device_scoped():
    table = WindowsThresholdNotificationState.__table__
    assert table.name == "windows_threshold_notification_states"
    assert not {"alert_id", "notification_id", "incident_id"}.intersection(table.c.keys())
    assert any(fk.target_fullname == "devices.id" for fk in table.c.device_id.foreign_keys)
    assert any(
        constraint.columns.keys() == ["device_id", "metric_name"]
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_notification_state_has_metric_and_state_constraints():
    constraints = {constraint.name: str(constraint.sqltext) for constraint in WindowsThresholdNotificationState.__table__.constraints if constraint.__class__.__name__ == "CheckConstraint"}
    assert "'cpu'" in constraints["ck_windows_threshold_notification_states_metric"]
    assert "'warning'" in constraints["ck_windows_threshold_notification_states_state"]


def test_notification_state_read_schema_maps_orm_values():
    class State:
        id = 1
        device_id = 7
        metric_name = "memory"
        state = "warning"
        last_value = 74.8
        threshold_at_transition = 40
        last_transition_at = datetime(2026, 1, 1)
        last_error = None
        created_at = datetime(2026, 1, 1)
        updated_at = datetime(2026, 1, 2)

    result = WindowsThresholdNotificationStateRead.model_validate(State())
    assert result.device_id == 7
    assert result.state == "warning"


def test_notification_state_migration_follows_threshold_config():
    ids = [migration.migration_id for migration in MIGRATIONS]
    assert ids.index("20261027_0068_windows_threshold_configs") < ids.index(
        "20261027_0069_windows_threshold_notification_states"
    )
    migration = next(item for item in MIGRATIONS if item.migration_id.endswith("0069_windows_threshold_notification_states"))
    assert "independent Windows threshold notification state" in migration.description
