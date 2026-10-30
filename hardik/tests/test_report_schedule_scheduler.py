from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.models import GeneratedReport, ReportSchedule
from backend.schemas.nms import ReportScheduleCreate, ReportScheduleUpdate
from backend.services import report_schedule


def _schedule(frequency: str, timezone: str = "Asia/Kolkata"):
    return SimpleNamespace(frequency=frequency, timezone=timezone)


@pytest.mark.parametrize(
    ("frequency", "now", "expected"),
    [
        ("daily", datetime(2026, 1, 1, 8), (datetime(2025, 12, 31), datetime(2026, 1, 1))),
        ("weekly", datetime(2026, 1, 5, 8), (datetime(2025, 12, 29), datetime(2026, 1, 5))),
        ("monthly", datetime(2026, 1, 1, 8), (datetime(2025, 12, 1), datetime(2026, 1, 1))),
        ("monthly", datetime(2026, 3, 1, 8), (datetime(2026, 2, 1), datetime(2026, 3, 1))),
        ("monthly", datetime(2027, 1, 1, 8), (datetime(2026, 12, 1), datetime(2027, 1, 1))),
    ],
)
def test_report_window_boundaries(frequency, now, expected):
    assert report_schedule._window(_schedule(frequency), now) == expected


def test_report_window_uses_schedule_timezone(monkeypatch):
    utc_now = datetime(2026, 1, 1, 18, 45)

    assert report_schedule._window(_schedule("daily", "America/New_York"), utc_now) == (
        datetime(2025, 12, 31),
        datetime(2026, 1, 1),
    )


def test_invalid_timezone_falls_back_to_ist():
    assert report_schedule._tz("Not/A_Timezone").key == "Asia/Kolkata"
    assert report_schedule._tz(None).key == "Asia/Kolkata"


class _FakeJob:
    def __init__(self, next_run_time=None):
        self.next_run_time = next_run_time


class _FakeScheduler:
    def __init__(self, next_run_time=None):
        self.jobs = {}
        self.added = []
        self.removed = []
        self.next_run_time = next_run_time

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def remove_job(self, job_id):
        self.removed.append(job_id)
        self.jobs.pop(job_id, None)

    def add_job(self, function, trigger, args, id, replace_existing, max_instances, coalesce, misfire_grace_time):
        self.added.append({
            "function": function, "trigger": trigger, "args": args, "id": id,
            "replace_existing": replace_existing, "max_instances": max_instances,
            "coalesce": coalesce, "misfire_grace_time": misfire_grace_time,
        })
        self.jobs[id] = _FakeJob(self.next_run_time)
        return self.jobs[id]


def test_sync_registers_stable_job_and_prevents_duplicate_registration():
    scheduler = _FakeScheduler()
    report_schedule.set_report_scheduler(SimpleNamespace(scheduler=scheduler))
    schedule = SimpleNamespace(id=42, enabled=True, frequency="daily", run_time="09:30", timezone="Asia/Kolkata", next_run_at=None)

    report_schedule.sync_report_schedule(schedule)
    report_schedule.sync_report_schedule(schedule)

    assert scheduler.added[-1]["id"] == "report_schedule_42"
    assert scheduler.added[-1]["replace_existing"] is True
    assert scheduler.added[-1]["max_instances"] == 1
    assert scheduler.added[-1]["coalesce"] is True
    assert scheduler.removed == ["report_schedule_42"]


def test_disabled_schedule_clears_next_run_at_and_is_not_registered():
    scheduler = _FakeScheduler()
    report_schedule.set_report_scheduler(SimpleNamespace(scheduler=scheduler))
    schedule = SimpleNamespace(id=43, enabled=False, frequency="daily", run_time="09:30", timezone="Asia/Kolkata", next_run_at=datetime(2026, 10, 30, 11, 1))

    report_schedule.sync_report_schedule(schedule)

    assert scheduler.added == []
    assert schedule.next_run_at is None


def test_enabled_schedule_stores_next_run_at():
    next_run = datetime(2026, 10, 31, 3, 30, tzinfo=report_schedule._tz("Asia/Kolkata"))
    scheduler = _FakeScheduler(next_run)
    report_schedule.set_report_scheduler(SimpleNamespace(scheduler=scheduler))
    schedule = SimpleNamespace(id=44, enabled=True, frequency="daily", run_time="09:30", timezone="Asia/Kolkata", next_run_at=None)

    report_schedule.sync_report_schedule(schedule)

    assert schedule.next_run_at == datetime(2026, 10, 31, 3, 30)


