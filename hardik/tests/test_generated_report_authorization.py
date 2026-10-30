from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.api import routes
from backend.models import GeneratedReport, ReportSchedule


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, *args):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _DB:
    def __init__(self, reports=(), schedules=()):
        self.reports = list(reports)
        self.schedules = list(schedules)

    def query(self, model):
        return _Query(self.reports if model is GeneratedReport else self.schedules)


def _user(user_id=7):
    return SimpleNamespace(id=user_id)


def test_restricted_listing_excludes_non_owner_ownerless_and_orphaned(monkeypatch):
    owner_schedule = SimpleNamespace(id=10, created_by=7, filters={"site_id": 1})
    reports = [
        SimpleNamespace(id=1, schedule_id=10),
        SimpleNamespace(id=2, schedule_id=11),
        SimpleNamespace(id=3, schedule_id=None),
        SimpleNamespace(id=4, schedule_id=12),
    ]
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)
    monkeypatch.setattr(routes, "_authorize_schedule_access", lambda user, db, schedule: None)

    result = routes.list_generated_reports(db=_DB(reports, [owner_schedule]), current_user=_user())

    assert result == [reports[0]]


def test_restricted_download_denies_orphan_before_filesystem(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=None, status="SUCCESS", file_path=object())
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)

    with pytest.raises(HTTPException) as exc:
        routes.download_generated_report(1, _DB([item]), _user())

    assert exc.value.status_code == 404


def test_restricted_download_denies_non_owner_before_filesystem(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=10, status="SUCCESS", file_path=object())
    schedule = SimpleNamespace(id=10, created_by=8, filters={"site_id": 1})
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)

    with pytest.raises(HTTPException) as exc:
        routes.download_generated_report(1, _DB([item], [schedule]), _user())

    assert exc.value.status_code == 404


def test_super_admin_can_access_orphaned_legacy_report(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=None, status="FAILED", file_path=None)
    monkeypatch.setattr(routes, "is_super_admin", lambda user: True)

    with pytest.raises(HTTPException) as exc:
        routes.download_generated_report(1, _DB([item]), _user())

    assert exc.value.status_code == 404
    assert "filesystem" not in str(exc.value.detail).lower()


def test_owner_can_download_authorized_report(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=10, status="SUCCESS", format="csv", file_path="/tmp/report-root/report.csv")
    schedule = SimpleNamespace(id=10, created_by=7, filters={"site_id": 1})
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)
    monkeypatch.setattr(routes, "_authorize_schedule_access", lambda user, db, value: None)
    monkeypatch.setattr(routes, "REPORT_STORAGE_DIR", Path("/tmp/report-root"))
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(routes, "FileResponse", lambda path, **kwargs: (str(path), kwargs["filename"], kwargs["media_type"]))

    result = routes.download_generated_report(1, _DB([item], [schedule]), _user())

    assert result[1] == "report.csv"
    assert result[2] == "text/csv"


@pytest.mark.parametrize(
    ("report_format", "filename", "expected_media_type"),
    [
        ("csv", "report.csv", "text/csv"),
        ("xlsx", "report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pdf", "report.pdf", "application/pdf"),
    ],
)
def test_owner_download_uses_stored_format_media_type(monkeypatch, report_format, filename, expected_media_type):
    item = SimpleNamespace(id=1, schedule_id=10, status="SUCCESS", format=report_format, file_path=f"/tmp/report-root/{filename}")
    schedule = SimpleNamespace(id=10, created_by=7, filters={"site_id": 1})
    monkeypatch.setattr(routes, "is_super_admin", lambda user: False)
    monkeypatch.setattr(routes, "_authorize_schedule_access", lambda user, db, value: None)
    monkeypatch.setattr(routes, "REPORT_STORAGE_DIR", Path("/tmp/report-root"))
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(routes, "FileResponse", lambda path, **kwargs: kwargs)

    result = routes.download_generated_report(1, _DB([item], [schedule]), _user())

    assert result["filename"] == filename
    assert result["media_type"] == expected_media_type


def test_legacy_missing_format_defaults_to_csv(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=None, status="SUCCESS", file_path="/tmp/report-root/legacy.csv")
    monkeypatch.setattr(routes, "is_super_admin", lambda user: True)
    monkeypatch.setattr(routes, "REPORT_STORAGE_DIR", Path("/tmp/report-root"))
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(routes, "FileResponse", lambda path, **kwargs: kwargs)

    result = routes.download_generated_report(1, _DB([item]), _user())

    assert result["filename"] == "legacy.csv"
    assert result["media_type"] == "text/csv"


def test_unsupported_format_is_rejected_before_filesystem_access(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=None, status="SUCCESS", format="docx", file_path="/tmp/report-root/report.docx")
    monkeypatch.setattr(routes, "is_super_admin", lambda user: True)
    monkeypatch.setattr(routes, "REPORT_STORAGE_DIR", Path("/tmp/report-root"))
    monkeypatch.setattr(Path, "resolve", lambda self: pytest.fail("filesystem path must not be resolved"))

    with pytest.raises(HTTPException) as exc:
        routes.download_generated_report(1, _DB([item]), _user())

    assert exc.value.status_code == 404
    assert "format" in str(exc.value.detail).lower()


def test_missing_report_file_returns_not_found(monkeypatch, tmp_path):
    item = SimpleNamespace(id=1, schedule_id=None, status="SUCCESS", format="pdf", file_path=str(tmp_path / "missing.pdf"))
    monkeypatch.setattr(routes, "is_super_admin", lambda user: True)
    monkeypatch.setattr(routes, "REPORT_STORAGE_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        routes.download_generated_report(1, _DB([item]), _user())

    assert exc.value.status_code == 404
    assert "not found" in str(exc.value.detail).lower()


def test_path_containment_protection_remains_effective(monkeypatch):
    item = SimpleNamespace(id=1, schedule_id=None, status="SUCCESS", file_path="/etc/hosts")
    monkeypatch.setattr(routes, "is_super_admin", lambda user: True)
    monkeypatch.setattr(routes, "REPORT_STORAGE_DIR", Path("/tmp/report-root"))

    with pytest.raises(HTTPException) as exc:
        routes.download_generated_report(1, _DB([item]), _user())

    assert exc.value.status_code == 404
    assert "invalid" in str(exc.value.detail).lower()
