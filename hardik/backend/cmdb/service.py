"""CMDB reconciliation against persisted NMS records.

This module deliberately reads database state only. It never starts an SNMP,
ICMP, topology, or discovery operation.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime
from threading import Lock
from typing import Any, Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models import (
    APMApplication,
    APMService,
    CIType,
    CIRelationship,
    CIHistory,
    ConfigurationItem,
    Device,
    DeviceIdentity,
    Interface,
)
from backend.models.identity import DeviceCapabilities
from backend.models.snmp import DeviceInterface, DeviceInventory, LLDPNeighbor, LatestInterface


RECONCILIATION_OWNER = "nms_reconciliation"
AUTO_RELATION_TYPES = {"contains", "runs_on", "connected_to", "topology_link"}
_LOCAL_RECONCILIATION_LOCK = Lock()
logger = logging.getLogger(__name__)


def active_relationships(db: Session) -> list[CIRelationship]:
    return db.query(CIRelationship).filter(CIRelationship.deleted_at.is_(None)).all()


def would_create_cycle(db: Session, source_ci_id: int, target_ci_id: int) -> bool:
    if source_ci_id == target_ci_id:
        return True
    graph: dict[int, set[int]] = defaultdict(set)
    for relation in active_relationships(db):
        graph[relation.source_ci_id].add(relation.target_ci_id)
    pending = deque([target_ci_id])
    visited: set[int] = set()
    while pending:
        current = pending.popleft()
        if current == source_ci_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(graph[current] - visited)
    return False


def create_relationship(db: Session, source_ci_id: int, target_ci_id: int, relationship_type: str,
                        user_id: int | None = None) -> CIRelationship:
    if not relationship_type.strip():
        raise ValueError("relationship_type is required")
    if db.query(ConfigurationItem.id).filter(ConfigurationItem.id == source_ci_id, ConfigurationItem.deleted_at.is_(None)).first() is None:
        raise LookupError("source configuration item not found")
    if db.query(ConfigurationItem.id).filter(ConfigurationItem.id == target_ci_id, ConfigurationItem.deleted_at.is_(None)).first() is None:
        raise LookupError("target configuration item not found")
    duplicate = db.query(CIRelationship).filter(
        CIRelationship.source_ci_id == source_ci_id,
        CIRelationship.target_ci_id == target_ci_id,
        CIRelationship.relationship_type == relationship_type,
        CIRelationship.deleted_at.is_(None),
    ).first()
    if duplicate is not None:
        raise ValueError("active CMDB relationship already exists")
    if would_create_cycle(db, source_ci_id, target_ci_id):
        raise ValueError("relationship would create a circular dependency")
    relation = CIRelationship(source_ci_id=source_ci_id, target_ci_id=target_ci_id,
                              relationship_type=relationship_type.strip(), created_at=datetime.utcnow())
    db.add(relation)
    return relation


def _type(db: Session, category: str) -> CIType:
    item = db.query(CIType).filter(CIType.name == category, CIType.deleted_at.is_(None)).first()
    if item:
        return item
    now = datetime.utcnow()
    item = CIType(name=category, category=category, created_at=now, updated_at=now)
    db.add(item)
    db.flush()
    return item


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _first(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _device_sources(db: Session, device: Device) -> dict[str, Any]:
    identity = db.query(DeviceIdentity).filter(DeviceIdentity.device_id == device.id).first()
    inventory = db.query(DeviceInventory).filter(DeviceInventory.device_id == device.id).order_by(DeviceInventory.updated_at.desc()).first()
    site = device.site
    vendor_name = device.vendor.vendor_name if device.vendor else None
    device_type = device.device_type.name if device.device_type else None
    discovered_at = min(
        [value for value in (device.created_at, getattr(identity, "discovered_at", None), getattr(inventory, "created_at", None)) if value is not None],
        default=device.created_at,
    )
    source = {
        "device_id": device.id,
        "hostname": _first(getattr(identity, "hostname", None), getattr(identity, "sys_name", None), device.hostname),
        "ip_address": device.ip_address,
        "mac_address": _first(device.mac_address, *(getattr(identity, "mac_addresses", None) or [])),
        "device_type": _first(getattr(identity, "device_type", None), device_type),
        "vendor": _first(getattr(identity, "vendor", None), vendor_name),
        "model": _first(getattr(identity, "model", None), getattr(inventory, "model", None), device.model),
        "serial_number": _first(getattr(identity, "serial_number", None), getattr(inventory, "serial_number", None), device.serial_number),
        "firmware_version": _first(getattr(identity, "firmware_version", None), getattr(inventory, "firmware", None), device.firmware_version),
        "os_version": getattr(identity, "os_version", None),
        "sys_object_id": getattr(identity, "sys_object_id", None),
        "sys_descr": _first(getattr(identity, "sys_descr", None), getattr(inventory, "description", None)),
        "operational_status": device.status,
        "monitoring_status": device.monitoring_status,
        "site_id": device.site_id,
        "organization_id": site.organization_id if site else None,
        "first_discovered": discovered_at,
        "last_seen": device.last_seen,
        "identity_discovered_at": getattr(identity, "discovered_at", None),
        "inventory_updated_at": getattr(inventory, "updated_at", None),
    }
    return source


def _record_history(db: Session, ci: ConfigurationItem, field: str, old: Any, new: Any, now: datetime) -> None:
    db.add(CIHistory(
        ci_id=ci.id,
        changed_by_user_id=None,
        action="source_updated",
        field_name=field,
        old_value=json.dumps(_json_value(old), sort_keys=True),
        new_value=json.dumps(_json_value(new), sort_keys=True),
        changed_at=now,
    ))


def _lock_key(db: Session, key: str) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


def _source_owned(item: ConfigurationItem) -> bool:
    return item.sync_source == RECONCILIATION_OWNER or (item.attributes or {}).get("source") == "inventory_sync"


def _upsert_ci(db: Session, ci_type: CIType, key: str, name: str, source: dict[str, Any],
               links: dict[str, Any], now: datetime, counts: dict[str, int]) -> ConfigurationItem:
    _lock_key(db, key)
    item = db.query(ConfigurationItem).filter(ConfigurationItem.external_key == key).order_by(ConfigurationItem.id.asc()).first()
    if item is None:
        item = ConfigurationItem(
            ci_type_id=ci_type.id, name=name, external_key=key, lifecycle_state="active",
            attributes={"source": "inventory_sync", "nms": _json_value(source)}, created_at=now, updated_at=now,
            first_discovered=source.get("first_discovered"), last_seen=source.get("last_seen"),
            last_synchronized=now, sync_source=RECONCILIATION_OWNER, **links,
        )
        db.add(item)
        db.flush()
        counts["created"] += 1
        return item

    serialized_source = _json_value(source)
    old_source = (item.attributes or {}).get("nms", {})
    source_owned = _source_owned(item)
    changed = old_source != serialized_source
    if item.deleted_at is not None and source_owned:
        item.deleted_at = None
        changed = True
    if source_owned:
        for field, value in {"name": name, "ci_type_id": ci_type.id, **links}.items():
            if getattr(item, field) != value:
                _record_history(db, item, field, getattr(item, field), value, now)
                setattr(item, field, value)
                changed = True
        item.lifecycle_state = "active"
    merged_attributes = dict(item.attributes or {})
    merged_attributes["source"] = "inventory_sync"
    merged_attributes["nms"] = serialized_source
    item.attributes = merged_attributes
    item.first_discovered = item.first_discovered or source.get("first_discovered")
    item.last_seen = source.get("last_seen")
    item.last_synchronized = now
    item.sync_source = RECONCILIATION_OWNER
    if changed:
        for field, old_value in old_source.items():
            if old_value != serialized_source.get(field):
                _record_history(db, item, f"source.{field}", old_value, serialized_source.get(field), now)
        for field, value in serialized_source.items():
            if old_source.get(field) != value and field not in old_source:
                _record_history(db, item, f"source.{field}", None, value, now)
        item.updated_at = now
        counts["updated"] += 1
    else:
        counts["unchanged"] += 1
    return item


def _upsert_relationship(db: Session, source: ConfigurationItem, target: ConfigurationItem,
                         relationship_type: str, source_key: str, now: datetime,
                         counts: dict[str, int]) -> None:
    if source.id == target.id:
        counts["skipped"] += 1
        return
    _lock_key(db, f"relationship:{source_key}")
    relation = db.query(CIRelationship).filter(
        CIRelationship.source_ci_id == source.id, CIRelationship.target_ci_id == target.id,
        CIRelationship.relationship_type == relationship_type,
    ).order_by(CIRelationship.id.asc()).first()
    if relation is not None:
        if relation.deleted_at is not None and relation.managed_by == RECONCILIATION_OWNER:
            relation.deleted_at = None
            counts["relationships_updated"] += 1
        elif relation.deleted_at is None:
            if relation.managed_by == RECONCILIATION_OWNER:
                if relation.source_key != source_key:
                    relation.source_key = source_key
                    counts["relationships_updated"] += 1
                else:
                    counts["relationships_unchanged"] += 1
        return
    try:
        relation = create_relationship(db, source.id, target.id, relationship_type)
    except ValueError:
        counts["skipped"] += 1
        return
    relation.managed_by = RECONCILIATION_OWNER
    relation.source_key = source_key
    relation.created_at = now
    db.flush()
    counts["relationships_created"] += 1


def _persisted_interfaces(db: Session, device_id: int) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    normalized = db.query(DeviceInterface).filter(DeviceInterface.device_id == device_id).order_by(DeviceInterface.id.asc()).all()
    latest = {row.interface_id: row for row in db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()}
    if normalized:
        rows = []
        for row in normalized:
            latest_row = next((value for value in latest.values() if value.if_index == row.if_index), None)
            source = {
                "interface_id": row.id, "device_id": row.device_id,
                "name": _first(row.name, latest_row.name if latest_row else None, f"if{row.if_index}"),
                "if_index": row.if_index, "admin_status": getattr(latest_row, "admin_status", None),
                "operational_status": _first(getattr(latest_row, "oper_status", None), row.status),
                "speed_bps": _first(getattr(latest_row, "speed_bps", None), row.speed_bps),
                "last_seen": getattr(latest_row, "polled_at", None),
            }
            rows.append((f"interface:{row.id}", source, {}))
        return rows
    return [
        (f"interface:{row.id}", {
            "interface_id": row.id, "device_id": row.device_id, "name": row.interface_name,
            "operational_status": row.status, "speed": row.speed, "last_seen": row.last_updated,
        }, {"interface_id": row.id})
        for row in db.query(Interface).filter(Interface.device_id == device_id).order_by(Interface.id.asc()).all()
    ]


def _known_device_map(db: Session, devices: list[Device]) -> dict[str, Device]:
    result: dict[str, Device] = {}
    identities = {row.device_id: row for row in db.query(DeviceIdentity).filter(DeviceIdentity.device_id.in_([row.id for row in devices])).all()}
    for device in devices:
        values = [device.ip_address, device.hostname, str(device.id), device.mac_address]
        identity = identities.get(device.id)
        values.extend([getattr(identity, "hostname", None), getattr(identity, "sys_name", None)])
        values.extend(getattr(identity, "mac_addresses", None) or [])
        for value in values:
            if value not in (None, ""):
                result[str(value).strip().lower()] = device
    return result


def _topology_links(db: Session, devices: list[Device]) -> list[tuple[Device, Device]]:
    known = _known_device_map(db, devices)
    result: list[tuple[Device, Device]] = []
    caps = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id.in_([row.id for row in devices])).all()
    for cap in caps:
        payload = (cap.capability_detail or {}).get("topology") or {}
        for link in ((payload.get("data") or {}).get("links") or []):
            if not isinstance(link, dict):
                continue
            source_value = _first(link.get("source_device_id"), link.get("source_ip"), link.get("source"), link.get("from"))
            target_value = _first(link.get("target_device_id"), link.get("target_ip"), link.get("target"), link.get("to"))
            source = known.get(str(source_value).strip().lower()) if source_value is not None else None
            target = known.get(str(target_value).strip().lower()) if target_value is not None else None
            if source and target:
                result.append((source, target))
    for device in devices:
        for link in ((device.topology_metadata or {}).get("links") or []):
            if not isinstance(link, dict):
                continue
            source_value = _first(link.get("source_device_id"), link.get("source_ip"), link.get("source"), link.get("from"))
            target_value = _first(link.get("target_device_id"), link.get("target_ip"), link.get("target"), link.get("to"))
            source = known.get(str(source_value).strip().lower()) if source_value is not None else None
            target = known.get(str(target_value).strip().lower()) if target_value is not None else None
            if source and target:
                result.append((source, target))
    return result


def _lldp_links(db: Session, devices: list[Device]) -> list[tuple[Device, Device]]:
    known = _known_device_map(db, devices)
    by_id = {row.id: row for row in devices}
    result = []
    for row in db.query(LLDPNeighbor).filter(LLDPNeighbor.device_id.in_(by_id)).all():
        source = by_id.get(row.device_id)
        target = known.get(str(row.remote_device or "").strip().lower())
        if source and target and source.id != target.id:
            result.append((source, target))
    return result


def _retire_stale_relationships(db: Session, current_keys: set[str], now: datetime, counts: dict[str, int]) -> None:
    rows = db.query(CIRelationship).filter(
        CIRelationship.managed_by == RECONCILIATION_OWNER,
        CIRelationship.relationship_type.in_(AUTO_RELATION_TYPES),
        CIRelationship.deleted_at.is_(None),
    ).all()
    for relation in rows:
        if relation.source_key and relation.source_key not in current_keys:
            relation.deleted_at = now
            counts["relationships_removed"] += 1


@contextmanager
def _reconciliation_lock(db: Session) -> Iterator[None]:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(821150303)"))
        yield
    else:
        with _LOCAL_RECONCILIATION_LOCK:
            yield


def reconcile_cmdb(db: Session) -> dict[str, Any]:
    """Reconcile all persisted NMS sources without performing network I/O."""
    started = datetime.utcnow()
    counts = {
        "created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "errors": 0,
        "relationships_created": 0, "relationships_updated": 0,
        "relationships_removed": 0, "relationships_unchanged": 0,
    }
    current_relationship_keys: set[str] = set()
    with _reconciliation_lock(db):
        devices = db.query(Device).filter(Device.deleted_at.is_(None)).order_by(Device.id.asc()).all()
        device_type = _type(db, "device")
        interface_type = _type(db, "interface")
        application_type = _type(db, "application")
        device_cis: dict[int, ConfigurationItem] = {}
        for device in devices:
            source = _device_sources(db, device)
            device_cis[device.id] = _upsert_ci(db, device_type, f"device:{device.id}", device.hostname, source, {
                "device_id": device.id, "site_id": device.site_id,
                "organization_id": source.get("organization_id"),
            }, started, counts)
        for device in devices:
            for key, source, links in _persisted_interfaces(db, device.id):
                ci = _upsert_ci(db, interface_type, key, source.get("name") or key, source, {
                    "device_id": device.id, **links,
                }, started, counts)
                parent = device_cis.get(device.id)
                if parent:
                    relation_key = f"contains:{parent.id}:{ci.id}"
                    _upsert_relationship(db, parent, ci, "contains", relation_key, started, counts)
                    current_relationship_keys.add(relation_key)
        for application in db.query(APMApplication).filter(APMApplication.deleted_at.is_(None), APMApplication.enabled.is_(True)).all():
            source = _json_value({"application_id": application.id, "name": application.name, "environment": application.environment})
            application_ci = _upsert_ci(db, application_type, f"application:{application.id}", application.name, source, {
                "application_id": application.id, "environment": application.environment,
            }, started, counts)
            for service in db.query(APMService).filter(APMService.application_id == application.id, APMService.deleted_at.is_(None), APMService.device_id.isnot(None)).all():
                target = device_cis.get(service.device_id)
                if target:
                    relation_key = f"runs_on:{application_ci.id}:{target.id}"
                    _upsert_relationship(db, application_ci, target, "runs_on", relation_key, started, counts)
                    current_relationship_keys.add(relation_key)
        for source_device, target_device in _lldp_links(db, devices) + _topology_links(db, devices):
            source = device_cis.get(source_device.id)
            target = device_cis.get(target_device.id)
            if source and target:
                relation_key = f"topology_link:{source.id}:{target.id}"
                _upsert_relationship(db, source, target, "topology_link", relation_key, started, counts)
                current_relationship_keys.add(relation_key)
        _retire_stale_relationships(db, current_relationship_keys, started, counts)

        active_keys = {f"device:{device.id}" for device in devices}
        retired = db.query(ConfigurationItem).filter(
            ConfigurationItem.sync_source == RECONCILIATION_OWNER,
            ConfigurationItem.external_key.like("device:%"),
            ConfigurationItem.deleted_at.is_(None),
        ).all()
        for item in retired:
            if item.external_key not in active_keys:
                if item.lifecycle_state != "retired":
                    _record_history(db, item, "lifecycle_state", item.lifecycle_state, "retired", started)
                    item.lifecycle_state = "retired"
                    item.updated_at = started
                    counts["updated"] += 1
                item.last_synchronized = started
        db.commit()
    completed = datetime.utcnow()
    result = {**counts, "started_at": started.isoformat(), "completed_at": completed.isoformat()}
    logger.info("cmdb_reconciliation_complete %s", counts)
    return result


def sync_inventory_relationships(db: Session) -> dict[str, int]:
    """Compatibility wrapper for the existing manual inventory endpoint."""
    result = reconcile_cmdb(db)
    return {
        "configuration_items": result["created"] + result["updated"] + result["unchanged"],
        "relationships_created": result["relationships_created"],
    }


def sync_topology_relationships(db: Session, links: list[dict[str, Any]]) -> dict[str, int]:
    """Compatibility wrapper for caller-supplied topology links."""
    sync_inventory_relationships(db)
    devices = db.query(Device).filter(Device.deleted_at.is_(None)).all()
    by_ip = {device.ip_address: device for device in devices}
    ci_by_key = {item.external_key: item for item in db.query(ConfigurationItem).filter(ConfigurationItem.deleted_at.is_(None), ConfigurationItem.external_key.isnot(None)).all()}
    created = skipped = 0
    for link in links:
        source_device = by_ip.get(str(link.get("source") or link.get("source_ip") or ""))
        target_device = by_ip.get(str(link.get("target") or link.get("target_ip") or ""))
        source = ci_by_key.get(f"device:{source_device.id}") if source_device else None
        target = ci_by_key.get(f"device:{target_device.id}") if target_device else None
        if source is None or target is None:
            skipped += 1
            continue
        try:
            relation = create_relationship(db, source.id, target.id, "topology_link")
            relation.managed_by = "manual"
            relation.source_key = None
            db.commit()
            created += 1
        except ValueError:
            db.rollback()
            skipped += 1
    return {"relationships_created": created, "links_skipped": skipped}
