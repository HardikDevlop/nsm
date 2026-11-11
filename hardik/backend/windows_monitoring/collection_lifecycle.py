"""Transactional lifecycle state machine for Windows process collections."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.models import Device
from .models import WindowsProcessCollection


class CollectionState(str, Enum):
    RESERVED = "RESERVED"
    COLLECTING = "COLLECTING"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class CollectionLifecycleError(ValueError):
    pass


ACTIVE_STATES = {CollectionState.RESERVED, CollectionState.COLLECTING}
TERMINAL_STATES = {CollectionState.FINALIZED, CollectionState.FAILED, CollectionState.SUPERSEDED, CollectionState.EXPIRED}


def _now(value=None):
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def reserve_collection(db: Session, device_id: int, *, site_id: int | None = None, ttl_seconds: int = 60, collection_id: UUID | None = None, now=None):
    if ttl_seconds <= 0 or ttl_seconds > 300:
        raise CollectionLifecycleError("invalid collection expiry")
    device = db.get(Device, device_id)
    if device is None or (site_id is not None and device.site_id != site_id):
        raise CollectionLifecycleError("invalid device/site binding")
    current = _now(now)
    row = WindowsProcessCollection(collection_id=collection_id or uuid4(), device_id=device_id, site_id=device.site_id, state=CollectionState.RESERVED.value, created_at=current, expires_at=current + timedelta(seconds=ttl_seconds), updated_at=current)
    db.add(row)
    db.flush()
    return row


def _transition(db, collection_id, expected, target, *, now=None, set_started=False, set_finalized=False):
    current = _now(now)
    values = {"state": target.value, "updated_at": current}
    if set_started: values["started_at"] = current
    if set_finalized: values["finalized_at"] = current
    result = db.execute(update(WindowsProcessCollection).where(WindowsProcessCollection.collection_id == collection_id, WindowsProcessCollection.state.in_([item.value for item in expected]), WindowsProcessCollection.expires_at > current if target not in {CollectionState.EXPIRED} else True).values(**values).returning(WindowsProcessCollection))
    row = result.first()
    if row is None:
        raise CollectionLifecycleError("invalid or stale collection transition")
    return row[0] if isinstance(row, tuple) else row


def mark_collecting(db, collection_id, *, now=None): return _transition(db, collection_id, {CollectionState.RESERVED}, CollectionState.COLLECTING, now=now, set_started=True)
def finalize_collection(db, collection_id, *, now=None): return _transition(db, collection_id, {CollectionState.COLLECTING}, CollectionState.FINALIZED, now=now, set_finalized=True)
def fail_collection(db, collection_id, *, now=None): return _transition(db, collection_id, ACTIVE_STATES, CollectionState.FAILED, now=now)
def supersede_collection(db, collection_id, *, now=None): return _transition(db, collection_id, ACTIVE_STATES, CollectionState.SUPERSEDED, now=now)
def expire_collection(db, collection_id, *, now=None): return _transition(db, collection_id, ACTIVE_STATES, CollectionState.EXPIRED, now=now)


def get_active_collection(db: Session, device_id: int, *, collection_id: UUID | None = None, now=None):
    current = _now(now)
    query = db.query(WindowsProcessCollection).filter(WindowsProcessCollection.device_id == device_id, WindowsProcessCollection.state.in_([item.value for item in ACTIVE_STATES]), WindowsProcessCollection.expires_at > current)
    if collection_id is not None:
        query = query.filter(WindowsProcessCollection.collection_id == collection_id)
    return query.order_by(WindowsProcessCollection.created_at.desc()).first()