def test_restore_registers_only_enabled_schedules(monkeypatch):
    scheduler = _FakeScheduler()
    report_schedule.set_report_scheduler(SimpleNamespace(scheduler=scheduler))
    enabled = SimpleNamespace(id=1, enabled=True, frequency="daily", run_time="09:00", timezone="Asia/Kolkata", next_run_at=None)
    disabled = SimpleNamespace(id=2, enabled=False, frequency="daily", run_time="09:00", timezone="Asia/Kolkata", next_run_at=None)

    class _Query:
        def all(self):
            return [enabled, disabled]

    class _DB:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def query(self, model): return _Query()
        def commit(self): pass

    monkeypatch.setattr(report_schedule, "SessionLocal", lambda: _DB())
    report_schedule.restore_report_schedules()

    assert [job["id"] for job in scheduler.added] == ["report_schedule_1"]
    assert disabled.next_run_at is None


def test_successful_execution_updates_next_run_at(monkeypatch, tmp_path):
    scheduler = _FakeScheduler()
    next_run = datetime(2026, 11, 1, 3, 30, tzinfo=report_schedule._tz("Asia/Kolkata"))
    scheduler.jobs["report_schedule_45"] = _FakeJob(next_run)
    report_schedule.set_report_scheduler(SimpleNamespace(scheduler=scheduler))
    schedule = SimpleNamespace(id=45, enabled=True, name="daily", frequency="daily", timezone="Asia/Kolkata", report_format="csv", filters={}, next_run_at=None)
    generated = GeneratedReport(schedule_id=45, report_name="daily", format="csv", status="RUNNING", period_start=datetime(2026, 1, 1), period_end=datetime(2026, 1, 2), generated_at=datetime(2026, 1, 2))
    generated.id = 104
    generated = _run_with_fake_db(monkeypatch, tmp_path, schedule, generated, [{"hostname": "router-1"}])

    assert generated.status == "SUCCESS"
    assert schedule.next_run_at == datetime(2026, 11, 1, 3, 30)


def test_missing_scheduler_or_job_does_not_crash():
    schedule = SimpleNamespace(id=46, enabled=True, timezone="Asia/Kolkata", next_run_at=datetime(2026, 1, 1))
    report_schedule.set_report_scheduler(None)
    report_schedule._sync_next_run_at(schedule)
    assert schedule.next_run_at == datetime(2026, 1, 1)

    scheduler = _FakeScheduler()
    report_schedule.set_report_scheduler(SimpleNamespace(scheduler=scheduler))
    report_schedule._sync_next_run_at(schedule)
    assert schedule.next_run_at is None


