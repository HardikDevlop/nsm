"""Persistence helpers for Windows CA bundle metadata and assignments.

This module stores metadata only. PEM material is intentionally out of scope
for this foundation and must not be placed in these records.
"""

from sqlalchemy.orm import Session

from .models import WindowsCABundle, WindowsDeviceCAAssignment


def create_ca_bundle(db: Session, **values) -> WindowsCABundle:
    item = WindowsCABundle(**values)
    db.add(item)
    db.flush()
    return item


def get_ca_bundle(db: Session, bundle_id: int, *, site_id: int | None = None) -> WindowsCABundle | None:
    query = db.query(WindowsCABundle).filter(WindowsCABundle.id == bundle_id)
    if site_id is not None:
        query = query.filter(WindowsCABundle.site_id == site_id)
    return query.first()


def list_site_ca_bundles(db: Session, site_id: int) -> list[WindowsCABundle]:
    return db.query(WindowsCABundle).filter(
        WindowsCABundle.site_id == site_id,
    ).order_by(WindowsCABundle.id).all()


def get_ca_bundle_by_fingerprint(db: Session, site_id: int, fingerprint: str) -> WindowsCABundle | None:
    return db.query(WindowsCABundle).filter(
        WindowsCABundle.site_id == site_id,
        WindowsCABundle.sha256_fingerprint == fingerprint,
    ).first()


def get_active_device_ca_assignment(db: Session, device_id: int) -> WindowsDeviceCAAssignment | None:
    return db.query(WindowsDeviceCAAssignment).filter(
        WindowsDeviceCAAssignment.device_id == device_id,
        WindowsDeviceCAAssignment.unassigned_at.is_(None),
    ).first()


def create_device_ca_assignment(db: Session, **values) -> WindowsDeviceCAAssignment:
    item = WindowsDeviceCAAssignment(**values)
    db.add(item)
    db.flush()
    return item


def can_delete_ca_bundle(db: Session, bundle_id: int) -> bool:
    return not db.query(WindowsDeviceCAAssignment).filter(
        WindowsDeviceCAAssignment.ca_bundle_id == bundle_id,
        WindowsDeviceCAAssignment.unassigned_at.is_(None),
    ).first()


def delete_ca_bundle(db: Session, bundle: WindowsCABundle) -> None:
    db.delete(bundle)
    db.flush()
