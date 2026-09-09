from datetime import datetime
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.changes.service import ChangeTransitionError, transition_change
from backend.models import AuditLog, CIRelationship, ConfigurationItem, Incident, Problem, ChangeCI, ChangeHistory, ChangeIncident, ChangeProblem, ChangeRequest, User

router = APIRouter(prefix="/api/v1/changes", tags=["Change Management"])


class ChangeCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str = Field(default="normal", pattern="^(standard|normal|emergency)$")
    risk: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    impact: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    priority: str = Field(default="p3", pattern="^p[1-4]$")
    owner_id: int | None = Field(default=None, gt=0)
    approval_required: bool = False
    maintenance_start: datetime | None = None
    maintenance_end: datetime | None = None
    implementation_plan: str | None = Field(default=None, max_length=10000)
    rollback_plan: str | None = Field(default=None, max_length=10000)
    ci_ids: list[int] = Field(default_factory=list, max_length=500)
    incident_ids: list[int] = Field(default_factory=list, max_length=500)
    problem_ids: list[int] = Field(default_factory=list, max_length=500)

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
    priority: str | None = Field(default=None, pattern="^p[1-4]$")
    owner_id: int | None = Field(default=None, gt=0)
    approval_required: bool | None = None
    status: str | None = Field(default=None, pattern="^(draft|submitted|approved|rejected|scheduled|implementing|implemented|rolled_back|closed)$")
    maintenance_start: datetime | None = None
    maintenance_end: datetime | None = None
    implementation_plan: str | None = Field(default=None, max_length=10000)
    rollback_plan: str | None = Field(default=None, max_length=10000)
    implementation_result: str | None = Field(default=None, max_length=10000)
    implementation_failure_reason: str | None = Field(default=None, max_length=10000)
    rollback_result: str | None = Field(default=None, max_length=10000)
    rollback_status: str | None = Field(default=None, pattern="^(planned|in_progress|completed|failed)$")
    closure_note: str | None = Field(default=None, max_length=10000)


class ApprovalPayload(BaseModel):
    comment: str | None = Field(default=None, max_length=5000)


class ImplementationPayload(BaseModel):
    result: str | None = Field(default=None, max_length=10000)
    failure_reason: str | None = Field(default=None, max_length=10000)


class RollbackPayload(BaseModel):
    result: str | None = Field(default=None, max_length=10000)
    status: str = Field(default="completed", pattern="^(planned|in_progress|completed|failed)$")


def _history(db: Session, change_id: int, user_id: int, action: str, field: str | None = None, old: Any = None, new: Any = None) -> None:
    db.add(ChangeHistory(change_id=change_id, changed_by=user_id, action=action, field_name=field, old_value=None if old is None else json.dumps(old, default=str), new_value=None if new is None else json.dumps(new, default=str), created_at=datetime.utcnow()))


def _audit(db: Session, user_id: int, action: str, resource: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource))


def _serialize(db: Session, item: ChangeRequest) -> dict[str, Any]:
    cis = db.query(ChangeCI).filter(ChangeCI.change_id == item.id).order_by(ChangeCI.linked_at.asc()).all()
    incidents = db.query(ChangeIncident).filter(ChangeIncident.change_id == item.id).order_by(ChangeIncident.linked_at.asc()).all()
    problems = db.query(ChangeProblem).filter(ChangeProblem.change_id == item.id).order_by(ChangeProblem.linked_at.asc()).all()
    incident_rows = db.query(Incident).filter(Incident.id.in_([row.incident_id for row in incidents])).all() if incidents else []
    problem_rows = db.query(Problem).filter(Problem.id.in_([row.problem_id for row in problems])).all() if problems else []
    ci_rows = db.query(ConfigurationItem).filter(ConfigurationItem.id.in_([row.ci_id for row in cis])).all() if cis else []
    return {"id": item.id, "number": item.number, "title": item.title, "description": item.description, "category": item.category, "risk": item.risk, "impact": item.impact, "priority": item.priority, "status": item.status, "requested_by": item.requested_by, "owner_id": item.owner_id, "approved_by": item.approved_by, "approved_at": item.approved_at, "approval_required": item.approval_required, "approval_comment": item.approval_comment, "rejected_by": item.rejected_by, "rejected_at": item.rejected_at, "rejection_comment": item.rejection_comment, "maintenance_start": item.maintenance_start, "maintenance_end": item.maintenance_end, "implementation_plan": item.implementation_plan, "rollback_plan": item.rollback_plan, "implementation_result": item.implementation_result, "implementation_failure_reason": item.implementation_failure_reason, "rollback_result": item.rollback_result, "rollback_status": item.rollback_status, "closure_note": item.closure_note, "created_at": item.created_at, "updated_at": item.updated_at, "closed_at": item.closed_at, "ci_ids": [row.ci_id for row in cis], "cis": [{"id": row.id, "name": row.name, "status": getattr(row, "status", None)} for row in ci_rows], "incident_ids": [row.incident_id for row in incidents], "incidents": [{"id": row.id, "title": row.title, "status": row.status, "priority": getattr(row, "priority", None)} for row in incident_rows], "problem_ids": [row.problem_id for row in problems], "problems": [{"id": row.id, "number": row.number, "title": row.title, "status": row.status, "priority": getattr(row, "priority", None)} for row in problem_rows], "history": [{"id": row.id, "action": row.action, "field_name": row.field_name, "old_value": row.old_value, "new_value": row.new_value, "created_at": row.created_at} for row in db.query(ChangeHistory).filter(ChangeHistory.change_id == item.id).order_by(ChangeHistory.created_at.asc(), ChangeHistory.id.asc()).all()]}