def test_unauthorized_schedule_fails_before_report_generation(monkeypatch, tmp_path):
    schedule = SimpleNamespace(id=7, enabled=True, name="restricted", frequency="daily", timezone="Asia/Kolkata", report_format="pdf", filters={})
    generated = GeneratedReport(schedule_id=7, report_name="restricted", format="pdf", status="RUNNING", period_start=datetime(2026, 1, 1), period_end=datetime(2026, 1, 2), generated_at=datetime(2026, 1, 2))
    generated.id = 99
    generated_rows = []

    class _Query:
        def __init__(self, model): self.model = model
        def filter(self, *args): return self
        def first(self): return schedule if self.model is ReportSchedule else generated

    class _DB:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def query(self, model): return _Query(model)
        def add(self, item): generated_rows.append(item)
        def commit(self): pass
        def refresh(self, item): pass
        def rollback(self): pass

    def deny(*args): raise report_schedule.ReportScheduleAuthorizationError("schedule scope is unauthorized")
    monkeypatch.setattr(report_schedule, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(report_schedule, "_authorize_schedule_execution", deny)
    monkeypatch.setattr(report_schedule, "build_report_rows", lambda *args: pytest.fail("report generation must not run"))
    monkeypatch.setattr(report_schedule, "generate_report_csv", lambda *args: pytest.fail("file generation must not run"))
    monkeypatch.setattr(report_schedule, "generate_report_pdf", lambda *args, **kwargs: pytest.fail("PDF generation must not run"))
    monkeypatch.setattr(report_schedule, "REPORT_STORAGE_DIR", Path(tmp_path))

    report_schedule._run_schedule(7)

    assert generated.status == "FAILED"
    assert list(tmp_path.iterdir()) == []


def _run_with_fake_db(monkeypatch, tmp_path, schedule, generated, rows, xlsx_error=None, pdf_error=None):
    added = []

    class _Query:
        def __init__(self, model): self.model = model
        def filter(self, *args): return self
        def first(self): return schedule if self.model is ReportSchedule else (added[0] if added else generated)

    class _DB:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def query(self, model): return _Query(model)
        def add(self, item): added.append(item)
        def commit(self): pass
        def refresh(self, item): pass
        def rollback(self): pass

    monkeypatch.setattr(report_schedule, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(report_schedule, "_authorize_schedule_execution", lambda *args: None)
    monkeypatch.setattr(report_schedule, "build_report_rows", lambda *args: (None, rows))
    if xlsx_error:
        monkeypatch.setattr(report_schedule, "generate_report_xlsx", lambda *args: (_ for _ in ()).throw(xlsx_error))
    if pdf_error:
        monkeypatch.setattr(report_schedule, "generate_report_pdf", lambda *args, **kwargs: (_ for _ in ()).throw(pdf_error))
    monkeypatch.setattr(report_schedule, "REPORT_STORAGE_DIR", Path(tmp_path))
    report_schedule._run_schedule(schedule.id)
    return added[0]


def test_schedule_formats_accept_csv_and_xlsx_with_csv_default():
    assert ReportScheduleCreate(name="CSV", frequency="daily", run_time="09:00").report_format == "csv"
    assert ReportScheduleCreate(name="XLSX", frequency="daily", run_time="09:00", report_format="xlsx").report_format == "xlsx"
    assert ReportScheduleUpdate(report_format="xlsx").report_format == "xlsx"
    assert ReportScheduleCreate(name="PDF", frequency="daily", run_time="09:00", report_format="pdf").report_format == "pdf"
    assert ReportScheduleUpdate(report_format="pdf").report_format == "pdf"


def test_successful_xlsx_generation_has_headers_values_and_metadata(monkeypatch, tmp_path):
    load_workbook = pytest.importorskip("openpyxl").load_workbook
    schedule = SimpleNamespace(id=8, enabled=True, name="xlsx", frequency="daily", timezone="Asia/Kolkata", report_format="xlsx", filters={})
    generated = GeneratedReport(schedule_id=8, report_name="xlsx", format="xlsx", status="RUNNING", period_start=datetime(2026, 1, 1), period_end=datetime(2026, 1, 2), generated_at=datetime(2026, 1, 2))
    generated.id = 100
    generated = _run_with_fake_db(monkeypatch, tmp_path, schedule, generated, [{"hostname": "router-1", "availability_pct": 99.5}])

    assert generated.status == "SUCCESS"
    assert generated.format == "xlsx"
    assert generated.file_path.endswith(".xlsx")
    assert generated.file_size > 0
    workbook = load_workbook(generated.file_path, read_only=True)
    assert list(workbook.active.values) == [("hostname", "availability_pct"), ("router-1", 99.5)]


def test_xlsx_generation_failure_records_failed(monkeypatch, tmp_path):
    schedule = SimpleNamespace(id=9, enabled=True, name="xlsx", frequency="daily", timezone="Asia/Kolkata", report_format="xlsx", filters={})
    generated = GeneratedReport(schedule_id=9, report_name="xlsx", format="xlsx", status="RUNNING", period_start=datetime(2026, 1, 1), period_end=datetime(2026, 1, 2), generated_at=datetime(2026, 1, 2))
    generated.id = 101
    generated = _run_with_fake_db(monkeypatch, tmp_path, schedule, generated, [{"hostname": "router-1"}], RuntimeError("xlsx failed"))

    assert generated.status == "FAILED"
    assert generated.file_path is None
    assert list(tmp_path.iterdir()) == []


def test_successful_pdf_generation_has_signature_and_metadata(monkeypatch, tmp_path):
    schedule = SimpleNamespace(id=10, enabled=True, name="Management PDF", frequency="daily", timezone="Asia/Kolkata", report_format="pdf", filters={})
    generated = GeneratedReport(schedule_id=10, report_name="Management PDF", format="pdf", status="RUNNING", period_start=datetime(2026, 1, 1), period_end=datetime(2026, 1, 2), generated_at=datetime(2026, 1, 2))
    generated.id = 102
    generated = _run_with_fake_db(monkeypatch, tmp_path, schedule, generated, [{"hostname": "router-1", "availability_pct": 99.5}])

    assert generated.status == "SUCCESS"
    assert generated.format == "pdf"
    assert generated.file_path.endswith(".pdf")
    assert generated.file_size > 0
    assert Path(generated.file_path).read_bytes().startswith(b"%PDF-")


def test_pdf_generation_failure_records_failed_and_cleans_temp_files(monkeypatch, tmp_path):
    schedule = SimpleNamespace(id=11, enabled=True, name="Management PDF", frequency="daily", timezone="Asia/Kolkata", report_format="pdf", filters={})
    generated = GeneratedReport(schedule_id=11, report_name="Management PDF", format="pdf", status="RUNNING", period_start=datetime(2026, 1, 1), period_end=datetime(2026, 1, 2), generated_at=datetime(2026, 1, 2))
    generated.id = 103
    generated = _run_with_fake_db(monkeypatch, tmp_path, schedule, generated, [{"hostname": "router-1"}], pdf_error=RuntimeError("pdf failed"))

    assert generated.status == "FAILED"
    assert generated.file_path is None
    assert list(tmp_path.iterdir()) == []
