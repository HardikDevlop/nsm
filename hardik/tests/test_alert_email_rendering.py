from datetime import datetime
from types import SimpleNamespace

from backend.services import alerting
from backend.services.alerting import NotificationIntent


def _intent(**values):
    base = dict(notification_id=1, alert_id=2426, title="Linux <MEMORY>", description="Used < 80%", severity="warning", status="open", recipient="ops@example.com")
    base.update(values)
    return NotificationIntent(**base)


def test_warning_heading_and_dynamic_metadata_are_rendered():
    plain, html = alerting.render_alert_email(
        _intent(device_name="agnigatenms", device_ip="192.168.100.40", operating_system="Ubuntu", module="memory", site_name="HQ"),
        created_at=datetime(2026, 11, 13, 10, 30, 0),
    )
    assert "AGNIGATE · WARNING ALERT" in html
    assert "agnigatenms" in html and "192.168.100.40" in html
    assert "Ubuntu" in html and "HQ" in html
    assert "Detected" in html and "IST" in html
    assert "Used &lt; 80%" in html
    assert "Linux <MEMORY>" in plain
    assert "Recommended actions:" in plain


def test_critical_info_and_recovery_headings():
    assert "AGNIGATE · CRITICAL ALERT" in alerting.render_alert_email(_intent(severity="critical"))[1]
    assert "AGNIGATE · INFO ALERT" in alerting.render_alert_email(_intent(severity="info"))[1]
    plain, html = alerting.render_alert_email(
        _intent(status="resolved", severity="warning", module="availability"),
        created_at=datetime(2026, 11, 13, 10, 0),
        resolved_at=datetime(2026, 11, 13, 12, 5),
    )
    assert "AGNIGATE · RECOVERY ALERT" in html
    assert "Resolved" in html and "2h 5m 0s" in html
    assert "RECOVERY" in plain


def test_optional_fields_and_metric_values_are_not_fabricated():
    plain, html = alerting.render_alert_email(_intent())
    assert "Device/server" not in html
    assert "Operating system" not in html
    assert "threshold" not in plain.lower()
    assert "93.01" not in plain
    assert "MemAvailable" not in plain


def test_rendering_does_not_create_notifications_or_call_smtp(monkeypatch):
    called = []
    monkeypatch.setattr(alerting, "smtplib", SimpleNamespace(SMTP=lambda *args, **kwargs: called.append(args)))
    plain, html = alerting.render_alert_email(_intent(module="cpu"))
    assert called == []
    assert "CPU" in plain
    assert "agnigate.com" in html


def test_delivery_uses_renderer_and_preserves_plain_text_fallback(monkeypatch):
    class FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def send_message(self, message):
            self.message = message
    smtp = FakeSMTP()
    monkeypatch.setattr(alerting.smtplib, "SMTP", lambda *args, **kwargs: smtp)
    monkeypatch.setattr(alerting, "get_settings", lambda: SimpleNamespace(
        smtp_host="smtp.test", smtp_port=587, smtp_use_tls=False, smtp_username="", smtp_password="", smtp_from=""
    ))
    status, _ = alerting._deliver_intent(_intent(module="disk"))
    assert status == "delivered"
    assert smtp.message.get_body(preferencelist=("plain",)).get_content().startswith("AgniGate")
    assert "AGNIGATE · WARNING ALERT" in smtp.message.get_body(preferencelist=("html",)).get_content()


def test_renderer_exception_uses_escaped_fallback_and_calls_smtp_once(monkeypatch):
    class FakeSMTP:
        calls = 0
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def send_message(self, message):
            self.message = message
    smtp = FakeSMTP()
    monkeypatch.setattr(alerting, "render_alert_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("template failure")))
    monkeypatch.setattr(alerting.smtplib, "SMTP", lambda *args, **kwargs: setattr(FakeSMTP, "calls", FakeSMTP.calls + 1) or smtp)
    monkeypatch.setattr(alerting, "get_settings", lambda: SimpleNamespace(
        smtp_host="smtp.test", smtp_port=587, smtp_use_tls=False, smtp_username="", smtp_password="", smtp_from=""
    ))
    status, _ = alerting._deliver_intent(_intent(title="<Alert>", description="<unsafe>"))
    assert status == "delivered"
    assert FakeSMTP.calls == 1
    assert "&lt;Alert&gt;" in smtp.message.get_body(preferencelist=("html",)).get_content()
    assert "&lt;unsafe&gt;" in smtp.message.get_body(preferencelist=("html",)).get_content()


def test_renderer_and_fallback_failure_returns_failed_without_smtp(monkeypatch):
    called = []
    monkeypatch.setattr(alerting, "render_alert_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("template failure")))
    monkeypatch.setattr(alerting, "_legacy_email_fallback", lambda _intent: (_ for _ in ()).throw(RuntimeError("fallback failure")))
    monkeypatch.setattr(alerting.smtplib, "SMTP", lambda *args, **kwargs: called.append(args))
    monkeypatch.setattr(alerting, "get_settings", lambda: SimpleNamespace(
        smtp_host="smtp.test", smtp_port=587, smtp_use_tls=False, smtp_username="", smtp_password="", smtp_from=""
    ))
    status, sent_at = alerting._deliver_intent(_intent())
    assert status == "failed"
    assert sent_at is None
    assert called == []


class _DeliveryDB:
    def __init__(self):
        self.updates = []
    def execute(self, statement, updates):
        self.updates.extend(updates)


def test_notification_status_is_updated_after_success_or_failure(monkeypatch):
    db = _DeliveryDB()
    monkeypatch.setattr(alerting, "_deliver_intent", lambda _intent: ("delivered", datetime(2026, 11, 13, 12, 0)))
    alerting.deliver_notification_intents(db, [_intent(notification_id=11)])
    assert db.updates == [{"id": 11, "status": "delivered", "sent_at": datetime(2026, 11, 13, 12, 0)}]
    db = _DeliveryDB()
    monkeypatch.setattr(alerting, "_deliver_intent", lambda _intent: ("failed", None))
    alerting.deliver_notification_intents(db, [_intent(notification_id=12)])
    assert db.updates == [{"id": 12, "status": "failed", "sent_at": None}]
