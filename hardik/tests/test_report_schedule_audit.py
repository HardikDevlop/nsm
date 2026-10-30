from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import routes
from backend.models import ReportSchedule
from backend.schemas.nms import ReportScheduleCreate, ReportScheduleUpdate


class _Query:
    def __init__(self, item):
        self.item = item

    def filter(self, *args):
        return self

    def first(self):
        return self.item


class _DB:
    def __init__(self, item=None):
        self.item = item
        self.deleted = None
        self.commits = 0

    def query(self, model):
        return _Query(self.item)

    def add(self, item):
        if isinstance(item, ReportSchedule) and item.id is None:
            item.id = 101

    def delete(self, item):
        self.deleted = item

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        return item


def _user():
    return SimpleNamespace(id=7, role=SimpleNamespace(role_name="Admin"))


def _schedule(schedule_id=101):
    return SimpleNamespace(
        id=schedule_id,
        name="Daily report",
        enabled=False,
        frequency="daily",
        run_time="09:30",
        timezone="Asia/Kolkata",
        report_format="csv",
        filters={"site_id": 12, "device_id": 4, "secret": "must-not-log"},
        created_by=7,
    )


def test_create_schedule_records_one_safe_audit_event(monkeypatch):
    events = []
    monkeypatch.setattr(routes, "_validate_schedule_scope", lambda *args: None)
    monkeypatch.setattr(routes, "sync_report_schedule", lambda item: None)
    monkeypatch.setattr(routes, "record_audit_event", lambda db, **kwargs: events.append(kwargs))
    db = _DB()

    result = routes.create_report_schedule(
        ReportScheduleCreate(name="Daily report", frequency="daily", run_time="09:30", filters={"site_id": 12}),
        db,
        _user(),
    )

    assert result.id == 101
    assert len(events) == 1
    event = events[0]
    assert event["action"] == "REPORT_SCHEDULE_CREATED"
    assert event["actor"].id == 7
    assert event["resource_type"] == "report_schedule"
    assert event["resource_id"] == 101
    assert event["site_id"] == 12
    assert event["outcome"] == "SUCCESS"
    assert "secret" not in str(event["new_values"])


def test_update_schedule_records_old_and_new_safe_values(monkeypatch):
    events = []
    schedule = _schedule()
    db = _DB(schedule)
    monkeypatch.setattr(routes, "_authorize_schedule_access", lambda *args: None)
    monkeypatch.setattr(routes, "_validate_schedule_scope", lambda *args: None)
    monkeypatch.setattr(routes, "sync_report_schedule", lambda item: None)
    monkeypatch.setattr(routes, "record_audit_event", lambda db, **kwargs: events.append(kwargs))

    routes.update_report_schedule(101, ReportScheduleUpdate(enabled=True, name="Updated"), db, _user())

    assert len(events) == 1
    event = events[0]
    assert event["action"] == "REPORT_SCHEDULE_UPDATED"
    assert event["resource_id"] == 101
    assert event["old_values"]["name"] == "Daily report"
    assert event["new_values"]["name"] == "Updated"
    assert event["old_values"]["enabled"] is False
    assert event["new_values"]["enabled"] is True
    assert "secret" not in str(event)


def test_delete_schedule_records_one_event_after_commit(monkeypatch):
    events = []
    schedule = _schedule()
    db = _DB(schedule)
    monkeypatch.setattr(routes, "_authorize_schedule_access", lambda *args: None)
    monkeypatch.setattr(routes, "remove_report_schedule", lambda schedule_id: None)
    monkeypatch.setattr(routes, "record_audit_event", lambda db, **kwargs: events.append((db.commits, kwargs)))

    result = routes.delete_report_schedule(101, db, _user())

    assert result is None
    assert len(events) == 1
    commit_count, event = events[0]
    assert commit_count == 1
    assert event["action"] == "REPORT_SCHEDULE_DELETED"
    assert event["resource_id"] == 101
    assert event["old_values"]["name"] == "Daily report"
    assert event["outcome"] == "SUCCESS"


def test_failed_update_does_not_record_audit(monkeypatch):
    events = []
    schedule = _schedule()
    db = _DB(schedule)
    monkeypatch.setattr(routes, "_authorize_schedule_access", lambda *args: None)
    monkeypatch.setattr(routes, "_validate_schedule_scope", lambda *args: (_ for _ in ()).throw(HTTPException(404, "scope")))
    monkeypatch.setattr(routes, "record_audit_event", lambda db, **kwargs: events.append(kwargs))

    with pytest.raises(HTTPException):
        routes.update_report_schedule(101, ReportScheduleUpdate(enabled=True), db, _user())

    assert events == []
    assert db.commits == 0
