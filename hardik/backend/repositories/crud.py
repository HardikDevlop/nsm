from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class CRUDRouterMixin:
    """Generic CRUD helper shared by every module router."""

    def __init__(self, model: type) -> None:
        self.model = model
        self.has_soft_delete = hasattr(model, "deleted_at")

    def _payload_to_dict(self, payload: BaseModel | dict[str, Any], partial: bool = False) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            return payload.model_dump(exclude_unset=partial)
        return dict(payload)

    def list(self, db: Session, skip: int = 0, limit: int = 100) -> list[Any]:
        query = db.query(self.model)
        if self.has_soft_delete:
            query = query.filter(self.model.deleted_at.is_(None))
        return query.order_by(self.model.id).offset(skip).limit(min(limit, 500)).all()

    def get(self, db: Session, item_id: int) -> Any:
        item = db.get(self.model, item_id)
        if item is None or (self.has_soft_delete and item.deleted_at is not None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} {item_id} not found",
            )
        return item

    def create(self, db: Session, payload: BaseModel | dict[str, Any]) -> Any:
        item = self.model(**self._payload_to_dict(payload))
        db.add(item)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{self.model.__name__} violates a unique or foreign key constraint: {exc.orig}",
            )
        db.refresh(item)
        return item

    def update(self, db: Session, item_id: int, payload: BaseModel | dict[str, Any]) -> Any:
        item = self.get(db, item_id)
        for field, value in self._payload_to_dict(payload, partial=True).items():
            setattr(item, field, value)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{self.model.__name__} violates a unique or foreign key constraint: {exc.orig}",
            )
        db.refresh(item)
        return item

    def delete(self, db: Session, item_id: int) -> dict[str, Any]:
        item = self.get(db, item_id)
        if self.has_soft_delete:
            item.deleted_at = datetime.utcnow()
        else:
            db.delete(item)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{self.model.__name__} is referenced by other records: {exc.orig}",
            )
        return {"detail": f"{self.model.__name__} {item_id} deleted"}
