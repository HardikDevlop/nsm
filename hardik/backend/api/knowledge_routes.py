from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import APMService, AuditLog, Device, Incident, KnowledgeArticle, KnowledgeArticleVersion, KnowledgeDeviceLink, KnowledgeIncidentLink, KnowledgeProblemLink, KnowledgeServiceLink, Problem, User

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])


class ArticleCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    article_type: str = Field(default="knowledge", pattern="^(knowledge|known_error|runbook)$")
    body: str = Field(min_length=1, max_length=100000)
    incident_ids: list[int] = Field(default_factory=list, max_length=500)
    problem_ids: list[int] = Field(default_factory=list, max_length=500)
    device_ids: list[int] = Field(default_factory=list, max_length=500)
    service_ids: list[int] = Field(default_factory=list, max_length=500)


class ArticleUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=220)
    status: str | None = Field(default=None, pattern="^(draft|published|retired)$")
    body: str | None = Field(default=None, min_length=1, max_length=100000)


def _audit(db: Session, user_id: int, action: str, resource: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource))


def _serialize(db: Session, item: KnowledgeArticle, include_body: bool = True) -> dict[str, Any]:
    version = db.query(KnowledgeArticleVersion).filter_by(article_id=item.id, version=item.current_version).first()
    return {"id": item.id, "number": item.number, "title": item.title, "article_type": item.article_type, "status": item.status, "current_version": item.current_version, "body": version.body if version and include_body else None, "incident_ids": [x.incident_id for x in db.query(KnowledgeIncidentLink).filter_by(article_id=item.id).all()], "problem_ids": [x.problem_id for x in db.query(KnowledgeProblemLink).filter_by(article_id=item.id).all()], "device_ids": [x.device_id for x in db.query(KnowledgeDeviceLink).filter_by(article_id=item.id).all()], "service_ids": [x.service_id for x in db.query(KnowledgeServiceLink).filter_by(article_id=item.id).all()], "versions": [{"version": x.version, "changed_by": x.changed_by, "created_at": x.created_at} for x in db.query(KnowledgeArticleVersion).filter_by(article_id=item.id).order_by(KnowledgeArticleVersion.version.desc()).all()], "created_at": item.created_at, "updated_at": item.updated_at}


def _validate_links(db: Session, payload: ArticleCreatePayload) -> None:
    checks = ((Incident, payload.incident_ids, "incidents"), (Problem, payload.problem_ids, "problems"), (Device, payload.device_ids, "devices"), (APMService, payload.service_ids, "services"))
    for model, ids, label in checks:
        if ids and db.query(model.id).filter(model.id.in_(set(ids))).count() != len(set(ids)): raise HTTPException(404, f"One or more {label} not found")


@router.get("")
def list_articles(search: str | None = None, article_type: str | None = None, status: str = "published", skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    query = db.query(KnowledgeArticle).filter(KnowledgeArticle.status == status)
    if article_type: query = query.filter(KnowledgeArticle.article_type == article_type)
    if search:
        pattern = f"%{search}%"
        ids = db.query(KnowledgeArticleVersion.article_id).filter(KnowledgeArticleVersion.body.ilike(pattern)).subquery()
        query = query.filter(or_(KnowledgeArticle.title.ilike(pattern), KnowledgeArticle.id.in_(ids)))
    rows = query.order_by(KnowledgeArticle.updated_at.desc()).offset(skip).limit(limit).all()
    return {"items": [_serialize(db, row, include_body=False) for row in rows], "skip": skip, "limit": limit}


@router.post("", status_code=201)
def create_article(payload: ArticleCreatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:create"))):
    _validate_links(db, payload); now = datetime.utcnow()
    item = KnowledgeArticle(number="PENDING", title=payload.title, article_type=payload.article_type, status="published", current_version=1, created_by=current_user.id, updated_by=current_user.id, created_at=now, updated_at=now)
    db.add(item); db.flush(); item.number = f"KB-{item.id:06d}"
    db.add(KnowledgeArticleVersion(article_id=item.id, version=1, body=payload.body, changed_by=current_user.id, created_at=now))
    for model, link_model, ids in ((Incident, KnowledgeIncidentLink, payload.incident_ids), (Problem, KnowledgeProblemLink, payload.problem_ids), (Device, KnowledgeDeviceLink, payload.device_ids)):
        for target_id in set(ids): db.add(link_model(article_id=item.id, **({"incident_id": target_id} if link_model is KnowledgeIncidentLink else {"problem_id": target_id} if link_model is KnowledgeProblemLink else {"device_id": target_id}), linked_by=current_user.id, linked_at=now))
    for service_id in set(payload.service_ids): db.add(KnowledgeServiceLink(article_id=item.id, service_id=service_id, linked_by=current_user.id, linked_at=now))
    _audit(db, current_user.id, "CREATE", f"knowledge:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    item = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if item is None: raise HTTPException(404, "Knowledge article not found")
    return _serialize(db, item)


@router.patch("/{article_id}")
def update_article(article_id: int, payload: ArticleUpdatePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("knowledge:update"))):
    item = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()
    if item is None: raise HTTPException(404, "Knowledge article not found")
    values = payload.model_dump(exclude_unset=True); body = values.pop("body", None)
    for field, value in values.items(): setattr(item, field, value)
    if body is not None:
        item.current_version += 1; db.add(KnowledgeArticleVersion(article_id=item.id, version=item.current_version, body=body, changed_by=current_user.id, created_at=datetime.utcnow()))
    item.updated_by, item.updated_at = current_user.id, datetime.utcnow(); _audit(db, current_user.id, "UPDATE", f"knowledge:{item.id}"); db.commit(); db.refresh(item)
    return _serialize(db, item)


@router.get("/{article_id}/versions")
def article_versions(article_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("knowledge:read"))):
    if db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first() is None: raise HTTPException(404, "Knowledge article not found")
    return db.query(KnowledgeArticleVersion).filter_by(article_id=article_id).order_by(KnowledgeArticleVersion.version.desc()).all()
