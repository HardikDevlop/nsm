from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import Alert, AuditLog, Device, Incident, IncidentAlert, IncidentAttachment, IncidentComment, IncidentHistory, IncidentSLAConfig, IncidentSLAHistory, Interface, User
from backend.models.rca import RCAIncident
from backend.incidents.service import ACTIVE_STATUSES, _history, link_rca
from backend.incidents.sla import VALID_PAUSE_STATES, evaluate_timer, start_timer, timer_view
from backend.rca.engine import IncidentRCAError, analyze_incident_rca

router = APIRouter(prefix="/api/v1/incidents", tags=["Incident Management"])


class IncidentCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str = Field(default="other", pattern="^(availability|performance|security|change|other)$")
    priority: str = Field(default="p3", pattern="^p[1-5]$")
    assigned_to: int | None = Field(default=None, gt=0)
    alert_ids: list[int] = Field(default_factory=list, max_length=500)
    rca_incident_id: int | None = Field(default=None, gt=0)
    service_id: int | None = Field(default=None, gt=0)


class IncidentUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, pattern="^(availability|performance|security|change|other)$")
    priority: str | None = Field(default=None, pattern="^p[1-5]$")
    status: str | None = Field(default=None, pattern="^(open|investigating|pending|resolved|closed)$")
    assigned_to: int | None = Field(default=None, gt=0)
    rca_incident_id: int | None = Field(default=None, gt=0)


class CommentPayload(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class AttachmentPayload(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str | None = Field(default=None, max_length=120)
    size_bytes: int = Field(default=0, ge=0, le=50_000_000)
    storage_key: str = Field(min_length=1, max_length=500)


class SLAPolicyPayload(BaseModel):
    priority: str = Field(pattern="^p[1-5]$")
    service_id: int | None = Field(default=None, gt=0)
    response_target_minutes: int = Field(gt=0, le=100000)
    resolution_target_minutes: int = Field(gt=0, le=200000)
    pause_states: list[str] = Field(default_factory=lambda: ["pending"], max_length=10)
    escalation_after_minutes: int | None = Field(default=None, gt=0, le=200000)
    escalation_user_id: int | None = Field(default=None, gt=0)
    enabled: bool = True


def _audit(db: Session, user_id: int, action: str, resource: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource))


def _serialize(db: Session, item: Incident) -> dict[str, Any]:
    links = db.query(IncidentAlert).filter(IncidentAlert.incident_id == item.id).order_by(IncidentAlert.linked_at.asc()).all()
    alerts = db.query(Alert).filter(Alert.id.in_([x.alert_id for x in links])).all() if links else []
    device_ids = {a.device_id for a in alerts if a.device_id is not None}
    devices = {d.id: d for d in db.query(Device).filter(Device.id.in_(device_ids)).all()} if device_ids else {}
    interface_ids = {a.interface_id for a in alerts if a.interface_id is not None}
    interface_names = {a.title.split(":", 1)[1].strip() for a in alerts if a.title.lower().startswith("interface down:")}
    interface_filters = [Interface.device_id.in_(device_ids)]
    if interface_ids:
        interface_filters.append(Interface.id.in_(interface_ids))
    if interface_names:
        interface_filters.append(Interface.interface_name.in_(interface_names))
    interface_rows = db.query(Interface).filter(*interface_filters).all() if device_ids and (interface_ids or interface_names) else []
    interfaces_by_id = {i.id: i for i in interface_rows}
    interfaces_by_device_name = {(i.device_id, i.interface_name): i for i in interface_rows}
    rca = db.get(RCAIncident, item.rca_incident_id) if item.rca_incident_id else None
    return {"id": item.id, "title": item.title, "description": item.description, "category": item.category, "priority": item.priority, "status": item.status, "correlation_key": item.correlation_key, "assigned_to": item.assigned_to, "created_by": item.created_by, "rca_incident_id": item.rca_incident_id, "rca": {"id": rca.id, "root_kind": rca.root_kind, "root_label": rca.root_label, "root_device_id": rca.root_device_id, "root_interface_id": rca.root_interface_id, "root_ci_id": rca.root_ci_id, "confidence": rca.confidence, "impact_summary": rca.impact_summary, "window_start": rca.window_start, "window_end": rca.window_end, "created_at": rca.created_at, "updated_at": rca.updated_at, "evidence": [{"id": e.id, "evidence_type": e.evidence_type, "alert_id": e.alert_id, "event_id": e.event_id, "relationship_id": e.relationship_id, "score": e.score, "reason": e.reason, "payload": e.payload} for e in rca.evidence]} if rca else None, "service_id": item.service_id, "acknowledged_at": item.acknowledged_at, "acknowledged_by": item.acknowledged_by, "resolved_at": item.resolved_at, "closed_at": item.closed_at, "created_at": item.created_at, "updated_at": item.updated_at, "alert_ids": [x.alert_id for x in links], "alerts": [{"id": a.id, "device_id": a.device_id, "interface_id": a.interface_id, "device_name": devices[a.device_id].hostname if a.device_id in devices else None, "ip_address": devices[a.device_id].ip_address if a.device_id in devices else None, "interface_name": (interfaces_by_id.get(a.interface_id) or interfaces_by_device_name.get((a.device_id, a.title.split(":", 1)[1].strip()))).interface_name if (a.interface_id or a.title.lower().startswith("interface down:")) and (interfaces_by_id.get(a.interface_id) or interfaces_by_device_name.get((a.device_id, a.title.split(":", 1)[1].strip()))) else None, "severity": a.severity, "title": a.title, "description": a.description, "status": a.status, "resolved_at": a.resolved_at, "created_at": a.created_at} for a in alerts], "comments": [{"id": c.id, "author_id": c.author_id, "body": c.body, "created_at": c.created_at} for c in db.query(IncidentComment).filter(IncidentComment.incident_id == item.id).order_by(IncidentComment.created_at.asc()).all()], "attachments": [{"id": a.id, "file_name": a.file_name, "content_type": a.content_type, "size_bytes": a.size_bytes, "storage_key": a.storage_key, "created_at": a.created_at} for a in db.query(IncidentAttachment).filter(IncidentAttachment.incident_id == item.id).order_by(IncidentAttachment.created_at.asc()).all()]}


@router.get("")
def list_incidents(status_filter: str | None = None, category: str | None = None, priority: str | None = None, assigned_to: int | None = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("incidents:read"))):
    query = db.query(Incident)
    if status_filter: query = query.filter(Incident.status == status_filter)
    if category: query = query.filter(Incident.category == category)
    if priority: query = query.filter(Incident.priority == priority)
    if assigned_to: query = query.filter(Incident.assigned_to == assigned_to)
    rows = query.order_by(Incident.updated_at.desc()).offset(skip).limit(limit).all()
    return {"items": [_serialize(db, item) for item in rows], "skip": skip, "limit": limit}