def _validate_links(db: Session, ci_ids: list[int], incident_ids: list[int], problem_ids: list[int] | None = None) -> None:
    if ci_ids and db.query(ConfigurationItem.id).filter(ConfigurationItem.id.in_(ci_ids)).count() != len(set(ci_ids)):
        raise HTTPException(404, "One or more CMDB items not found")
    if incident_ids and db.query(Incident.id).filter(Incident.id.in_(incident_ids)).count() != len(set(incident_ids)):
        raise HTTPException(404, "One or more incidents not found")
    if problem_ids and db.query(Problem.id).filter(Problem.id.in_(problem_ids)).count() != len(set(problem_ids)):
        raise HTTPException(404, "One or more problems not found")


def _validate_owner(db: Session, owner_id: int | None) -> None:
    if owner_id is not None and db.query(User).filter(User.id == owner_id, User.status == "active").first() is None:
        raise HTTPException(422, "Owner must reference an active user")


def _change_or_404(db: Session, change_id: int) -> ChangeRequest:
    item = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if item is None:
        raise HTTPException(404, "Change request not found")
    return item


def _transition_or_409(db: Session, item: ChangeRequest, target: str, user_id: int) -> None:
    try:
        transition_change(db, item, target, user_id)
    except ChangeTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("")
def list_changes(status: str | None = None, risk: str | None = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("changes:read"))):
    query = db.query(ChangeRequest)
    if status: query = query.filter(ChangeRequest.status == status)
    if risk: query = query.filter(ChangeRequest.risk == risk)
    return {"items": [_serialize(db, row) for row in query.order_by(ChangeRequest.updated_at.desc()).offset(skip).limit(limit).all()], "skip": skip, "limit": limit}


@router.get("/available/incidents")
def available_incidents(db: Session = Depends(get_db), _: User = Depends(require_permission("incidents:read"))):
    return db.query(Incident).order_by(Incident.updated_at.desc()).limit(500).all()


@router.get("/available/problems")
def available_problems(db: Session = Depends(get_db), _: User = Depends(require_permission("problems:read"))):
    return db.query(Problem).order_by(Problem.updated_at.desc()).limit(500).all()


@router.get("/available/cis")
def available_cis(db: Session = Depends(get_db), _: User = Depends(require_permission("cmdb:read"))):
    return db.query(ConfigurationItem).filter(ConfigurationItem.deleted_at.is_(None)).order_by(ConfigurationItem.name).limit(500).all()


@router.post("", status_code=201)
def create_change(payload: ChangeCreatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:create"))):
    _validate_links(db, payload.ci_ids, payload.incident_ids, payload.problem_ids)
    _validate_owner(db, payload.owner_id)
    now = datetime.utcnow(); item = ChangeRequest(number="PENDING", **payload.model_dump(exclude={"ci_ids", "incident_ids", "problem_ids"}), requested_by=current_user.id, created_at=now, updated_at=now)
    db.add(item); db.flush(); item.number = f"CHG-{item.id:06d}"
    for ci_id in set(payload.ci_ids): db.add(ChangeCI(change_id=item.id, ci_id=ci_id, linked_by=current_user.id, linked_at=now))
    for incident_id in set(payload.incident_ids): db.add(ChangeIncident(change_id=item.id, incident_id=incident_id, linked_by=current_user.id, linked_at=now))
    for problem_id in set(payload.problem_ids): db.add(ChangeProblem(change_id=item.id, problem_id=problem_id, linked_by=current_user.id, linked_at=now))
    _history(db, item.id, current_user.id, "created", new=payload.model_dump()); _audit(db, current_user.id, "CREATE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{change_id}")
def get_change(change_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("changes:read"))):
    item = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if item is None: raise HTTPException(404, "Change request not found")
    return _serialize(db, item)


@router.patch("/{change_id}")
def update_change(change_id: int, payload: ChangeUpdatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id)
    values = payload.model_dump(exclude_unset=True)
    if "owner_id" in values:
        _validate_owner(db, values["owner_id"])
    start, end = values.get("maintenance_start", item.maintenance_start), values.get("maintenance_end", item.maintenance_end)
    if start and end and end <= start: raise HTTPException(422, "maintenance_end must be after maintenance_start")
    target = values.pop("status", None)
    if target is not None:
        _transition_or_409(db, item, target, current_user.id)
    for field, value in values.items():
        old = getattr(item, field); setattr(item, field, value)
        if old != value:
            _history(db, item.id, current_user.id, "assigned" if field == "owner_id" else "updated", field, old, value)
    item.updated_at = datetime.utcnow(); _audit(db, current_user.id, "UPDATE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/approve")
