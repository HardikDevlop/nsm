from datetime import datetime
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import AuditLog, CIRelationship, ConfigurationItem, Incident, ChangeCI, ChangeHistory, ChangeIncident, ChangeRequest, User

router = APIRouter(prefix="/api/v1/changes", tags=["Change Management"])


class ChangeCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str = Field(default="normal", pattern="^(standard|normal|emergency)$")
    risk: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    impact: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    maintenance_start: datetime | None = None
    maintenance_end: datetime | None = None
    implementation_plan: str | None = Field(default=None, max_length=10000)
    rollback_plan: str | None = Field(default=None, max_length=10000)
    ci_ids: list[int] = Field(default_factory=list, max_length=500)
    incident_ids: list[int] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def valid_window(self):
        if self.maintenance_start and self.maintenance_end and self.maintenance_end <= self.maintenance_start:
            raise ValueError("maintenance_end must be after maintenance_start")
        return self


class ChangeUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, pattern="^(standard|normal|emergency)$")
    risk: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    impact: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    status: str | None = Field(default=None, pattern="^(draft|submitted|approved|rejected|scheduled|implementing|implemented|rolled_back|closed)$")
    maintenance_start: datetime | None = None
    maintenance_end: datetime | None = None
    implementation_plan: str | None = Field(default=None, max_length=10000)
    rollback_plan: str | None = Field(default=None, max_length=10000)
    closure_note: str | None = Field(default=None, max_length=10000)


class ApprovalPayload(BaseModel):
    comment: str | None = Field(default=None, max_length=5000)


def _history(db: Session, change_id: int, user_id: int, action: str, field: str | None = None, old: Any = None, new: Any = None) -> None:
    db.add(ChangeHistory(change_id=change_id, changed_by=user_id, action=action, field_name=field, old_value=None if old is None else json.dumps(old, default=str), new_value=None if new is None else json.dumps(new, default=str), created_at=datetime.utcnow()))


def _audit(db: Session, user_id: int, action: str, resource: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource))


def _serialize(db: Session, item: ChangeRequest) -> dict[str, Any]:
    cis = db.query(ChangeCI).filter(ChangeCI.change_id == item.id).order_by(ChangeCI.linked_at.asc()).all()
    incidents = db.query(ChangeIncident).filter(ChangeIncident.change_id == item.id).order_by(ChangeIncident.linked_at.asc()).all()
    return {"id": item.id, "number": item.number, "title": item.title, "description": item.description, "category": item.category, "risk": item.risk, "impact": item.impact, "status": item.status, "requested_by": item.requested_by, "approved_by": item.approved_by, "approval_comment": item.approval_comment, "maintenance_start": item.maintenance_start, "maintenance_end": item.maintenance_end, "implementation_plan": item.implementation_plan, "rollback_plan": item.rollback_plan, "closure_note": item.closure_note, "created_at": item.created_at, "updated_at": item.updated_at, "closed_at": item.closed_at, "ci_ids": [row.ci_id for row in cis], "incident_ids": [row.incident_id for row in incidents], "history": [{"id": row.id, "action": row.action, "field_name": row.field_name, "old_value": row.old_value, "new_value": row.new_value, "created_at": row.created_at} for row in db.query(ChangeHistory).filter(ChangeHistory.change_id == item.id).order_by(ChangeHistory.created_at.asc(), ChangeHistory.id.asc()).all()]}


def _validate_links(db: Session, ci_ids: list[int], incident_ids: list[int]) -> None:
    if ci_ids and db.query(ConfigurationItem.id).filter(ConfigurationItem.id.in_(ci_ids)).count() != len(set(ci_ids)):
        raise HTTPException(404, "One or more CMDB items not found")
    if incident_ids and db.query(Incident.id).filter(Incident.id.in_(incident_ids)).count() != len(set(incident_ids)):
        raise HTTPException(404, "One or more incidents not found")


@router.get("")
def list_changes(status: str | None = None, risk: str | None = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("changes:read"))):
    query = db.query(ChangeRequest)
    if status: query = query.filter(ChangeRequest.status == status)
    if risk: query = query.filter(ChangeRequest.risk == risk)
    return {"items": [_serialize(db, row) for row in query.order_by(ChangeRequest.updated_at.desc()).offset(skip).limit(limit).all()], "skip": skip, "limit": limit}