@router.post("", status_code=201)
def create_incident(payload: IncidentCreatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:create"))):
    now = datetime.utcnow()
    if payload.assigned_to is not None and db.query(User).filter(User.id == payload.assigned_to, User.status == "active").first() is None:
        raise HTTPException(422, "Assigned user does not exist or is inactive")
    item = Incident(**payload.model_dump(exclude={"alert_ids"}), created_by=current_user.id, created_at=now, updated_at=now)
    db.add(item); db.flush()
    start_timer(db, item)
    for alert_id in payload.alert_ids:
        if db.query(Alert).filter(Alert.id == alert_id, Alert.deleted_at.is_(None)).first() is None: raise HTTPException(404, f"Alert {alert_id} not found")
        db.add(IncidentAlert(incident_id=item.id, alert_id=alert_id, linked_at=now))
        _history(db, item, "alert_linked", current_user.id, new_value=str(alert_id))
    _history(db, item, "created", current_user.id, new_value="open")
    _audit(db, current_user.id, "CREATE", f"incidents:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/sla/policies")
def list_sla_policies(db: Session = Depends(get_db), _: User = Depends(require_permission("incidents:read"))):
    return db.query(IncidentSLAConfig).order_by(IncidentSLAConfig.priority.asc(), IncidentSLAConfig.service_id.asc()).all()


@router.post("/sla/policies", status_code=201)
def create_sla_policy(payload: SLAPolicyPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:manage"))):
    invalid = set(payload.pause_states) - VALID_PAUSE_STATES
    if invalid:
        raise HTTPException(422, f"Unsupported SLA pause state(s): {', '.join(sorted(invalid))}")
    now = datetime.utcnow()
    item = IncidentSLAConfig(**payload.model_dump(), created_at=now, updated_at=now)
    db.add(item); _audit(db, current_user.id, "CREATE_SLA_POLICY", "incident_sla_configs"); db.commit(); db.refresh(item)
    return item


@router.post("/{incident_id}/rca")
def analyze_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("rca:execute"))):
    try:
        item = db.query(Incident).filter(Incident.id == incident_id).first()
        if item is None:
            raise HTTPException(404, "Incident not found")
        rca = analyze_incident_rca(db, incident_id)
        _audit(db, current_user.id, "ANALYZE_RCA", f"incidents:{incident_id}")
        db.commit()
        db.refresh(item)
        db.refresh(rca)
        return {"incident_id": incident_id, "rca": {"id": rca.id, "root_kind": rca.root_kind, "root_label": rca.root_label, "root_device_id": rca.root_device_id, "root_interface_id": rca.root_interface_id, "root_ci_id": rca.root_ci_id, "confidence": rca.confidence, "impact_summary": rca.impact_summary, "window_start": rca.window_start, "window_end": rca.window_end, "created_at": rca.created_at, "updated_at": rca.updated_at, "evidence": [{"id": e.id, "evidence_type": e.evidence_type, "alert_id": e.alert_id, "event_id": e.event_id, "relationship_id": e.relationship_id, "score": e.score, "reason": e.reason, "payload": e.payload} for e in rca.evidence]}}
    except IncidentRCAError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))


