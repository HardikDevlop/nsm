from datetime import datetime
from typing import Any
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import AuditLog, Incident, Problem, ProblemHistory, ProblemIncident, RCAIncident, User, utc_now

router = APIRouter(prefix="/api/v1/problems", tags=["Problem Management"])


def _now() -> datetime:
    return utc_now()

ALLOWED_TRANSITIONS = {
    "open": {"open", "in_progress"},
    "in_progress": {"in_progress", "known_error", "resolved"},
    "known_error": {"known_error", "resolved"},
    "resolved": {"resolved", "closed", "in_progress"},
    "closed": {"closed"},
}


class ProblemCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str = Field(default="other", pattern="^(availability|performance|security|capacity|other)$")
    priority: str = Field(default="p3", pattern="^p[1-4]$")
    root_cause: str | None = Field(default=None, max_length=10000)
    workaround: str | None = Field(default=None, max_length=10000)
    known_error: str | None = Field(default=None, max_length=10000)
    permanent_fix: str | None = Field(default=None, max_length=10000)
    owner_id: int | None = Field(default=None, gt=0)
    incident_ids: list[int] = Field(default_factory=list, max_length=500)


class ProblemUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, pattern="^(availability|performance|security|capacity|other)$")
    priority: str | None = Field(default=None, pattern="^p[1-4]$")
    status: str | None = Field(default=None, pattern="^(open|known_error|in_progress|resolved|closed)$")
    root_cause: str | None = Field(default=None, max_length=10000)
    workaround: str | None = Field(default=None, max_length=10000)
    known_error: str | None = Field(default=None, max_length=10000)
    permanent_fix: str | None = Field(default=None, max_length=10000)
    owner_id: int | None = Field(default=None, gt=0)


def _history(db: Session, problem_id: int, user_id: int, action: str, field: str | None = None, old: Any = None, new: Any = None) -> None:
    db.add(ProblemHistory(problem_id=problem_id, changed_by=user_id, action=action, field_name=field, old_value=None if old is None else json.dumps(old, default=str), new_value=None if new is None else json.dumps(new, default=str), created_at=_now()))


def _audit(db: Session, user_id: int, action: str, resource: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource))


def _validate_owner(db: Session, owner_id: int | None) -> None:
    if owner_id is not None and db.query(User).filter(User.id == owner_id, User.status == "active").first() is None:
        raise HTTPException(422, "Problem owner does not exist or is inactive")


def _change_action(field: str, value: Any) -> str:
    if field == "status":
        return str(value) if value in {"known_error", "resolved", "closed"} else "status_changed"
    return {"priority": "priority_changed", "owner_id": "owner_changed"}.get(field, "edited")


def _serialize(db: Session, item: Problem) -> dict[str, Any]:
    links = db.query(ProblemIncident).filter(ProblemIncident.problem_id == item.id).order_by(ProblemIncident.linked_at.asc()).all()
    incident_ids = [link.incident_id for link in links]
    incidents = db.query(Incident).filter(Incident.id.in_(incident_ids)).order_by(Incident.created_at.asc(), Incident.id.asc()).all() if incident_ids else []
    rca_ids = [incident.rca_incident_id for incident in incidents if incident.rca_incident_id is not None]
    rcas = {rca.id: rca for rca in db.query(RCAIncident).filter(RCAIncident.id.in_(rca_ids)).all()} if rca_ids else {}
    incident_summaries = [{
        "id": incident.id,
        "title": incident.title,
        "status": incident.status,
        "priority": incident.priority,
        "rca": ({"id": rca.id, "reference": f"RCA-{rca.id}", "status": "available", "probable_root_cause": rca.root_label, "root_kind": rca.root_kind, "root_label": rca.root_label, "confidence": rca.confidence, "impact_summary": rca.impact_summary, "updated_at": rca.updated_at} if (rca := rcas.get(incident.rca_incident_id)) else None),
    } for incident in incidents]
    return {"id": item.id, "number": item.number, "title": item.title, "description": item.description, "category": item.category, "priority": item.priority, "status": item.status, "root_cause": item.root_cause, "workaround": item.workaround, "known_error": item.known_error, "permanent_fix": item.permanent_fix, "owner_id": item.owner_id, "created_by": item.created_by, "created_at": item.created_at, "updated_at": item.updated_at, "closed_at": item.closed_at, "incident_ids": incident_ids, "incidents": incident_summaries, "history": [{"id": row.id, "action": row.action, "field_name": row.field_name, "old_value": row.old_value, "new_value": row.new_value, "created_at": row.created_at} for row in db.query(ProblemHistory).filter(ProblemHistory.problem_id == item.id).order_by(ProblemHistory.created_at.asc(), ProblemHistory.id.asc()).all()]}


