from sqlalchemy import CheckConstraint

from backend.database.isolated_realtime_schemas import (
    REALTIME_MONITOR_OWNERSHIP_STATES,
    metadata,
    realtime_monitor_ownership,
    realtime_notification_outbox,
)


def _checks(table):
    return {constraint.name: str(constraint.sqltext) for constraint in table.constraints if isinstance(constraint, CheckConstraint)}


def test_isolated_tables_have_expected_columns_and_constraints():
    assert {column.name for column in realtime_monitor_ownership.c} == {
        "worker_name", "epoch", "owner_token", "state", "lease_expires_at", "created_at", "updated_at"
    }
    assert {column.name for column in realtime_notification_outbox.c} == {
        "id", "event_key", "alert_id", "channel", "recipient", "payload", "status",
        "attempt_count", "next_attempt_at", "claimed_by", "claimed_until", "last_error", "created_at", "sent_at"
    }
    ownership_checks = _checks(realtime_monitor_ownership)
    assert "epoch >= 0" in ownership_checks["ck_realtime_ownership_epoch_nonnegative"]
    assert "state IN" in ownership_checks["ck_realtime_ownership_state_valid"]
    assert "owner_token" in ownership_checks["ck_realtime_ownership_token_matches_state"]
    assert "lease_expires_at" in ownership_checks["ck_realtime_ownership_token_matches_state"]
    outbox_checks = _checks(realtime_notification_outbox)
    assert "status IN" in outbox_checks["ck_realtime_outbox_status_valid"]
    assert "attempt_count >= 0" in outbox_checks["ck_realtime_outbox_attempt_count_nonnegative"]
    assert "claimed_by" in outbox_checks["ck_realtime_outbox_claim_fields_match_status"]
    assert "sent_at" in outbox_checks["ck_realtime_outbox_sent_timestamp_required"]


def test_lifecycle_and_outbox_constraints_are_explicit():
    assert REALTIME_MONITOR_OWNERSHIP_STATES == (
        "stopped", "starting", "running", "stopping", "incomplete_stop", "lease_lost", "error"
    )
    assert realtime_monitor_ownership.c.epoch.server_default is not None
    assert realtime_notification_outbox.c.event_key.unique is True
    assert realtime_notification_outbox.c.attempt_count.server_default is not None
    foreign_keys = list(realtime_notification_outbox.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "alerts.id"
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_outbox_foreign_key_restricts_alert_deletion():
    foreign_key = next(iter(realtime_notification_outbox.c.alert_id.foreign_keys))
    assert foreign_key.ondelete == "RESTRICT"
    assert realtime_notification_outbox.c.alert_id.nullable is False


def test_required_indexes_exist():
    assert {index.name for index in realtime_monitor_ownership.indexes} == {
        "ix_realtime_monitor_ownership_lease_expires_at",
        "ix_realtime_monitor_ownership_state",
    }
    assert {index.name for index in realtime_notification_outbox.indexes} == {
        "ix_realtime_outbox_dispatch_due",
        "ix_realtime_outbox_claim_expiry",
        "ix_realtime_outbox_alert_id",
    }


def test_definitions_are_non_destructive_and_metadata_is_isolated():
    assert not any("DROP" in str(item).upper() for item in metadata.tables.values())
    assert set(metadata.tables) == {"realtime_monitor_ownership", "realtime_notification_outbox"}


def test_not_registered_with_runtime_migrations_or_startup():
    from backend.database.migrations import MIGRATIONS

    names = {migration.migration_id for migration in MIGRATIONS}
    assert "realtime_monitor_ownership" not in names
    assert "realtime_notification_outbox" not in names