@router.get("/{incident_id}/history")
def incident_history(incident_id: int, limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("incidents:read"))):
    if db.query(Incident.id).filter(Incident.id == incident_id).first() is None:
        raise HTTPException(404, "Incident not found")
    rows = db.query(IncidentHistory).filter(IncidentHistory.incident_id == incident_id).order_by(IncidentHistory.created_at.asc(), IncidentHistory.id.asc()).limit(limit).all()
    return [{"id": row.id, "action": row.action, "actor_id": row.actor_id, "old_value": row.old_value, "new_value": row.new_value, "reason": row.reason, "created_at": row.created_at} for row in rows]


@router.post("/{incident_id}/acknowledge")
def acknowledge_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:update"))):
    item = db.query(Incident).filter(Incident.id == incident_id).first()
    if item is None: raise HTTPException(404, "Incident not found")
    if item.status in {"resolved", "closed"}: raise HTTPException(409, "Resolved or closed incidents cannot be acknowledged")
    if item.acknowledged_at is None:
        item.acknowledged_at = datetime.utcnow(); item.acknowledged_by = current_user.id; item.updated_at = datetime.utcnow()
        _history(db, item, "acknowledged", current_user.id, new_value=str(current_user.id))
        _audit(db, current_user.id, "ACKNOWLEDGE", f"incidents:{item.id}")
        db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{incident_id}/resolve")
def resolve_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:update"))):
    item = db.query(Incident).filter(Incident.id == incident_id).first()
    if item is None: raise HTTPException(404, "Incident not found")
    if item.status == "closed": raise HTTPException(409, "Closed incidents cannot be resolved")
    old_status = item.status; now = datetime.utcnow(); item.status = "resolved"; item.resolved_at = item.resolved_at or now; item.updated_at = now
    _history(db, item, "resolved", current_user.id, old_status, "resolved")
    _audit(db, current_user.id, "RESOLVE", f"incidents:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{incident_id}/reopen")
