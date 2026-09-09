"""Alert creation and email notification helpers."""

from email.message import EmailMessage
import logging
import smtplib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.config.settings import get_settings
from backend.models import Alert, Notification, User

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
_smtp_suspended_until: datetime | None = None


def _process_incident_safely(db: Session, alert: Alert) -> None:
    try:
        from backend.incidents.service import process_alert_for_incident
        process_alert_for_incident(db, alert.id)
    except Exception:
        logger.exception("Incident processing failed for alert %s", alert.id)


def now_ist() -> datetime:
    """Naive IST timestamp for PostgreSQL TIMESTAMP columns."""
    return datetime.now(IST).replace(tzinfo=None)


def _recipients(db: Session) -> list[str]:
    settings = get_settings()
    configured = [x.strip() for x in settings.alert_email_recipients.split(",") if x.strip()]
    if configured:
        return configured
    return [u.email for u in db.query(User).filter(User.status == "active").all() if u.email]


def _is_daily_limit_error(exc: Exception) -> bool:
    """Identify provider throttling without depending on a provider-specific class."""
    text = str(exc).lower()
    return "daily user sending limit exceeded" in text or "daily sending limit" in text


def _smtp_is_suspended(now: datetime) -> bool:
    global _smtp_suspended_until
    if _smtp_suspended_until is None:
        return False
    if now >= _smtp_suspended_until:
        _smtp_suspended_until = None
        return False
    return True


def _suspend_smtp_for_day(now: datetime) -> None:
    global _smtp_suspended_until
    _smtp_suspended_until = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    logger.error(
        "SMTP email notifications suspended until %s after provider daily sending limit",
        _smtp_suspended_until.isoformat(),
    )


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

    _process_incident_safely(db, alert)

    _notify(db, alert)
    return alert


def create_device_added_alert(
    db: Session,
    device_id: int,
    hostname: str,
    ip_address: str,
    discovery_method: str,
    status: str,
    mac_address: str | None = None,
    snmp_version: str | None = None,
) -> Alert | None:
    """Create one active informational alert when discovery adds a device."""
    title = f"New Device Added: {hostname}"
    existing = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.title == title,
        Alert.status.in_(("open", "acknowledged")),
        Alert.deleted_at.is_(None),
    ).first()
    if existing:
        return None

    details = [
        f"IP address: {ip_address}",
        f"Discovery method: {discovery_method}",
        f"Status: {status}",
    ]
    if mac_address:
        details.append(f"MAC address: {mac_address}")
    if snmp_version:
        details.append(f"SNMP version: {snmp_version}")

    alert = Alert(
        device_id=device_id,
        severity="info",
        title=title,
        description="A new device was added to the inventory.\n" + "\n".join(details),
        status="open",
        created_at=now_ist(),
    )
    db.add(alert)
    db.flush()
    _process_incident_safely(db, alert)
    _notify(db, alert)
    return alert


def create_operational_alert(
    db: Session,
    title: str,
    description: str,
    severity: str = "info",
    device_id: int | None = None,
) -> Alert:
    """Create a notification-backed alert for an explicit operator action."""
    alert = Alert(
        device_id=device_id,
        severity=severity,
        title=title,
        description=description,
        status="open",
        created_at=now_ist(),
    )
    db.add(alert)
    db.flush()
    _notify(db, alert)
    return alert


def create_threshold_alert(
    db: Session,
    device_id: int,
    title: str,
    description: str,
    severity: str,
    interface_id: int | None = None,
) -> Alert | None:
    """Persist and notify one active alert for a metric condition."""
    existing = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.title == title,
        Alert.status.in_(("open", "acknowledged")),
        Alert.deleted_at.is_(None),
    ).first()
    if existing:
        return None
    alert = Alert(device_id=device_id, interface_id=interface_id, severity=severity, title=title,
                  description=description, status="open", created_at=now_ist())
    db.add(alert)
    db.flush()
    _process_incident_safely(db, alert)
    _notify(db, alert)
    return alert


def resolve_interface_down_alert(
    db: Session,
    device_id: int,
    interface_id: int,
    interface_name: str,
) -> Alert | None:
    """Resolve the active SNMP alert for one interface and reconcile its incident."""
    alert = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.interface_id == interface_id,
        Alert.title.ilike("Interface Down:%"),
        Alert.status.in_(("open", "acknowledged")),
        Alert.deleted_at.is_(None),
    ).order_by(Alert.created_at.desc()).first()
    if alert is None:
        # Retain compatibility with alerts created before interface_id existed.
        alert = db.query(Alert).filter(
            Alert.device_id == device_id,
            Alert.title == f"Interface Down: {interface_name}",
            Alert.status.in_(("open", "acknowledged")),
            Alert.deleted_at.is_(None),
        ).order_by(Alert.created_at.desc()).first()
    if alert is None:
        return None

    alert.status = "resolved"
    alert.resolved_at = now_ist()
    try:
        from backend.incidents.service import process_alert_recovery
        process_alert_recovery(db, alert.id)
    except Exception:
        logger.exception("Incident recovery failed for interface alert %s", alert.id)
    return alert


def _notify(db: Session, alert: Alert) -> None:
    body = f"{alert.title}\n\n{alert.description}"
    settings = get_settings()
    for recipient in _recipients(db):
        notification = Notification(alert_id=alert.id, channel="email", sent_to=recipient, status="pending")
        db.add(notification)
        if settings.smtp_host:
            now = now_ist()
            if _smtp_is_suspended(now):
                notification.status = "failed"
                continue
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
            except Exception as exc:
                notification.status = "failed"
                if _is_daily_limit_error(exc):
                    _suspend_smtp_for_day(now_ist())
                    logger.error(
                        "Could not email alert %s to %s: provider daily limit reached; skipping further attempts today",
                        alert.id,
                        recipient,
                    )
                else:
                    logger.exception("Could not email alert %s to %s", alert.id, recipient)
