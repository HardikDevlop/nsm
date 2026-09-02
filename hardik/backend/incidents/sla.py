from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.models import Alert, AuditLog, Incident, IncidentSLAConfig, IncidentSLAHistory, IncidentSLATimer

VALID_PAUSE_STATES = {"pending"}


def _now() -> datetime:
    return datetime.utcnow()


def select_policy(db: Session, priority: str, service_id: int | None) -> IncidentSLAConfig | None:
    if service_id is not None:
        policy = db.query(IncidentSLAConfig).filter_by(priority=priority, service_id=service_id, enabled=True).first()
        if policy:
            return policy
    return db.query(IncidentSLAConfig).filter_by(priority=priority, service_id=None, enabled=True).first()


def start_timer(db: Session, incident: Incident) -> IncidentSLATimer | None:
    policy = select_policy(db, incident.priority, incident.service_id)
    if policy is None or db.query(IncidentSLATimer).filter_by(incident_id=incident.id).first():
        return None
    started = incident.created_at or _now()
    timer = IncidentSLATimer(incident_id=incident.id, config_id=policy.id, started_at=started,
                             response_deadline=started + timedelta(minutes=policy.response_target_minutes),
                             resolution_deadline=started + timedelta(minutes=policy.resolution_target_minutes), updated_at=_now())
    db.add(timer)
    db.add(IncidentSLAHistory(incident_id=incident.id, action="started", details=f"Policy {policy.id}", created_at=_now()))
    return timer


def sync_timer_state(db: Session, incident: Incident, now: datetime | None = None) -> IncidentSLATimer | None:
    now = now or _now()
    timer = db.query(IncidentSLATimer).filter_by(incident_id=incident.id).first()
    if timer is None:
        timer = start_timer(db, incident)
        if timer is None:
            return None
        db.flush()
    policy = db.query(IncidentSLAConfig).filter_by(id=timer.config_id).first()
    pause_states = set(policy.pause_states or []) if policy else set()
    pause_states &= VALID_PAUSE_STATES
    should_pause = incident.status in pause_states
    if should_pause and timer.paused_at is None and incident.status not in {"resolved", "closed"}:
        timer.paused_at = now
        db.add(IncidentSLAHistory(incident_id=incident.id, timer_id=timer.id, action="paused", details=f"State {incident.status}", created_at=now))
    elif not should_pause and timer.paused_at is not None:
        timer.paused_seconds += max(0, int((now - timer.paused_at).total_seconds()))
        timer.paused_at = None
        db.add(IncidentSLAHistory(incident_id=incident.id, timer_id=timer.id, action="resumed", details=f"State {incident.status}", created_at=now))
    if incident.status in {"investigating", "resolved", "closed"} and timer.first_responded_at is None:
        timer.first_responded_at = now
        db.add(IncidentSLAHistory(incident_id=incident.id, timer_id=timer.id, action="responded", created_at=now))
    if incident.status in {"resolved", "closed"} and timer.resolved_at is None:
        timer.resolved_at = incident.closed_at or now
        db.add(IncidentSLAHistory(incident_id=incident.id, timer_id=timer.id, action="resolved", created_at=now))
    timer.updated_at = now
    return timer


def evaluate_timer(db: Session, incident: Incident, now: datetime | None = None) -> IncidentSLATimer | None:
    now = now or _now()
    timer = sync_timer_state(db, incident, now)
    if timer is None:
        return None
    policy = db.query(IncidentSLAConfig).filter_by(id=timer.config_id).first()
    paused = timer.paused_seconds + (int((now - timer.paused_at).total_seconds()) if timer.paused_at else 0)
    effective_now = now - timedelta(seconds=paused)
    if timer.first_responded_at is None and effective_now >= timer.response_deadline and not timer.response_breached:
        timer.response_breached = True
        _record_breach(db, incident, timer, "response")
    if timer.resolved_at is None and incident.status not in {"resolved", "closed"} and effective_now >= timer.resolution_deadline and not timer.resolution_breached:
        timer.resolution_breached = True
        _record_breach(db, incident, timer, "resolution")
    if policy and policy.escalation_after_minutes is not None and not timer.escalation_sent and effective_now >= timer.started_at + timedelta(minutes=policy.escalation_after_minutes):
        timer.escalation_sent = True
        db.add(IncidentSLAHistory(incident_id=incident.id, timer_id=timer.id, action="escalated", details=f"user_id={policy.escalation_user_id}", created_at=now))
        db.add(Alert(device_id=None, severity="high", title=f"SLA escalation: incident #{incident.id}", description="Incident exceeded configured escalation threshold", status="open", created_at=now))
    timer.updated_at = now
    return timer


def _record_breach(db: Session, incident: Incident, timer: IncidentSLATimer, target: str) -> None:
    now = _now()
    db.add(IncidentSLAHistory(incident_id=incident.id, timer_id=timer.id, action=f"{target}_breach", details=f"{target} target exceeded", created_at=now))
    db.add(Alert(device_id=None, severity="high", title=f"SLA breach: incident #{incident.id} ({target})", description=f"Configured {target} target was exceeded", status="open", created_at=now))


def timer_view(db: Session, incident: Incident) -> dict | None:
    timer = evaluate_timer(db, incident)
    if timer is None:
        return None
    return {"id": timer.id, "incident_id": timer.incident_id, "started_at": timer.started_at, "response_deadline": timer.response_deadline, "resolution_deadline": timer.resolution_deadline, "first_responded_at": timer.first_responded_at, "resolved_at": timer.resolved_at, "paused_at": timer.paused_at, "paused_seconds": timer.paused_seconds, "response_breached": timer.response_breached, "resolution_breached": timer.resolution_breached, "escalation_sent": timer.escalation_sent}
