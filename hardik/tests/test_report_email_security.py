from datetime import datetime
from types import SimpleNamespace

from backend.services import report_email


def _settings(**overrides):
    values = {
        "report_email_enabled": False,
        "report_email_recipients": "",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "not-for-logs",
        "smtp_from": "",
        "smtp_use_tls": True,
        "report_email_hour": 11,
        "report_email_minute": 0,
        "report_timezone": "Asia/Kolkata",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_recipients_are_validated_and_deduplicated(monkeypatch):
    monkeypatch.setattr(report_email, "get_settings", lambda: _settings(report_email_recipients="valid@example.com, invalid, valid@example.com"))

    assert report_email.resolve_report_recipients() == ["valid@example.com"]


def test_disabled_or_incomplete_configuration_prevents_delivery(monkeypatch):
    monkeypatch.setattr(report_email, "get_settings", lambda: _settings())
    assert report_email.send_yesterday_report_email() is False

    monkeypatch.setattr(report_email, "get_settings", lambda: _settings(report_email_enabled=True, report_email_recipients="valid@example.com"))
    assert report_email.send_yesterday_report_email() is False

    monkeypatch.setattr(
        report_email,
        "get_settings",
        lambda: _settings(
            report_email_enabled=True,
            report_email_recipients="valid@example.com",
            smtp_host="smtp.example.com",
            smtp_username="nms-user",
            smtp_password="",
        ),
    )
    assert report_email.send_yesterday_report_email() is False


def test_attachment_generation_failure_is_controlled(monkeypatch):
    settings = _settings(report_email_enabled=True, report_email_recipients="valid@example.com", smtp_host="smtp.example.com", smtp_from="nms@example.com")
    monkeypatch.setattr(report_email, "get_settings", lambda: settings)
    monkeypatch.setattr(report_email, "build_report_workbook", lambda summary: (_ for _ in ()).throw(RuntimeError("sensitive workbook detail")))
    monkeypatch.setattr(report_email, "SessionLocal", lambda: _FakeSession())
    _patch_report_rows(monkeypatch)

    assert report_email.send_yesterday_report_email() is False


def test_smtp_failure_is_controlled_without_logging_exception_details(monkeypatch, caplog):
    settings = _settings(report_email_enabled=True, report_email_recipients="valid@example.com", smtp_host="smtp.example.com", smtp_from="nms@example.com")
    monkeypatch.setattr(report_email, "get_settings", lambda: settings)
    monkeypatch.setattr(report_email, "build_report_workbook", lambda summary: b"xlsx")
    monkeypatch.setattr(report_email, "SessionLocal", lambda: _FakeSession())
    _patch_report_rows(monkeypatch)

    class _SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): raise RuntimeError("smtp-password-sensitive-detail")
        def __exit__(self, *args): return False

    monkeypatch.setattr(report_email.smtplib, "SMTP", _SMTP)
    assert report_email.send_yesterday_report_email() is False
    assert "smtp-password-sensitive-detail" not in caplog.text


def test_registration_preserves_singleton_safety_and_disabled_removal(monkeypatch):
    class _Scheduler:
        def __init__(self): self.jobs = {report_email.DAILY_REPORT_JOB_ID: object()}; self.calls = []
        def get_job(self, job_id): return self.jobs.get(job_id)
        def remove_job(self, job_id): self.calls.append(("remove", job_id))
        def add_job(self, *args, **kwargs): self.calls.append(("add", kwargs)); return object()

    scheduler = _Scheduler()
    monkeypatch.setattr(report_email, "get_settings", lambda: _settings())
    assert report_email.register_daily_report_job(SimpleNamespace(scheduler=scheduler)) is False
    assert scheduler.calls == [("remove", report_email.DAILY_REPORT_JOB_ID)]

    scheduler = _Scheduler()
    monkeypatch.setattr(report_email, "get_settings", lambda: _settings(report_email_enabled=True))
    assert report_email.register_daily_report_job(SimpleNamespace(scheduler=scheduler)) is True
    options = scheduler.calls[-1][1]
    assert options["id"] == report_email.DAILY_REPORT_JOB_ID
    assert options["replace_existing"] is True
    assert options["max_instances"] == 1
    assert options["coalesce"] is True


class _FakeSession:
    def __enter__(self): return self
    def __exit__(self, *args): return False


def _patch_report_rows(monkeypatch):
    import backend.api.routes as routes
    summary = SimpleNamespace(period_start=datetime(2026, 1, 1), total_devices=1, availability_pct=99.0, sla_met_pct=100.0)
    monkeypatch.setattr(routes, "_build_report_rows", lambda db, filters: (summary, []))
