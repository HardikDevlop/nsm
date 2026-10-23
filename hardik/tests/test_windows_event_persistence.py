from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.windows_monitoring.events import SystemEvent
from backend.windows_monitoring.models import WindowsEventLog
from backend.windows_monitoring.persistence import insert_system_events, list_system_events, save_system_events


def event(record_id=42, event_id=7036, level="Information", message="service changed"):
    return SystemEvent(record_id, "2026-10-17T12:00:00+00:00", event_id, "Service Control Manager", level, "WIN01", message, None)


def db_with_rowcount(rowcount=1):
    db = Mock()
    db.execute.return_value.scalars.return_value.all.return_value = list(range(rowcount))
    return db


def test_insert_system_events_uses_deduplicating_unique_key_and_sensitive_fields():
    db = db_with_rowcount(1)

    inserted = insert_system_events(db, 314, "System", [event()])

    assert inserted == 1
    statement = db.execute.call_args.args[0]
    assert statement.table.name == WindowsEventLog.__tablename__
    assert statement._post_values_clause is not None
    assert "uq_windows_event_logs_device_channel_record" in {constraint.name for constraint in statement.table.constraints}
    params = statement.compile().params
    assert 314 in params.values()
    assert "System" in params.values()


def test_duplicate_batch_is_safe_and_empty_batch_does_not_write():
    db = db_with_rowcount(0)
    assert insert_system_events(db, 314, "System", [event()]) == 0
    db.execute.reset_mock()
    assert insert_system_events(db, 314, "System", []) == 0
    db.execute.assert_not_called()


def test_mixed_batch_returns_only_newly_returned_record_ids():
    db = db_with_rowcount(2)

    inserted = insert_system_events(db, 314, "System", [event(1), event(2), event(3)])

    assert inserted == 2
    statement = db.execute.call_args.args[0]
    assert statement._returning


def test_failed_batch_rolls_back_without_commit():
    db = db_with_rowcount()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError):
        save_system_events(db, 314, "System", [event()])

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_event_fields_are_bounded_and_channel_is_allowlisted():
    db = db_with_rowcount()
    with pytest.raises(ValueError):
        insert_system_events(db, 314, "Security", [event()])
    with pytest.raises(ValueError):
        insert_system_events(db, 314, "System", [event(message="x" * 1_000_001)])
    with pytest.raises(ValueError):
        insert_system_events(db, 314, "System", [event()] * 501)


def test_list_system_events_builds_bounded_filters_and_pagination():
    db = Mock()
    db.scalars.return_value = [SimpleNamespace(record_id=42)]
    start = datetime(2026, 10, 17, tzinfo=timezone.utc)
    end = datetime(2026, 10, 18, tzinfo=timezone.utc)

    result = list_system_events(db, 314, start_time=start, end_time=end, event_ids=(7036,), level="Information", offset=20, limit=25)

    assert result[0].record_id == 42
    query = db.scalars.call_args.args[0]
    compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
    assert "windows_event_logs" in compiled
    assert "LIMIT" in compiled and "OFFSET" in compiled


def test_list_system_events_rejects_unbounded_or_invalid_filters():
    db = Mock()
    with pytest.raises(ValueError):
        list_system_events(db, 314, limit=501)
    with pytest.raises(ValueError):
        list_system_events(db, 314, event_ids=(1, -1))