@router.post("", status_code=201)
def create_change(payload: ChangeCreatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:create"))):
    _validate_links(db, payload.ci_ids, payload.incident_ids)
    now = datetime.utcnow(); item = ChangeRequest(number="PENDING", **payload.model_dump(exclude={"ci_ids", "incident_ids"}), requested_by=current_user.id, created_at=now, updated_at=now)
    db.add(item); db.flush(); item.number = f"CHG-{item.id:06d}"
    for ci_id in set(payload.ci_ids): db.add(ChangeCI(change_id=item.id, ci_id=ci_id, linked_by=current_user.id, linked_at=now))
    for incident_id in set(payload.incident_ids): db.add(ChangeIncident(change_id=item.id, incident_id=incident_id, linked_by=current_user.id, linked_at=now))
    _history(db, item.id, current_user.id, "created", new=payload.model_dump()); _audit(db, current_user.id, "CREATE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{change_id}")
def get_change(change_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("changes:read"))):
    item = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if item is None: raise HTTPException(404, "Change request not found")
    return _serialize(db, item)


@router.patch("/{change_id}")
def update_change(change_id: int, payload: ChangeUpdatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if item is None: raise HTTPException(404, "Change request not found")
    values = payload.model_dump(exclude_unset=True)
    start, end = values.get("maintenance_start", item.maintenance_start), values.get("maintenance_end", item.maintenance_end)
    if start and end and end <= start: raise HTTPException(422, "maintenance_end must be after maintenance_start")
    for field, value in values.items():
        old = getattr(item, field); setattr(item, field, value)
        if old != value: _history(db, item.id, current_user.id, "updated", field, old, value)
    if item.status in {"closed", "rolled_back"} and item.closed_at is None: item.closed_at = datetime.utcnow()
    item.updated_at = datetime.utcnow(); _audit(db, current_user.id, "UPDATE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/approve")
def approve_change(change_id: int, payload: ApprovalPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:approve"))):
    item = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if item is None: raise HTTPException(404, "Change request not found")
    if item.status not in {"submitted", "draft"}: raise HTTPException(409, "Only draft or submitted changes can be approved")
    item.status, item.approved_by, item.approval_comment, item.updated_at = "approved", current_user.id, payload.comment, datetime.utcnow()
    _history(db, item.id, current_user.id, "approved", new=payload.comment); _audit(db, current_user.id, "APPROVE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/cis/{ci_id}", status_code=201)
def link_ci(change_id: int, ci_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    if db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first() is None: raise HTTPException(404, "Change request not found")
    if db.query(ConfigurationItem).filter(ConfigurationItem.id == ci_id).first() is None: raise HTTPException(404, "CMDB item not found")
    if db.query(ChangeCI).filter_by(change_id=change_id, ci_id=ci_id).first(): raise HTTPException(409, "CMDB item already linked")
    db.add(ChangeCI(change_id=change_id, ci_id=ci_id, linked_by=current_user.id, linked_at=datetime.utcnow())); _history(db, change_id, current_user.id, "ci_linked", new={"ci_id": ci_id}); _audit(db, current_user.id, "LINK_CI", f"changes:{change_id}"); db.commit()
    return {"change_id": change_id, "ci_id": ci_id, "linked": True}


@router.post("/{change_id}/incidents/{incident_id}", status_code=201)
def link_incident(change_id: int, incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    if db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first() is None: raise HTTPException(404, "Change request not found")
    if db.query(Incident).filter(Incident.id == incident_id).first() is None: raise HTTPException(404, "Incident not found")
    if db.query(ChangeIncident).filter_by(change_id=change_id, incident_id=incident_id).first(): raise HTTPException(409, "Incident already linked")
    db.add(ChangeIncident(change_id=change_id, incident_id=incident_id, linked_by=current_user.id, linked_at=datetime.utcnow())); _history(db, change_id, current_user.id, "incident_linked", new={"incident_id": incident_id}); _audit(db, current_user.id, "LINK_INCIDENT", f"changes:{change_id}"); db.commit()
    return {"change_id": change_id, "incident_id": incident_id, "linked": True}
