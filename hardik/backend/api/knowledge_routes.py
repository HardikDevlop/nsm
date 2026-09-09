from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.knowledge.service import KnowledgeTransitionError, transition_article
from backend.models import APMService, AuditLog, ChangeRequest, ConfigurationItem, Device, Incident, KnowledgeArticle, KnowledgeArticleHistory, KnowledgeArticleVersion, KnowledgeChangeLink, KnowledgeCILink, KnowledgeDeviceLink, KnowledgeFeedback, KnowledgeIncidentLink, KnowledgeProblemLink, KnowledgeRelatedLink, KnowledgeServiceLink, Problem, User

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])


class ArticleCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    summary: str | None = Field(default=None, max_length=10000)
    article_type: str = Field(default="knowledge", pattern="^(knowledge|known_error|runbook)$")
    category: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=100)
    owner_id: int | None = Field(default=None, gt=0)
    body: str = Field(min_length=1, max_length=100000)
    incident_ids: list[int] = Field(default_factory=list, max_length=500)
    problem_ids: list[int] = Field(default_factory=list, max_length=500)
    device_ids: list[int] = Field(default_factory=list, max_length=500)
    service_ids: list[int] = Field(default_factory=list, max_length=500)


class ArticleUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=220)
    summary: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=100)
    owner_id: int | None = Field(default=None, gt=0)
    body: str | None = Field(default=None, min_length=1, max_length=100000)


class FeedbackPayload(BaseModel):
    helpful: bool


def _audit(db: Session, user_id: int, action: str, resource: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource))


def _validate_owner(db: Session, owner_id: int | None) -> None:
    if owner_id is not None and db.query(User).filter(User.id == owner_id, User.status == "active").first() is None:
        raise HTTPException(422, "Owner must reference an active user")


def _serialize(db: Session, item: KnowledgeArticle, include_body: bool = True) -> dict[str, Any]:
    version = db.query(KnowledgeArticleVersion).filter_by(article_id=item.id, version=item.current_version).first()
    changes = db.query(KnowledgeChangeLink).filter_by(article_id=item.id).all()
    cis = db.query(KnowledgeCILink).filter_by(article_id=item.id).all()
    related = db.query(KnowledgeRelatedLink).filter_by(article_id=item.id).all()
    change_rows = db.query(ChangeRequest).filter(ChangeRequest.id.in_([x.change_id for x in changes])).all() if changes else []
    ci_rows = db.query(ConfigurationItem).filter(ConfigurationItem.id.in_([x.ci_id for x in cis])).all() if cis else []
    related_rows = db.query(KnowledgeArticle).filter(KnowledgeArticle.id.in_([x.related_article_id for x in related])).all() if related else []
    return {"id": item.id, "number": item.number, "title": item.title, "summary": item.summary, "article_type": item.article_type, "category": item.category, "tags": item.tags or [], "owner_id": item.owner_id, "status": item.status, "published_at": item.published_at, "view_count": item.view_count, "helpful_count": item.helpful_count, "not_helpful_count": item.not_helpful_count, "current_version": item.current_version, "body": version.body if version and include_body else None, "incident_ids": [x.incident_id for x in db.query(KnowledgeIncidentLink).filter_by(article_id=item.id).all()], "problem_ids": [x.problem_id for x in db.query(KnowledgeProblemLink).filter_by(article_id=item.id).all()], "change_ids": [x.change_id for x in changes], "ci_ids": [x.ci_id for x in cis], "device_ids": [x.device_id for x in db.query(KnowledgeDeviceLink).filter_by(article_id=item.id).all()], "service_ids": [x.service_id for x in db.query(KnowledgeServiceLink).filter_by(article_id=item.id).all()], "changes": [{"id": x.id, "number": x.number, "title": x.title, "status": x.status} for x in change_rows], "cis": [{"id": x.id, "name": x.name, "status": x.lifecycle_state} for x in ci_rows], "related_article_ids": [x.related_article_id for x in related], "related_articles": [{"id": x.id, "number": x.number, "title": x.title, "status": x.status} for x in related_rows], "usage": {"incident_count": len(db.query(KnowledgeIncidentLink).filter_by(article_id=item.id).all()), "problem_count": len(db.query(KnowledgeProblemLink).filter_by(article_id=item.id).all())}, "versions": [{"version": x.version, "changed_by": x.changed_by, "created_at": x.created_at} for x in db.query(KnowledgeArticleVersion).filter_by(article_id=item.id).order_by(KnowledgeArticleVersion.version.desc()).all()], "history": [{"id": x.id, "action": x.action, "actor_id": x.actor_id, "metadata": x.metadata_json, "created_at": x.created_at} for x in db.query(KnowledgeArticleHistory).filter_by(article_id=item.id).order_by(KnowledgeArticleHistory.created_at.asc(), KnowledgeArticleHistory.id.asc()).all()], "created_at": item.created_at, "updated_at": item.updated_at}