def approve_change(change_id: int, payload: ApprovalPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:approve"))):
    item = _change_or_404(db, change_id)
    _transition_or_409(db, item, "approved", current_user.id)
    item.approved_by, item.approved_at, item.approval_comment = current_user.id, datetime.utcnow(), payload.comment
    _audit(db, current_user.id, "APPROVE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/submit")
def submit_change(change_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "submitted", current_user.id)
    _audit(db, current_user.id, "SUBMIT", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/reject")
def reject_change(change_id: int, payload: ApprovalPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:approve"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "rejected", current_user.id)
    item.rejected_by, item.rejected_at, item.rejection_comment = current_user.id, datetime.utcnow(), payload.comment
    _audit(db, current_user.id, "REJECT", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/schedule")
def schedule_change(change_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "scheduled", current_user.id)
    _audit(db, current_user.id, "SCHEDULE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/implementation/start")
def start_implementation(change_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "implementing", current_user.id)
    _audit(db, current_user.id, "IMPLEMENT_START", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/implementation/complete")
def complete_implementation(change_id: int, payload: ImplementationPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "implemented", current_user.id)
    item.implementation_result, item.implementation_failure_reason = payload.result, None
    _audit(db, current_user.id, "IMPLEMENT_COMPLETE", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/implementation/fail")
def fail_implementation(change_id: int, payload: ImplementationPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id)
    if item.status != "implementing":
        raise HTTPException(409, "Implementation can fail only while implementing")
    item.implementation_failure_reason, item.updated_at = payload.failure_reason, datetime.utcnow()
    _history(db, item.id, current_user.id, "implementation_failed", new=payload.failure_reason)
    _audit(db, current_user.id, "IMPLEMENT_FAIL", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/rollback")
def rollback_change(change_id: int, payload: RollbackPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "rolled_back", current_user.id)
    item.rollback_result, item.rollback_status = payload.result, payload.status
    _audit(db, current_user.id, "ROLLBACK", f"changes:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{change_id}/close")
def close_change(change_id: int, payload: ApprovalPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    item = _change_or_404(db, change_id); _transition_or_409(db, item, "closed", current_user.id)
    if payload.comment is not None: item.closure_note = payload.comment
    _audit(db, current_user.id, "CLOSE", f"changes:{item.id}"); db.commit(); db.refresh(item)
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


@router.post("/{change_id}/problems/{problem_id}", status_code=201)
def link_problem(change_id: int, problem_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    if db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first() is None: raise HTTPException(404, "Change request not found")
    if db.query(Problem).filter(Problem.id == problem_id).first() is None: raise HTTPException(404, "Problem not found")
    if db.query(ChangeProblem).filter_by(change_id=change_id, problem_id=problem_id).first(): raise HTTPException(409, "Problem already linked")
    db.add(ChangeProblem(change_id=change_id, problem_id=problem_id, linked_by=current_user.id, linked_at=datetime.utcnow())); _history(db, change_id, current_user.id, "problem_linked", new={"problem_id": problem_id}); _audit(db, current_user.id, "LINK_PROBLEM", f"changes:{change_id}"); db.commit()
    return {"change_id": change_id, "problem_id": problem_id, "linked": True}


def _unlink_relationship(db: Session, change_id: int, user_id: int, relationship: Any, action: str, resource: str, identifier: dict[str, int]) -> None:
    if relationship is None:
        raise HTTPException(404, "Relationship not found")
    db.delete(relationship)
    _history(db, change_id, user_id, action, new=identifier)
    _audit(db, user_id, action.upper(), f"changes:{change_id}")
    db.commit()


@router.delete("/{change_id}/cis/{ci_id}")
def unlink_ci(change_id: int, ci_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    _change_or_404(db, change_id)
    relationship = db.query(ChangeCI).filter_by(change_id=change_id, ci_id=ci_id).first()
    _unlink_relationship(db, change_id, current_user.id, relationship, "ci_unlinked", "CI", {"ci_id": ci_id})
    return {"change_id": change_id, "ci_id": ci_id, "linked": False}


@router.delete("/{change_id}/incidents/{incident_id}")
def unlink_incident(change_id: int, incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    _change_or_404(db, change_id)
    relationship = db.query(ChangeIncident).filter_by(change_id=change_id, incident_id=incident_id).first()
    _unlink_relationship(db, change_id, current_user.id, relationship, "incident_unlinked", "incident", {"incident_id": incident_id})
    return {"change_id": change_id, "incident_id": incident_id, "linked": False}


@router.delete("/{change_id}/problems/{problem_id}")
def unlink_problem(change_id: int, problem_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("changes:update"))):
    _change_or_404(db, change_id)
    relationship = db.query(ChangeProblem).filter_by(change_id=change_id, problem_id=problem_id).first()
    _unlink_relationship(db, change_id, current_user.id, relationship, "problem_unlinked", "problem", {"problem_id": problem_id})
    return {"change_id": change_id, "problem_id": problem_id, "linked": False}
