from types import SimpleNamespace

import pytest

from backend.models import Device, User
from backend.services import report_schedule


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args):
        return self

    def first(self):
        return self.value


class _DB:
    def __init__(self, user=None, device=None):
        self.user = user
        self.device = device

    def query(self, model):
        return _Query(self.user if model is User else self.device)


def _user(status="active", role_name="Admin", sites=(10,), authority=80):
    role = SimpleNamespace(role_name=role_name, is_system_role=role_name == "Super Admin", authority_level=authority)
    return SimpleNamespace(id=7, status=status, role=role, sites=[SimpleNamespace(id=value) for value in sites])


def _schedule(created_by=7, filters=None):
    return SimpleNamespace(created_by=created_by, filters=filters or {"site_id": 10})


def test_active_creator_with_authorized_site_is_allowed(monkeypatch):
    creator = _user()
    monkeypatch.setattr(report_schedule, "get_accessible_site_ids", lambda user: {10})
    monkeypatch.setattr(report_schedule, "can_access_site", lambda user, site: site == 10)

    report_schedule._authorize_schedule_execution(_DB(user=creator), _schedule())


@pytest.mark.parametrize("status", ["disabled", "blocked", "locked", "inactive"])
def test_inactive_creator_is_denied(monkeypatch, status):
    monkeypatch.setattr(report_schedule, "get_accessible_site_ids", lambda user: {10})

    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(_DB(user=_user(status=status)), _schedule())


def test_missing_creator_and_ownerless_schedule_are_denied():
    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(_DB(user=None), _schedule(created_by=None))
    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(_DB(user=None), _schedule(created_by=99))


def test_creator_losing_site_access_is_denied(monkeypatch):
    monkeypatch.setattr(report_schedule, "get_accessible_site_ids", lambda user: set())
    monkeypatch.setattr(report_schedule, "can_access_site", lambda user, site: False)

    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(_DB(user=_user(sites=())), _schedule())


def test_invalid_device_and_mismatched_site_are_denied(monkeypatch):
    monkeypatch.setattr(report_schedule, "get_accessible_site_ids", lambda user: {10})
    monkeypatch.setattr(report_schedule, "can_access_site", lambda user, site: site == 10)

    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(_DB(user=_user(), device=None), _schedule(filters={"device_id": 3}))
    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(
            _DB(user=_user(), device=SimpleNamespace(site_id=10)),
            _schedule(filters={"site_id": 11, "device_id": 3}),
        )


def test_restricted_broad_scope_is_denied(monkeypatch):
    monkeypatch.setattr(report_schedule, "get_accessible_site_ids", lambda user: {10})

    with pytest.raises(report_schedule.ReportScheduleAuthorizationError):
        report_schedule._authorize_schedule_execution(_DB(user=_user()), _schedule(filters={"device_type_id": 4}))


def test_super_admin_creator_can_use_unrestricted_scope(monkeypatch):
    creator = _user(role_name="Super Admin", sites=(), authority=100)
    monkeypatch.setattr(report_schedule, "get_accessible_site_ids", lambda user: None)
    monkeypatch.setattr(report_schedule, "is_super_admin", lambda user: True)

    report_schedule._authorize_schedule_execution(_DB(user=creator), _schedule(filters={}))
