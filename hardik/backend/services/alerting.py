"""Alert creation and email notification helpers."""

from email.message import EmailMessage
from dataclasses import dataclass
from html import escape
import logging
import smtplib
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import update

from backend.config.settings import get_settings
from backend.models import Alert, Notification, User

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
_smtp_suspended_until: datetime | None = None
_NOT_PRELOADED = object()


@dataclass(frozen=True)
class NotificationIntent:
    notification_id: int
    alert_id: int
    title: str
    description: str
    severity: str
    status: str
    recipient: str
    device_name: str | None = None
    device_ip: str | None = None
    operating_system: str | None = None
    module: str | None = None
    site_name: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None


def _format_alert_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return f"{value.isoformat(sep=' ', timespec='seconds')} IST"
    return value.astimezone(IST).isoformat(sep=" ", timespec="seconds") + " IST"


def _duration_text(created_at: datetime | None, resolved_at: datetime | None) -> str | None:
    if created_at is None or resolved_at is None:
        return None
    try:
        seconds = max(0, int((resolved_at - created_at).total_seconds()))
    except (TypeError, ValueError):
        return None
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s"


def _recommendations(module: str | None) -> tuple[str, ...]:
    actions = {
        "cpu": ("Review top CPU-consuming processes.", "Check for sustained load or recent workload changes."),
        "memory": ("Review available memory and top memory-consuming processes.", "Check for memory pressure, leaks, or workload growth."),
        "disk": ("Review filesystem utilization and largest recent files.", "Verify log rotation and available capacity."),
        "availability": ("Verify network reachability and device power/connectivity.", "Check the device interface and monitoring path."),
    }
    return actions.get((module or "").lower(), ())


def render_alert_email(intent: NotificationIntent, *, created_at: datetime | None = None,
                       resolved_at: datetime | None = None) -> tuple[str, str]:
    """Render an alert email without querying, mutating, or delivering anything."""
    severity = (intent.severity or "info").lower()
    heading = "RECOVERY" if intent.status.lower() == "resolved" else severity.upper()
    heading_color = {"critical": "#b42318", "warning": "#b54708", "info": "#175cd3"}.get(severity, "#344054")
    status = escape((intent.status or "unknown").upper())
    title = escape(intent.title or "Alert")
    description = escape(intent.description or "", quote=False).replace("\n", "<br>")
    details = []
    for label, value in (("Device/server", intent.device_name), ("IP address", intent.device_ip),
                         ("Operating system", intent.operating_system), ("Monitoring module", intent.module),
                         ("Site/group", intent.site_name)):
        if value:
            details.append(f"<tr><td style='padding:6px 12px 6px 0;color:#667085'>{escape(label)}</td><td style='padding:6px 0;color:#101828;font-weight:600'>{escape(value)}</td></tr>")
    alert_details = [
        ("Alert ID", str(intent.alert_id)),
        ("Severity", escape((intent.severity or "unknown").upper())),
        ("Status", status),
    ]
    detected = _format_alert_time(created_at)
    resolved = _format_alert_time(resolved_at) if intent.status.lower() == "resolved" else None
    duration = _duration_text(created_at, resolved_at) if intent.status.lower() == "resolved" else None
    if detected:
        alert_details.append(("Detected", escape(detected)))
    if resolved:
        alert_details.append(("Resolved", escape(resolved)))
    if duration:
        alert_details.append(("Duration", escape(duration)))
    detail_rows = "".join(f"<tr><td style='padding:6px 12px 6px 0;color:#667085'>{label}</td><td style='padding:6px 0;color:#101828;font-weight:600'>{value}</td></tr>" for label, value in alert_details)
    recommendation_items = "".join(f"<li style='margin:0 0 6px'>{escape(item)}</li>" for item in _recommendations(intent.module))
    recommendation_block = f"<h3 style='color:#172b4d;margin:24px 0 8px'>Recommended actions</h3><ul style='color:#475467;padding-left:20px'>{recommendation_items}</ul>" if recommendation_items else ""
    plain_lines = [f"AgniGate — {heading}", intent.title or "Alert", intent.description or "", f"Alert ID: {intent.alert_id}", f"Severity: {(intent.severity or 'unknown').upper()}", f"Status: {(intent.status or 'unknown').upper()}"]
    for label, value in (("Device/server", intent.device_name), ("IP address", intent.device_ip), ("Operating system", intent.operating_system), ("Monitoring module", intent.module), ("Site/group", intent.site_name), ("Detected", detected), ("Resolved", resolved), ("Duration", duration)):
        if value:
            plain_lines.append(f"{label}: {value}")
    recommendations = _recommendations(intent.module)
    if recommendations:
        plain_lines += ["", "Recommended actions:", *[f"- {item}" for item in recommendations]]
    plain_lines += ["", "Sent by Agnigate Network Monitoring"]
    plain = "\n".join(plain_lines)
    html_body = f"""<html><body style='margin:0;background:#f4f7fb;padding:24px;font-family:Arial,sans-serif;color:#101828'>
    <div style='max-width:620px;margin:auto;background:#fff;border:1px solid #e5eaf2;border-radius:12px;overflow:hidden'>
    <div style='padding:22px 28px;background:#172b4d;color:#fff;font-size:22px;font-weight:800'>AgniGate</div>
    <div style='padding:28px'><div style='color:{heading_color};font-size:13px;font-weight:700;letter-spacing:1px'>AGNIGATE · {heading} ALERT</div>
    <h2 style='color:#172b4d;margin:10px 0'>{title}</h2><p style='color:#475467;font-size:15px;line-height:1.5'>{description}</p>
    <div style='background:#f8fafc;border-left:4px solid {heading_color};padding:12px 16px'><table>{detail_rows}</table></div>
    {f"<h3 style='color:#172b4d;margin:24px 0 8px'>Device information</h3><table>{''.join(details)}</table>" if details else ""}
    {recommendation_block}
    <p style='color:#8492a6;font-size:12px;margin-top:28px'>Sent by <a href='https://agnigate.com/' style='color:#2563eb;text-decoration:none;font-weight:bold'>Agnigate</a> Network Monitoring</p>
    </div></div></body></html>"""
    return plain, html_body


