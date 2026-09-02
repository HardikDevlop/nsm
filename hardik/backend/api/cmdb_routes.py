from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import CIHistory, CIType, CIRelationship, ConfigurationItem
from backend.cmdb.service import create_relationship, reconcile_cmdb, sync_inventory_relationships, sync_topology_relationships

router = APIRouter(prefix="/api/v1/cmdb", tags=["CMDB"])


def _now() -> datetime:
    return datetime.utcnow()


class CITypePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="custom", pattern="^(device|interface|server|application|database|business_service|custom)$")
    description: str | None = Field(default=None, max_length=2000)


class CIPayload(BaseModel):
    ci_type_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=180)
    external_key: str | None = Field(default=None, max_length=180)
    lifecycle_state: str = Field(default="planned", pattern="^(planned|build|active|maintenance|retired|disposed)$")
    owner_user_id: int | None = Field(default=None, gt=0)
    organization_id: int | None = Field(default=None, gt=0)
    device_id: int | None = Field(default=None, gt=0)
    interface_id: int | None = Field(default=None, gt=0)
    site_id: int | None = Field(default=None, gt=0)
    application_id: int | None = Field(default=None, gt=0)
    environment: str | None = Field(default=None, max_length=80)
    attributes: dict[str, Any] = Field(default_factory=dict)


class CIRelationshipPayload(BaseModel):
    target_ci_id: int = Field(gt=0)
    relationship_type: str = Field(min_length=1, max_length=80)


class TopologyLinksPayload(BaseModel):
    links: list[dict[str, Any]] = Field(min_length=1, max_length=10000)


def _history(db: Session, ci_id: int, user_id: int | None, action: str, field: str | None = None,
             old: Any = None, new: Any = None) -> None:
    db.add(CIHistory(ci_id=ci_id, changed_by_user_id=user_id, action=action, field_name=field,
                     old_value=None if old is None else json.dumps(old, default=str),
                     new_value=None if new is None else json.dumps(new, default=str), changed_at=_now()))


@router.get("/types")
def list_ci_types(db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:read"))):
    return db.query(CIType).filter(CIType.deleted_at.is_(None)).order_by(CIType.name.asc()).all()


@router.post("/types")
def create_ci_type(payload: CITypePayload, db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:manage"))):
    now = _now()
    item = CIType(**payload.model_dump(), created_at=now, updated_at=now)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/items")
def list_configuration_items(search: str | None = None, ci_type_id: int | None = None,
                             lifecycle_state: str | None = None, owner_user_id: int | None = None,
                             device_id: int | None = None, site_id: int | None = None,
                             application_id: int | None = None, skip: int = Query(0, ge=0),
                             limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                             _: Any = Depends(require_permission("cmdb:read"))):
    query = db.query(ConfigurationItem).filter(ConfigurationItem.deleted_at.is_(None))
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(ConfigurationItem.name.ilike(pattern), ConfigurationItem.external_key.ilike(pattern)))
    for column, value in ((ConfigurationItem.ci_type_id, ci_type_id), (ConfigurationItem.lifecycle_state, lifecycle_state),
                          (ConfigurationItem.owner_user_id, owner_user_id), (ConfigurationItem.device_id, device_id),
                          (ConfigurationItem.site_id, site_id), (ConfigurationItem.application_id, application_id)):
        if value is not None:
            query = query.filter(column == value)
    return query.order_by(ConfigurationItem.name.asc()).offset(skip).limit(limit).all()


@router.post("/items")
def create_configuration_item(payload: CIPayload, db: Session = Depends(get_db), current_user: Any = Depends(require_permission("cmdb:manage"))):
    now = _now()
    item = ConfigurationItem(**payload.model_dump(), created_at=now, updated_at=now)
    db.add(item)
    db.flush()
    _history(db, item.id, getattr(current_user, "id", None), "created", new=payload.model_dump())
    db.commit()
    db.refresh(item)
    return item


@router.patch("/items/{ci_id}")
def update_configuration_item(ci_id: int, payload: CIPayload, db: Session = Depends(get_db), current_user: Any = Depends(require_permission("cmdb:manage"))):
    item = db.query(ConfigurationItem).filter(ConfigurationItem.id == ci_id, ConfigurationItem.deleted_at.is_(None)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Configuration item not found")
    old = {field: getattr(item, field) for field in payload.model_fields}
    values = payload.model_dump()
    for field, value in values.items():
        setattr(item, field, value)
        if old[field] != value:
            _history(db, item.id, getattr(current_user, "id", None), "updated", field, old[field], value)
    item.updated_at = _now()
    db.commit()
    db.refresh(item)
    return item


@router.get("/items/{ci_id}/history")
def configuration_item_history(ci_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:read"))):
    return db.query(CIHistory).filter(CIHistory.ci_id == ci_id).order_by(CIHistory.changed_at.desc(), CIHistory.id.desc()).all()


@router.get("/items/{ci_id}/relationships")
def list_ci_relationships(ci_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:read"))):
    return db.query(CIRelationship).filter(
        CIRelationship.deleted_at.is_(None),
        or_(CIRelationship.source_ci_id == ci_id, CIRelationship.target_ci_id == ci_id),
    ).order_by(CIRelationship.created_at.desc()).all()


@router.post("/items/{ci_id}/relationships")
def create_ci_relationship(ci_id: int, payload: CIRelationshipPayload, db: Session = Depends(get_db), current_user: Any = Depends(require_permission("cmdb:manage"))):
    try:
        relationship = create_relationship(db, ci_id, payload.target_ci_id, payload.relationship_type, getattr(current_user, "id", None))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already exists" in str(exc) else 422, detail=str(exc)) from exc
    db.commit()
    db.refresh(relationship)
    return relationship


@router.post("/relationships/sync")
def sync_cmdb_inventory(db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:manage"))):
    return sync_inventory_relationships(db)


@router.post("/sync")
def reconcile_cmdb_data(db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:manage"))):
    """Reconcile persisted NMS data without starting any network collectors."""
    return reconcile_cmdb(db)


@router.post("/relationships/sync/topology")
def sync_cmdb_topology(payload: TopologyLinksPayload, db: Session = Depends(get_db), _: Any = Depends(require_permission("cmdb:manage"))):
    return sync_topology_relationships(db, payload.links)