def reopen_incident(incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:update"))):
    item = db.query(Incident).filter(Incident.id == incident_id).first()
    if item is None: raise HTTPException(404, "Incident not found")
    if item.status != "resolved": raise HTTPException(409, "Only resolved incidents can be explicitly reopened")
    old_status = item.status; item.status = "open"; item.resolved_at = None; item.closed_at = None; item.updated_at = datetime.utcnow()
    _history(db, item, "reopened", current_user.id, old_status, "open", "Explicit operator reopen")
    _audit(db, current_user.id, "REOPEN", f"incidents:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("incidents:read"))):
    item = db.query(Incident).filter(Incident.id == incident_id).first()
    if item is None: raise HTTPException(404, "Incident not found")
    result = _serialize(db, item)
    result["sla"] = timer_view(db, item)
    result["sla_history"] = [{"id": row.id, "action": row.action, "details": row.details, "created_at": row.created_at} for row in db.query(IncidentSLAHistory).filter(IncidentSLAHistory.incident_id == item.id).order_by(IncidentSLAHistory.created_at.asc()).all()]
    result["history"] = [{"id": row.id, "action": row.action, "actor_id": row.actor_id, "old_value": row.old_value, "new_value": row.new_value, "reason": row.reason, "created_at": row.created_at} for row in db.query(IncidentHistory).filter(IncidentHistory.incident_id == item.id).order_by(IncidentHistory.created_at.asc(), IncidentHistory.id.asc()).limit(500).all()]
    db.commit()
    return result


@router.patch("/{incident_id}")
def update_incident(incident_id: int, payload: IncidentUpdatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:update"))):
    item = db.query(Incident).filter(Incident.id == incident_id).first()
    if item is None: raise HTTPException(404, "Incident not found")
    values = payload.model_dump(exclude_unset=True)
    if "assigned_to" in values and values["assigned_to"] is not None and db.query(User).filter(User.id == values["assigned_to"], User.status == "active").first() is None:
        raise HTTPException(422, "Assigned user does not exist or is inactive")
    old_status = item.status
    new_status = values.get("status", old_status)
    allowed_transitions = {"open": {"open", "investigating", "pending", "resolved"}, "investigating": {"investigating", "pending", "resolved"}, "pending": {"pending", "investigating", "resolved"}, "resolved": {"resolved", "closed"}, "closed": {"closed"}}
    if new_status not in allowed_transitions.get(old_status, set()):
        raise HTTPException(409, f"Invalid Incident transition: {old_status} -> {new_status}")
    if values.get("rca_incident_id"):
        try: link_rca(db, item, values["rca_incident_id"])
        except LookupError as exc: raise HTTPException(404, str(exc))
        values.pop("rca_incident_id")
    old_assignee = item.assigned_to
    for key, value in values.items(): setattr(item, key, value)
    now = datetime.utcnow()
    if item.status == "resolved" and item.resolved_at is None: item.resolved_at = now
    if item.status == "closed":
        if item.resolved_at is None: item.resolved_at = now
        if item.closed_at is None: item.closed_at = now
    if item.status in ACTIVE_STATUSES: item.closed_at = None; item.resolved_at = None
    if new_status != old_status:
        _history(db, item, "resolved" if new_status == "resolved" else "closed" if new_status == "closed" else "status_changed", current_user.id, old_status, new_status)
    if "assigned_to" in values and values["assigned_to"] != old_assignee:
        _history(db, item, "assigned" if old_assignee is None else "reassigned", current_user.id, str(old_assignee) if old_assignee is not None else None, str(values["assigned_to"]) if values["assigned_to"] is not None else None)
    evaluate_timer(db, item)
    item.updated_at = datetime.utcnow(); _audit(db, current_user.id, "UPDATE", f"incidents:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{incident_id}/comments", status_code=201)
def add_comment(incident_id: int, payload: CommentPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:update"))):
    if db.query(Incident).filter(Incident.id == incident_id).first() is None: raise HTTPException(404, "Incident not found")
    item = IncidentComment(incident_id=incident_id, author_id=current_user.id, body=payload.body, created_at=datetime.utcnow()); db.add(item)
    incident = db.query(Incident).filter(Incident.id == incident_id).first(); _history(db, incident, "comment_added", current_user.id, reason=payload.body)
    _audit(db, current_user.id, "COMMENT", f"incidents:{incident_id}"); db.commit(); db.refresh(item)
    return item


@router.post("/{incident_id}/attachments", status_code=201)
def add_attachment(incident_id: int, payload: AttachmentPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("incidents:update"))):
    if db.query(Incident).filter(Incident.id == incident_id).first() is None: raise HTTPException(404, "Incident not found")
    item = IncidentAttachment(incident_id=incident_id, uploaded_by=current_user.id, created_at=datetime.utcnow(), **payload.model_dump()); db.add(item); _audit(db, current_user.id, "ATTACHMENT", f"incidents:{incident_id}"); db.commit(); db.refresh(item)
    return item