def _intent_metadata(db: Session, alert: Alert) -> dict[str, str | None]:
    """Load presentation metadata only; failures leave optional fields absent."""
    result: dict[str, str | None] = {"device_name": None, "device_ip": None, "operating_system": None, "module": None, "site_name": None}
    try:
        if alert.linux_server_id:
            from backend.linux_monitoring.models import LinuxServer
            server = db.get(LinuxServer, alert.linux_server_id)
            if server:
                result.update(device_name=server.display_name or server.hostname, device_ip=server.ip_address, operating_system=server.os_name)
                result["site_name"] = getattr(getattr(server, "site", None), "name", None)
        elif alert.device_id:
            from backend.models import Device
            device = db.get(Device, alert.device_id)
            if device:
                result.update(device_name=device.hostname, device_ip=device.ip_address)
                result["site_name"] = getattr(getattr(device, "site", None), "name", None)
    except Exception:
        logger.warning("Could not load optional email alert metadata", exc_info=True)
    title = (alert.title or "").lower()
    for key in ("cpu", "memory", "disk"):
        if key in title:
            result["module"] = key
            break
    if "device down" in title or "availability" in title:
        result["module"] = "availability"
    return result


def _legacy_email_fallback(intent: NotificationIntent) -> tuple[str, str]:
    """Build a minimal escaped fallback without I/O or additional alert data."""
    title = intent.title or "Alert"
    description = intent.description or ""
    severity = (intent.severity or "unknown").upper()
    status = (intent.status or "unknown").upper()
    plain = "\n".join((
        f"AgniGate Alert: {title}",
        description,
        f"Alert ID: {intent.alert_id}",
        f"Severity: {severity}",
        f"Status: {status}",
    ))
    html_body = (
        "<html><body style='font-family:Arial,sans-serif;padding:24px'>"
        "<div style='max-width:560px;margin:auto;border:1px solid #e5eaf2;padding:24px'>"
        "<div style='font-size:22px;font-weight:800;color:#172b4d'>AgniGate</div>"
        f"<h2>{escape(title)}</h2>"
        f"<p>{escape(description, quote=False).replace(chr(10), '<br>')}</p>"
        f"<p>Alert ID: <b>{escape(str(intent.alert_id))}</b><br>"
        f"Severity: <b>{escape(severity)}</b><br>Status: <b>{escape(status)}</b></p>"
        "<p>Sent by <a href='https://agnigate.com/'>Agnigate</a> Network Monitoring</p>"
        "</div></body></html>"
    )
    return plain, html_body


