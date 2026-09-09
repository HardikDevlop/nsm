from __future__ import annotations

import hashlib
import re
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.incidents.sla import evaluate_timer, start_timer
from backend.models import Alert, Incident, IncidentAlert, IncidentHistory, RCAIncident

ACTIVE_STATUSES = ("open", "investigating", "pending")
ACTIONABLE_SEVERITIES = {"critical", "high"}
ACTIONABLE_STATUSES = {"open", "acknowledged"}


def _now() -> datetime:
    return datetime.utcnow()


def _category(alert: Alert) -> str:
    content = f"{alert.title} {alert.description or ''}".lower()
    if any(word in content for word in ("cpu", "memory", "latency", "storage", "capacity")):
        return "performance"
    if any(word in content for word in ("security", "attack", "firewall", "unauthorized")):
        return "security"
    if any(word in content for word in ("interface", "link", "offline", "down", "reachability")):
        return "availability"
    return "other"


def _priority(alert: Alert) -> str:
    return {"critical": "p1", "high": "p2", "medium": "p3", "warning": "p3", "low": "p4"}.get(alert.severity.lower(), "p3")


def _fault_signature(alert: Alert) -> str:
    title = (alert.title or "").strip()
    match = re.match(r"^interface\s+down:\s*(.+)$", title, re.IGNORECASE)
    if match:
        if alert.interface_id is not None:
            return f"interface_down_id:{alert.interface_id}"
        return f"interface_down:{match.group(1).strip().lower()}"
    if re.match(r"^device\s+down:", title, re.IGNORECASE):
        return "device_down"
    digest = hashlib.sha256(re.sub(r"\s+", " ", title.lower()).encode("utf-8")).hexdigest()[:24]
    return f"alert:{digest}"


def correlation_key(alert: Alert) -> str:
    scope = f"device:{alert.device_id}" if alert.device_id is not None else "global"
    return f"{scope}:{_category(alert)}:{_fault_signature(alert)}"[:240]


def _history(db: Session, incident: Incident, action: str, actor_id: int | None = None, old_value: str | None = None, new_value: str | None = None, reason: str | None = None) -> None:
    db.add(IncidentHistory(incident_id=incident.id, action=action, actor_id=actor_id, old_value=old_value, new_value=new_value, reason=reason, created_at=_now()))


def _advisory_lock(db: Session, key: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def process_alert_for_incident(db: Session, alert_id: int, created_by: int | None = None) -> Incident | None:
    """Reconcile one already-flushed Alert into an Incident safely and idempotently."""
    alert = db.get(Alert, alert_id)
    if alert is None or alert.deleted_at is not None:
        return None
    if alert.status not in ACTIONABLE_STATUSES or alert.severity.lower() not in ACTIONABLE_SEVERITIES:
        return None

    key = correlation_key(alert)
    try:
        with db.begin_nested():
            _advisory_lock(db, key)
            link = db.query(IncidentAlert).filter_by(alert_id=alert.id).first()
            if link:
                return db.get(Incident, link.incident_id)

            incident = db.query(Incident).filter(Incident.correlation_key == key, Incident.status.in_(ACTIVE_STATUSES)).order_by(Incident.updated_at.desc(), Incident.id.desc()).first()
            if incident is None:
                incident = db.query(Incident).filter(Incident.correlation_key == key, Incident.status == "resolved").order_by(Incident.updated_at.desc(), Incident.id.desc()).first()
                if incident is not None:
                    old_status = incident.status
                    incident.status = "open"
                    incident.resolved_at = None
                    incident.closed_at = None
                    incident.updated_at = _now()
                    _history(db, incident, "reopened", created_by, old_status, "open", "Matching active fault recurred")
            if incident is None:
                incident = Incident(title=f"{alert.severity.upper()} incident: {alert.title}", description="Automatically created from qualifying alert; source alert remains authoritative.", category=_category(alert), priority=_priority(alert), status="open", correlation_key=key, created_by=created_by, created_at=alert.created_at or _now(), updated_at=_now())
                db.add(incident)
                db.flush()
                _history(db, incident, "created", created_by, new_value="open", reason=f"Alert {alert.id}")
                start_timer(db, incident)

            db.add(IncidentAlert(incident_id=incident.id, alert_id=alert.id, linked_at=_now()))
            _history(db, incident, "alert_linked", created_by, new_value=str(alert.id))
            return incident
    except IntegrityError:
        # The nested transaction has already rolled back to its savepoint;
        # keep the caller's Alert transaction usable.
        existing = db.query(Incident).filter(Incident.correlation_key == key, Incident.status.in_(ACTIVE_STATUSES)).order_by(Incident.updated_at.desc(), Incident.id.desc()).first()
        if existing and not db.query(IncidentAlert).filter_by(incident_id=existing.id, alert_id=alert.id).first():
            db.add(IncidentAlert(incident_id=existing.id, alert_id=alert.id, linked_at=_now()))
        return existing


def process_alert_recovery(db: Session, alert_id: int, actor_id: int | None = None) -> list[Incident]:
    """Resolve linked active Incidents only after their source Alert is resolved."""
    alert = db.get(Alert, alert_id)
    if alert is None or alert.status != "resolved":
        return []
    resolved: list[Incident] = []
    for link in db.query(IncidentAlert).filter_by(alert_id=alert.id).all():
        incident = db.get(Incident, link.incident_id)
        if incident is None or incident.status not in ACTIVE_STATUSES:
            continue
        active_alert = db.query(IncidentAlert).join(Alert, IncidentAlert.alert_id == Alert.id).filter(IncidentAlert.incident_id == incident.id, Alert.status.in_(ACTIONABLE_STATUSES), Alert.deleted_at.is_(None)).first()
        if active_alert:
            continue
        old_status = incident.status
        incident.status = "resolved"
        incident.resolved_at = alert.resolved_at or _now()
        incident.updated_at = _now()
        _history(db, incident, "alert_recovered", actor_id, old_status, "resolved", f"Alert {alert.id} recovered")
        evaluate_timer(db, incident, incident.resolved_at)
        resolved.append(incident)
    return resolved


def create_incident_from_alert(db: Session, alert: Alert, created_by: int | None = None) -> Incident | None:
    """Backward-compatible wrapper for callers holding the persisted Alert object."""
    return process_alert_for_incident(db, alert.id, created_by) if alert.id else None


def link_rca(db: Session, incident: Incident, rca_id: int) -> None:
    if db.query(RCAIncident).filter(RCAIncident.id == rca_id).first() is None:
        raise LookupError("RCA incident not found")
    incident.rca_incident_id = rca_id
