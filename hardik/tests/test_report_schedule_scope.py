from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import routes
from backend.models import Device
from backend.schemas.nms import ReportManagementFilters, ReportScheduleUpdate


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.value


class _DB:
    def __init__(self, device=None, schedule=None):
        self.device = device
        self.schedule = schedule
        self.commits = 0

    def query(self, model):
        return _Query(self.device if model is Device else self.schedule)

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        return item


def _user():
    return SimpleNamespace(id=7)


def _restricted_scope(monkeypatch, sites=(10,)):
    monkeypatch.setattr(routes, "get_accessible_site_ids", lambda user: set(sites))
    monkeypatch.setattr(routes, "can_access_site", lambda user, site_id: site_id in sites)


def test_authorized_site_schedule_scope_is_accepted(monkeypatch):
    _restricted_scope(monkeypatch)
    monkeypatch.setattr(routes, "_validate_report_scope", lambda *args: None)

    routes._validate_schedule_scope(_user(), _DB(), ReportManagementFilters(site_id=10))


def test_unauthorized_site_is_rejected(monkeypatch):
    _restricted_scope(monkeypatch)
    monkeypatch.setattr(
        routes,
        "_validate_report_scope",
        lambda *args: (_ for _ in ()).throw(HTTPException(404, "Report scope not found")),
    )

    with pytest.raises(HTTPException):
        routes._validate_schedule_scope(_user(), _DB(), ReportManagementFilters(site_id=99))


def test_unauthorized_device_is_rejected(monkeypatch):
    _restricted_scope(monkeypatch)
    device = SimpleNamespace(site_id=99)
    monkeypatch.setattr(routes, "_validate_report_scope", lambda *args: None)

    with pytest.raises(HTTPException):
        routes._validate_schedule_scope(_user(), _DB(device=device), ReportManagementFilters(device_id=5))


def test_mismatched_site_and_device_are_rejected(monkeypatch):
    _restricted_scope(monkeypatch)
    device = SimpleNamespace(site_id=10)
    monkeypatch.setattr(routes, "_validate_report_scope", lambda *args: None)

    with pytest.raises(HTTPException):
        routes._validate_schedule_scope(_user(), _DB(device=device), ReportManagementFilters(site_id=20, device_id=5))


def test_restricted_user_must_supply_site_or_device(monkeypatch):
    _restricted_scope(monkeypatch)
    monkeypatch.setattr(routes, "_validate_report_scope", lambda *args: None)

    with pytest.raises(HTTPException):
        routes._validate_schedule_scope(_user(), _DB(), ReportManagementFilters())


def test_broad_device_type_filter_without_boundary_is_rejected(monkeypatch):
    _restricted_scope(monkeypatch)
    monkeypatch.setattr(routes, "_validate_report_scope", lambda *args: None)

    with pytest.raises(HTTPException):
        routes._validate_schedule_scope(_user(), _DB(), ReportManagementFilters(device_type_id=3))


def test_super_admin_can_create_unrestricted_schedule(monkeypatch):
    monkeypatch.setattr(routes, "get_accessible_site_ids", lambda user: None)
    monkeypatch.setattr(routes, "_validate_report_scope", lambda *args: None)

    routes._validate_schedule_scope(_user(), _DB(), ReportManagementFilters())


def test_update_rejects_scope_before_commit(monkeypatch):
    schedule = SimpleNamespace(filters={"site_id": 99}, name="existing", created_by=7)
    db = _DB(schedule=schedule)
    monkeypatch.setattr(
        routes,
        "_validate_schedule_scope",
        lambda *args: (_ for _ in ()).throw(HTTPException(404, "Report scope not found")),
    )

    with pytest.raises(HTTPException):
        routes.update_report_schedule(1, ReportScheduleUpdate(enabled=True), db, _user())

    assert schedule.name == "existing"
    assert schedule.filters == {"site_id": 99}
    assert db.commits == 0


def test_non_owner_and_ownerless_schedule_are_denied(monkeypatch):
    _restricted_scope(monkeypatch)
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)
    monkeypatch.setattr(routes, "_validate_schedule_scope", lambda *args: None)

    for created_by in (8, None):
        schedule = SimpleNamespace(created_by=created_by, filters={"site_id": 10})
        with pytest.raises(HTTPException):
            routes._authorize_schedule_access(_user(), _DB(), schedule)


def test_owner_with_lost_scope_is_denied(monkeypatch):
    _restricted_scope(monkeypatch, sites=())
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)
    schedule = SimpleNamespace(created_by=7, filters={"site_id": 10})
    monkeypatch.setattr(
        routes,
        "_validate_schedule_scope",
        lambda *args: (_ for _ in ()).throw(HTTPException(404, "Report scope not found")),
    )

    with pytest.raises(HTTPException):
        routes._authorize_schedule_access(_user(), _DB(), schedule)


def test_super_admin_can_access_any_schedule(monkeypatch):
    monkeypatch.setattr(routes, "is_super_admin", lambda user: True)
    schedule = SimpleNamespace(created_by=None, filters={})

    routes._authorize_schedule_access(_user(), _DB(), schedule)
