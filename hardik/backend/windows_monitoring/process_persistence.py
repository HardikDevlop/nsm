"""Transactional PostgreSQL persistence for Windows process snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import logging

from sqlalchemy.orm import Session

from backend.database.session import SessionLocal
from .models import WindowsProcessSnapshot, WindowsProcessSnapshotItem

logger = logging.getLogger(__name__)


def _collected_at(value: str | None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def persist_process_snapshot(db: Session, device_id: int, snapshot, *, collection_id: UUID | None = None) -> WindowsProcessSnapshot:
    """Insert one complete snapshot and all items in the caller transaction."""
    parent = WindowsProcessSnapshot(
        device_id=device_id,
        collected_at=_collected_at(snapshot.collected_at),
        collection_id=getattr(snapshot, "collection_id", None) or collection_id or uuid4(),
        process_count=len(snapshot.processes),
    )
    db.add(parent)
    db.flush()
    active_cpu = {item.process_id: item for item in snapshot.cpu if item.status != "terminated"}
    db.add_all([
        WindowsProcessSnapshotItem(
            snapshot_id=parent.id,
            device_id=device_id,
            process_id=row.process_id,
            process_creation_time=row.creation_time,
            process_name=row.name,
            parent_process_id=row.parent_process_id,
            cpu_percent=(cpu.cpu_percent if cpu and cpu.status == "ok" else None),
            cpu_status=(cpu.status if cpu else "unavailable"),
            cpu_reason=(cpu.reason if cpu else "missing_cpu_result"),
            working_set_bytes=row.working_set_bytes,
            private_memory_bytes=row.private_memory_bytes,
            thread_count=row.thread_count,
            started_at=row.creation_time,
            session_id=row.session_id,
            classification=row.classification,
            classification_source=row.classification_source,
            classification_confidence=row.classification_confidence,
            application_group_id=row.application_group_id,
        )
        for row in snapshot.processes if row.process_id is not None
        for cpu in [active_cpu.get(row.process_id)]
    ])
    db.flush()
    return parent


def try_persist_process_snapshot(db: Session, device_id: int, snapshot) -> bool:
    try:
        persist_process_snapshot(db, device_id, snapshot)
        return True
    except Exception:
        db.rollback()
        logger.warning("windows_process_snapshot_persistence_failed device_id=%s", device_id, exc_info=True)
        return False


def persist_process_snapshot_isolated(device_id: int, snapshot) -> bool:
    """Persist using a dedicated transaction, independent of request auditing."""
    session = SessionLocal()
    try:
        persist_process_snapshot(session, device_id, snapshot)
        session.commit()
        return True
    except Exception:
        session.rollback()
        logger.warning("windows_process_snapshot_persistence_failed device_id=%s", device_id, exc_info=True)
        return False
    finally:
        session.close()


def delete_expired_process_snapshots(db: Session, *, before: datetime, limit: int = 1000) -> int:
    """Delete at most ``limit`` expired parents; children cascade in PostgreSQL."""
    ids = [row[0] for row in db.query(WindowsProcessSnapshot.id)
           .filter(WindowsProcessSnapshot.collected_at < before)
           .order_by(WindowsProcessSnapshot.collected_at.asc(), WindowsProcessSnapshot.id.asc())
           .limit(limit).all()]
    if not ids:
        return 0
    deleted = db.query(WindowsProcessSnapshot).filter(WindowsProcessSnapshot.id.in_(ids)).delete(synchronize_session=False)
    db.flush()
    return deleted


def cleanup_process_snapshot_retention(db: Session, *, retention_days: int = 7, limit: int = 1000) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    return delete_expired_process_snapshots(
        db, before=datetime.now(timezone.utc) - timedelta(days=retention_days), limit=limit
    )


def cleanup_process_snapshot_retention_isolated(*, retention_days: int = 7, limit: int = 1000) -> int:
    session = SessionLocal()
    try:
        deleted = cleanup_process_snapshot_retention(session, retention_days=retention_days, limit=limit)
        session.commit()
        return deleted
    except Exception:
        session.rollback()
        logger.warning("windows_process_snapshot_retention_failed", exc_info=True)
        return 0
    finally:
        session.close()