@router.get("")
def list_problems(status: str | None = None, category: str | None = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("problems:read"))):
    query = db.query(Problem)
    if status: query = query.filter(Problem.status == status)
    if category: query = query.filter(Problem.category == category)
    rows = query.order_by(Problem.updated_at.desc()).offset(skip).limit(limit).all()
    return {"items": [_serialize(db, row) for row in rows], "skip": skip, "limit": limit}


@router.post("", status_code=201)
def create_problem(payload: ProblemCreatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("problems:create"))):
    now = _now()
    _validate_owner(db, payload.owner_id)
    incident_ids = list(dict.fromkeys(payload.incident_ids))
    missing_incidents = [incident_id for incident_id in incident_ids if db.query(Incident).filter(Incident.id == incident_id).first() is None]
    if missing_incidents:
        raise HTTPException(404, f"Incident {missing_incidents[0]} not found")
    item = Problem(number="PENDING", **payload.model_dump(exclude={"incident_ids"}), created_by=current_user.id, created_at=now, updated_at=now)
    db.add(item); db.flush(); item.number = f"PRB-{item.id:06d}"
    for incident_id in incident_ids:
        db.add(ProblemIncident(problem_id=item.id, incident_id=incident_id, linked_by=current_user.id, linked_at=now))
        _history(db, item.id, current_user.id, "incident_linked", new={"incident_id": incident_id})
    _history(db, item.id, current_user.id, "created", new=payload.model_dump()); _audit(db, current_user.id, "CREATE", f"problems:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{problem_id}")
def get_problem(problem_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("problems:read"))):
    item = db.query(Problem).filter(Problem.id == problem_id).first()
    if item is None: raise HTTPException(404, "Problem not found")
    return _serialize(db, item)


@router.patch("/{problem_id}")
def update_problem(problem_id: int, payload: ProblemUpdatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("problems:update"))):
    item = db.query(Problem).filter(Problem.id == problem_id).first()
    if item is None: raise HTTPException(404, "Problem not found")
    values = payload.model_dump(exclude_unset=True)
    if "owner_id" in values:
        _validate_owner(db, values["owner_id"])
    new_status = values.get("status", item.status)
    if new_status not in ALLOWED_TRANSITIONS.get(item.status, set()):
        raise HTTPException(409, f"Invalid Problem transition: {item.status} -> {new_status}")
    for field, value in values.items():
        old = getattr(item, field)
        setattr(item, field, value)
        if old != value:
            _history(db, item.id, current_user.id, _change_action(field, value), field, old, value)
    if item.status in {"resolved", "closed"} and item.closed_at is None: item.closed_at = _now()
    if item.status in {"open", "known_error", "in_progress"}: item.closed_at = None
    item.updated_at = _now(); _audit(db, current_user.id, "UPDATE", f"problems:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{problem_id}/incidents/{incident_id}", status_code=201)
def link_incident(problem_id: int, incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("problems:update"))):
    if db.query(Problem).filter(Problem.id == problem_id).first() is None: raise HTTPException(404, "Problem not found")
    if db.query(Incident).filter(Incident.id == incident_id).first() is None: raise HTTPException(404, "Incident not found")
    if db.query(ProblemIncident).filter_by(problem_id=problem_id, incident_id=incident_id).first(): raise HTTPException(409, "Incident already linked to problem")
    db.add(ProblemIncident(problem_id=problem_id, incident_id=incident_id, linked_by=current_user.id, linked_at=_now())); _history(db, problem_id, current_user.id, "incident_linked", new={"incident_id": incident_id}); _audit(db, current_user.id, "LINK_INCIDENT", f"problems:{problem_id}")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Incident already linked to problem") from exc
    return {"problem_id": problem_id, "incident_id": incident_id, "linked": True}


@router.get("/{problem_id}/history")
def problem_history(problem_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("problems:read"))):
    if db.query(Problem).filter(Problem.id == problem_id).first() is None: raise HTTPException(404, "Problem not found")
    return db.query(ProblemHistory).filter(ProblemHistory.problem_id == problem_id).order_by(ProblemHistory.created_at.asc(), ProblemHistory.id.asc()).all()