def _render_email_safely(intent: NotificationIntent) -> tuple[str, str]:
    """Use the enhanced renderer, falling back without touching persistence."""
    try:
        return render_alert_email(intent, created_at=intent.created_at, resolved_at=intent.resolved_at)
    except Exception:
        logger.exception("Alert email template rendering failed; using compatibility fallback for alert %s", intent.alert_id)
        return _legacy_email_fallback(intent)


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
        Alert.status.in_({"open", "acknowledged"}),
        Alert.title.like("Device Down:%"),
    ).first()
    if existing:
        return None
    dismissed = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.title.like("Device Down:%"),
        Alert.deleted_at.is_not(None),
        Alert.status.in_({"open", "acknowledged"}),
    ).first()
    if dismissed:
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
    notify: bool = True,
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
    if notify:
        _notify(db, alert)
    return alert


def create_operational_alert(
    db: Session,
    title: str,
    description: str,
    severity: str = "info",
    device_id: int | None = None,
    notify: bool = True,
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
    if notify:
        _notify(db, alert)
    return alert


def create_threshold_alert(
    db: Session,
    device_id: int,
    title: str,
    description: str,
    severity: str,
    interface_id: int | None = None,
    linux_server_id: int | None = None,
    existing_alert: Alert | None | object = _NOT_PRELOADED,
    notification_intents: list[NotificationIntent] | None = None,
) -> Alert | None:
    """Persist and notify one active alert for a metric condition."""
    existing = existing_alert
    if existing is _NOT_PRELOADED:
        existing = db.query(Alert).filter(
            Alert.device_id == device_id,
            Alert.linux_server_id == linux_server_id,
            Alert.title == title,
            Alert.status.in_({"open", "acknowledged"}),
        ).first()
    if existing:
        return None
    dismissed = db.query(Alert).filter(
        Alert.device_id == device_id, Alert.linux_server_id == linux_server_id, Alert.title == title,
        Alert.deleted_at.is_not(None), Alert.status.in_({"open", "acknowledged"}),
    ).first()
    if dismissed:
        return None
    alert = Alert(device_id=device_id, linux_server_id=linux_server_id, interface_id=interface_id, severity=severity, title=title,
                  description=description, status="open", created_at=now_ist())
    db.add(alert)
    db.flush()
    _process_incident_safely(db, alert)
    _notify(db, alert, notification_intents)
    return alert


def resolve_interface_down_alert(
    db: Session,
    device_id: int,
    interface_id: int,
    interface_name: str,
    existing_alert: Alert | None | object = _NOT_PRELOADED,
) -> Alert | None:
    """Resolve the active SNMP alert for one interface and reconcile its incident."""
    alert = existing_alert
    if alert is _NOT_PRELOADED:
        alert = db.query(Alert).filter(
            Alert.device_id == device_id,
            Alert.interface_id == interface_id,
            Alert.title.ilike("Interface Down:%"),
            Alert.status.in_({"open", "acknowledged"}),
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

    return resolve_alert(db, alert, "Interface is operational again; SNMP reports link UP.")


def resolve_alert(
    db: Session,
    alert: Alert,
    recovery_description: str,
    *,
    notification_intents: list[NotificationIntent] | None = None,
) -> Alert:
    """Resolve one verified active alert and preserve a complete recovery record."""
    if alert.status not in ("open", "acknowledged"):
        return alert
    resolved_at = now_ist()
    duration = max(0, int((resolved_at - alert.created_at).total_seconds())) if alert.created_at else 0
    original = alert.description or "No original description recorded."
    alert.description = (
        f"{original}\n\nRecovery: {recovery_description}"
        f"\nTriggered at (IST): {alert.created_at.isoformat() if alert.created_at else 'unknown'}"
        f"\nResolved at (IST): {resolved_at.isoformat()}"
        f"\nTotal duration: {duration // 3600}h {(duration % 3600) // 60}m {duration % 60}s"
    )
    alert.status = "resolved"
    alert.resolved_at = resolved_at
    try:
        from backend.incidents.service import process_alert_recovery
        process_alert_recovery(db, alert.id)
    except Exception:
        logger.exception("Incident recovery failed for alert %s", alert.id)
    # Send the same detailed recovery record through the existing notification path.
    _notify(db, alert, notification_intents)
    return alert


def _deliver_intent(intent: NotificationIntent) -> tuple[str, datetime | None]:
    """Perform external delivery without requiring an ORM object or session."""
    try:
        body, html_body = _render_email_safely(intent)
        settings = get_settings()
        if not settings.smtp_host:
            return "pending", None
        now = now_ist()
        if _smtp_is_suspended(now):
            return "failed", None
        message = EmailMessage()
        message["Subject"] = f"NMS Alert: {intent.title}"
        message["From"] = settings.smtp_from or settings.smtp_username
        message["To"] = intent.recipient
        message.set_content(body)
        message.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return "delivered", now_ist()
    except Exception as exc:
        if _is_daily_limit_error(exc):
            _suspend_smtp_for_day(now_ist())
            logger.error(
                "Could not email alert %s to %s: provider daily limit reached; skipping further attempts today",
                intent.alert_id,
                intent.recipient,
            )
        else:
            logger.exception("Could not email alert %s to %s", intent.alert_id, intent.recipient)
        return "failed", None


def deliver_notification_intents(db: Session, intents: list[NotificationIntent]) -> None:
    """Deliver committed intents and persist delivery status separately."""
    started = time.perf_counter()
    logger.info("[remote-access][post-create] stage=notification-delivery-start elapsed_ms=0.000 stage_ms=0.000 count=%s", len(intents))
    updates = []
    for intent in intents:
        status, sent_at = _deliver_intent(intent)
        updates.append({
            "id": intent.notification_id,
            "status": status,
            "sent_at": sent_at,
        })
    if updates:
        db.execute(update(Notification), updates)
    logger.info("[remote-access][post-create] stage=notification-delivery-end elapsed_ms=%.3f stage_ms=%.3f count=%s",
                (time.perf_counter() - started) * 1000,
                (time.perf_counter() - started) * 1000, len(intents))


def _notify(
    db: Session,
    alert: Alert,
    deferred: list[NotificationIntent] | None = None,
) -> None:
    intents = []
    metadata = _intent_metadata(db, alert)
    for recipient in _recipients(db):
        notification = Notification(alert_id=alert.id, channel="email", sent_to=recipient, status="pending")
        db.add(notification)
        db.flush()
        intents.append(NotificationIntent(
            notification_id=notification.id,
            alert_id=alert.id,
            title=alert.title,
            description=alert.description or "",
            severity=alert.severity,
            status=alert.status,
            recipient=recipient,
            **metadata,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
        ))
    if deferred is not None:
        deferred.extend(intents)
    else:
        deliver_notification_intents(db, intents)


def prepare_notification_ids(db: Session, alert: Alert) -> list[int]:
    """Persist pending notification rows without performing delivery."""
    ids = []
    for recipient in _recipients(db):
        notification = Notification(alert_id=alert.id, channel="email", sent_to=recipient, status="pending")
        db.add(notification)
        db.flush()
        ids.append(notification.id)
    return ids


def deliver_notification_ids(db: Session, notification_ids: list[int]) -> None:
    """Load committed pending notifications and deliver them in this session."""
    if not notification_ids:
        return
    notifications = (db.query(Notification)
                     .filter(Notification.id.in_(notification_ids), Notification.status == "pending")
                     .all())
    intents = []
    for notification in notifications:
        alert = notification.alert
        if alert is None:
            continue
        metadata = _intent_metadata(db, alert)
        intents.append(NotificationIntent(
            notification_id=notification.id,
            alert_id=alert.id,
            title=alert.title,
            description=alert.description or "",
            severity=alert.severity,
            status=alert.status,
            recipient=notification.sent_to,
            **metadata,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
        ))
    deliver_notification_intents(db, intents)