def _validate_links(db: Session, payload: ArticleCreatePayload) -> None:
    checks = ((Incident, payload.incident_ids, "incidents"), (Problem, payload.problem_ids, "problems"), (Device, payload.device_ids, "devices"), (APMService, payload.service_ids, "services"))
    for model, ids, label in checks:
        if ids and db.query(model.id).filter(model.id.in_(set(ids))).count() != len(set(ids)): raise HTTPException(404, f"One or more {label} not found")


def _article_or_404(db: Session, article_id: int) -> KnowledgeArticle:
    item = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if item is None: raise HTTPException(404, "Knowledge article not found")
    return item


def _history(db: Session, article_id: int, actor_id: int, action: str, metadata: dict[str, Any]) -> None:
    db.add(KnowledgeArticleHistory(article_id=article_id, action=action, actor_id=actor_id, metadata_json=metadata, created_at=datetime.utcnow()))


@router.get("")
def list_articles(search: str | None = None, article_type: str | None = None, status: str | None = "published", category: str | None = None, tag: str | None = None, owner_id: int | None = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    query = db.query(KnowledgeArticle)
    if status: query = query.filter(KnowledgeArticle.status == status)
    if article_type: query = query.filter(KnowledgeArticle.article_type == article_type)
    if category: query = query.filter(KnowledgeArticle.category == category)
    if owner_id is not None: query = query.filter(KnowledgeArticle.owner_id == owner_id)
    if tag:
        query = query.filter(KnowledgeArticle.tags.contains([tag]))
    if search:
        pattern = f"%{search}%"
        ids = db.query(KnowledgeArticleVersion.article_id).filter(KnowledgeArticleVersion.body.ilike(pattern)).subquery()
        query = query.filter(or_(KnowledgeArticle.title.ilike(pattern), KnowledgeArticle.id.in_(ids)))
    rows = query.order_by(KnowledgeArticle.updated_at.desc()).offset(skip).limit(limit).all()
    return {"items": [_serialize(db, row, include_body=False) for row in rows], "skip": skip, "limit": limit}


@router.get("/available/incidents")
def available_incidents(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    return db.query(Incident).order_by(Incident.updated_at.desc()).limit(500).all()


@router.get("/available/problems")
def available_problems(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    return db.query(Problem).order_by(Problem.updated_at.desc()).limit(500).all()


@router.get("/available/changes")
def available_changes(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    return db.query(ChangeRequest).order_by(ChangeRequest.updated_at.desc()).limit(500).all()


@router.get("/available/cis")
def available_cis(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    return db.query(ConfigurationItem).filter(ConfigurationItem.deleted_at.is_(None)).order_by(ConfigurationItem.name).limit(500).all()


@router.get("/available/devices")
def available_devices(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    return db.query(Device).order_by(Device.hostname).limit(500).all()


@router.get("/available/services")
def available_services(db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    return db.query(APMService).order_by(APMService.name).limit(500).all()


@router.post("", status_code=201)
def create_article(payload: ArticleCreatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:create"))):
    _validate_links(db, payload); _validate_owner(db, payload.owner_id); now = datetime.utcnow()
    item = KnowledgeArticle(number="PENDING", title=payload.title, summary=payload.summary, article_type=payload.article_type, category=payload.category, tags=payload.tags, owner_id=payload.owner_id, status="draft", current_version=1, created_by=current_user.id, updated_by=current_user.id, created_at=now, updated_at=now)
    db.add(item); db.flush(); item.number = f"KB-{item.id:06d}"
    db.add(KnowledgeArticleVersion(article_id=item.id, version=1, body=payload.body, changed_by=current_user.id, created_at=now))
    for model, link_model, ids in ((Incident, KnowledgeIncidentLink, payload.incident_ids), (Problem, KnowledgeProblemLink, payload.problem_ids), (Device, KnowledgeDeviceLink, payload.device_ids)):
        for target_id in set(ids): db.add(link_model(article_id=item.id, **({"incident_id": target_id} if link_model is KnowledgeIncidentLink else {"problem_id": target_id} if link_model is KnowledgeProblemLink else {"device_id": target_id}), linked_by=current_user.id, linked_at=now))
    for service_id in set(payload.service_ids): db.add(KnowledgeServiceLink(article_id=item.id, service_id=service_id, linked_by=current_user.id, linked_at=now))
    db.add(KnowledgeArticleHistory(article_id=item.id, action="created", actor_id=current_user.id, metadata_json={"number": item.number}, created_at=now)); _audit(db, current_user.id, "CREATE", f"knowledge:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    item = _article_or_404(db, article_id)
    item.view_count = (item.view_count or 0) + 1
    db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.patch("/{article_id}")
def update_article(article_id: int, payload: ArticleUpdatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    item = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if item is None: raise HTTPException(404, "Knowledge article not found")
    values = payload.model_dump(exclude_unset=True); body = values.pop("body", None)
    if "owner_id" in values: _validate_owner(db, values["owner_id"])
    owner_changed = "owner_id" in values and values["owner_id"] != item.owner_id
    for field, value in values.items(): setattr(item, field, value)
    if body is not None:
        item.current_version += 1; db.add(KnowledgeArticleVersion(article_id=item.id, version=item.current_version, body=body, changed_by=current_user.id, created_at=datetime.utcnow()))
    now = datetime.utcnow(); item.updated_by, item.updated_at = current_user.id, now
    db.add(KnowledgeArticleHistory(article_id=item.id, action="owner_changed" if owner_changed else "updated", actor_id=current_user.id, metadata_json={"fields": list(values), "version": item.current_version}, created_at=now)); _audit(db, current_user.id, "UPDATE", f"knowledge:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


def _lifecycle(article_id: int, target: str, db: Session, current_user: User):
    item = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if item is None: raise HTTPException(404, "Knowledge article not found")
    try:
        transition_article(db, item, target, current_user.id)
    except KnowledgeTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    _audit(db, current_user.id, target.upper(), f"knowledge:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.post("/{article_id}/submit-review")
def submit_for_review(article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _lifecycle(article_id, "review", db, current_user)


@router.post("/{article_id}/return-to-draft")
def return_to_draft(article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _lifecycle(article_id, "draft", db, current_user)


@router.post("/{article_id}/publish")
def publish_article(article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _lifecycle(article_id, "published", db, current_user)


@router.post("/{article_id}/retire")
def retire_article(article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _lifecycle(article_id, "retired", db, current_user)


@router.post("/{article_id}/restore")
def restore_article(article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _lifecycle(article_id, "draft", db, current_user)


@router.get("/{article_id}/versions")
def article_versions(article_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    if db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first() is None: raise HTTPException(404, "Knowledge article not found")
    return db.query(KnowledgeArticleVersion).filter_by(article_id=article_id).order_by(KnowledgeArticleVersion.version.desc()).all()


def _link(db: Session, article_id: int, target_id: int, target_model: Any, link_model: Any, target_field: str, action: str, actor_id: int) -> dict[str, Any]:
    _article_or_404(db, article_id)
    if db.query(target_model.id).filter(target_model.id == target_id).first() is None:
        raise HTTPException(404, "Referenced record not found")
    if db.query(link_model).filter_by(article_id=article_id, **{target_field: target_id}).first():
        raise HTTPException(409, "Relationship already exists")
    db.add(link_model(article_id=article_id, **{target_field: target_id}, linked_by=actor_id, linked_at=datetime.utcnow()))
    _history(db, article_id, actor_id, action, {target_field: target_id})
    _audit(db, actor_id, action.upper(), f"knowledge:{article_id}"); db.commit()
    return {"article_id": article_id, target_field: target_id, "linked": True}


def _unlink(db: Session, article_id: int, target_id: int, link_model: Any, target_field: str, action: str, actor_id: int) -> dict[str, Any]:
    _article_or_404(db, article_id)
    link = db.query(link_model).filter_by(article_id=article_id, **{target_field: target_id}).first()
    if link is None: raise HTTPException(404, "Relationship not found")
    db.delete(link); _history(db, article_id, actor_id, action, {target_field: target_id}); _audit(db, actor_id, action.upper(), f"knowledge:{article_id}"); db.commit()
    return {"article_id": article_id, target_field: target_id, "linked": False}


@router.post("/{article_id}/incidents/{incident_id}", status_code=201)
def link_incident(article_id: int, incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _link(db, article_id, incident_id, Incident, KnowledgeIncidentLink, "incident_id", "incident_linked", current_user.id)


@router.delete("/{article_id}/incidents/{incident_id}")
def unlink_incident(article_id: int, incident_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, incident_id, KnowledgeIncidentLink, "incident_id", "incident_unlinked", current_user.id)


@router.post("/{article_id}/problems/{problem_id}", status_code=201)
def link_problem(article_id: int, problem_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _link(db, article_id, problem_id, Problem, KnowledgeProblemLink, "problem_id", "problem_linked", current_user.id)


@router.delete("/{article_id}/problems/{problem_id}")
def unlink_problem(article_id: int, problem_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, problem_id, KnowledgeProblemLink, "problem_id", "problem_unlinked", current_user.id)


@router.post("/{article_id}/changes/{change_id}", status_code=201)
def link_change(article_id: int, change_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _link(db, article_id, change_id, ChangeRequest, KnowledgeChangeLink, "change_id", "change_linked", current_user.id)


@router.delete("/{article_id}/changes/{change_id}")
def unlink_change(article_id: int, change_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, change_id, KnowledgeChangeLink, "change_id", "change_unlinked", current_user.id)


@router.post("/{article_id}/cis/{ci_id}", status_code=201)
def link_ci(article_id: int, ci_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _link(db, article_id, ci_id, ConfigurationItem, KnowledgeCILink, "ci_id", "ci_linked", current_user.id)


@router.delete("/{article_id}/cis/{ci_id}")
def unlink_ci(article_id: int, ci_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, ci_id, KnowledgeCILink, "ci_id", "ci_unlinked", current_user.id)


@router.post("/{article_id}/devices/{device_id}", status_code=201)
def link_device(article_id: int, device_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _link(db, article_id, device_id, Device, KnowledgeDeviceLink, "device_id", "device_linked", current_user.id)


@router.delete("/{article_id}/devices/{device_id}")
def unlink_device(article_id: int, device_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, device_id, KnowledgeDeviceLink, "device_id", "device_unlinked", current_user.id)


@router.post("/{article_id}/services/{service_id}", status_code=201)
def link_service(article_id: int, service_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _link(db, article_id, service_id, APMService, KnowledgeServiceLink, "service_id", "service_linked", current_user.id)


@router.delete("/{article_id}/services/{service_id}")
def unlink_service(article_id: int, service_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, service_id, KnowledgeServiceLink, "service_id", "service_unlinked", current_user.id)


@router.post("/{article_id}/related/{related_article_id}", status_code=201)
def link_related(article_id: int, related_article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    if article_id == related_article_id: raise HTTPException(409, "An article cannot be related to itself")
    return _link(db, article_id, related_article_id, KnowledgeArticle, KnowledgeRelatedLink, "related_article_id", "related_article_linked", current_user.id)


@router.delete("/{article_id}/related/{related_article_id}")
def unlink_related(article_id: int, related_article_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    return _unlink(db, article_id, related_article_id, KnowledgeRelatedLink, "related_article_id", "related_article_unlinked", current_user.id)


@router.post("/{article_id}/feedback")
def submit_feedback(article_id: int, payload: FeedbackPayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:read"))):
    item = _article_or_404(db, article_id); now = datetime.utcnow()
    feedback = db.query(KnowledgeFeedback).filter_by(article_id=article_id, user_id=current_user.id).first()
    if feedback is None:
        feedback = KnowledgeFeedback(article_id=article_id, user_id=current_user.id, helpful=payload.helpful, created_at=now, updated_at=now); db.add(feedback)
        if payload.helpful: item.helpful_count = (item.helpful_count or 0) + 1
        else: item.not_helpful_count = (item.not_helpful_count or 0) + 1
        _history(db, article_id, current_user.id, "feedback_submitted", {"helpful": payload.helpful})
    elif feedback.helpful != payload.helpful:
        if feedback.helpful: item.helpful_count = max(0, (item.helpful_count or 0) - 1)
        else: item.not_helpful_count = max(0, (item.not_helpful_count or 0) - 1)
        if payload.helpful: item.helpful_count = (item.helpful_count or 0) + 1
        else: item.not_helpful_count = (item.not_helpful_count or 0) + 1
        feedback.helpful, feedback.updated_at = payload.helpful, now
        _history(db, article_id, current_user.id, "feedback_updated", {"helpful": payload.helpful})
    db.commit(); return _serialize(db, item)
