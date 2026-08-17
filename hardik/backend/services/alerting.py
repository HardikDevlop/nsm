"""Alert creation and email notification helpers."""

from email.message import EmailMessage
import logging
import smtplib
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.config.settings import get_settings
from backend.models import Alert, Notification, User

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Naive IST timestamp for PostgreSQL TIMESTAMP columns."""
    return datetime.now(IST).replace(tzinfo=None)


def _recipients(db: Session) -> list[str]:
    settings = get_settings()
    configured = [x.strip() for x in settings.alert_email_recipients.split(",") if x.strip()]
    if configured:
        return configured
    return [u.email for u in db.query(User).filter(User.status == "active").all() if u.email]


def create_offline_alert(db: Session, device_id: int, hostname: str, ip_address: str) -> Alert | None:
    """Create one open alert per device outage and notify active recipients."""
    existing = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.status.in_(("open", "acknowledged")),
        Alert.deleted_at.is_(None),
        Alert.title.like("Device Down:%"),
    ).first()
    if existing:
        return None

    alert = Alert(
        device_id=device_id,
        severity="critical",
        title=f"Device Down: {hostname}",
        description=f"{ip_address} stopped responding to ICMP (realtime monitor)",
        status="open",
        created_at=now_ist(),
    )
    db.add(alert)
    db.flush()

    _notify(db, alert)
    return alert


def create_threshold_alert(db: Session, device_id: int, title: str, description: str, severity: str) -> Alert | None:
    """Persist and notify one active alert for a metric condition."""
    existing = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.title == title,
        Alert.status.in_(("open", "acknowledged")),
        Alert.deleted_at.is_(None),
    ).first()
    if existing:
        return None
    alert = Alert(device_id=device_id, severity=severity, title=title,
                  description=description, status="open", created_at=now_ist())
    db.add(alert)
    db.flush()
    _notify(db, alert)
    return alert


def _notify(db: Session, alert: Alert) -> None:
    body = f"{alert.title}\n\n{alert.description}"
    settings = get_settings()
    for recipient in _recipients(db):
        notification = Notification(alert_id=alert.id, channel="email", sent_to=recipient, status="pending")
        db.add(notification)
        if settings.smtp_host:
            try:
                message = EmailMessage()
                message["Subject"] = f"NMS Alert: {alert.title}"
                message["From"] = settings.smtp_from or settings.smtp_username
                message["To"] = recipient
                message.set_content(body)
                message.add_alternative(
                    f"""<html><body style='font-family:Arial,sans-serif;background:#f4f7fb;padding:24px'>
                    <div style='max-width:560px;margin:auto;background:white;border-radius:12px;padding:28px;border:1px solid #e5eaf2;box-shadow:0 8px 24px rgba(23,43,77,.08)'>
                    <div style='font-size:22px;font-weight:800;color:#172b4d;margin-bottom:24px'>Agnigate</div>
                    <div style='color:#d92d20;font-size:12px;font-weight:bold;letter-spacing:1px'>AGNIGATE · CRITICAL ALERT</div>
                    <h2 style='color:#172b4d;margin-bottom:8px'>{alert.title}</h2>
                    <p style='color:#526581;font-size:15px'>{alert.description}</p>
                    <div style='background:#fff1f0;border-left:4px solid #d92d20;padding:12px;color:#7a271a'>Severity: <b>{alert.severity.upper()}</b><br>Status: <b>{alert.status.upper()}</b></div>
                    <p style='color:#8492a6;font-size:12px;margin-top:24px'>Sent by <a href='https://agnigate.com/' style='color:#2563eb;text-decoration:none;font-weight:bold'>Agnigate</a> Network Monitoring</p>
                    </div></body></html>""",
                    subtype="html",
                )
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                    if settings.smtp_use_tls:
                        smtp.starttls()
                    if settings.smtp_username:
                        smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(message)
                notification.status = "delivered"
                notification.sent_at = now_ist()
            except Exception:
                notification.status = "failed"
                logger.exception("Could not email alert %s to %s", alert.id, recipient)
