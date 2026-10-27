"""Persistence helpers for Windows monitoring snapshots.

This module intentionally has no API/router responsibilities.  Phase 3
network collection can persist into the existing per-device, per-module JSON
snapshot table without exposing a new endpoint yet.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from .cim import NetworkInterfaceResult
from .events import SystemEvent
from .models import WindowsEventLog, WindowsHardwareSnapshot, WindowsMetricSnapshot, windows_now


def _json_value(value):
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


_HARDWARE_SINGLETON_SECTIONS = ("computer_system", "system_product", "baseboard", "bios")
_HARDWARE_ARRAY_SECTIONS = ("processors", "memory_modules", "memory_arrays")


def _singleton_section(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return {}


def _array_section(value) -> list:
    return value if isinstance(value, list) else []


def serialize_hardware_information(value: dict) -> dict:
    """Convert hardware_information() output into JSON-safe snapshot data."""
    if not isinstance(value, dict):
        raise ValueError("hardware information must be a mapping")
    required = ("computer_system", "system_product", "baseboard", "bios", "processors", "memory_modules", "memory_arrays")
    if any(key not in value for key in required):
        raise ValueError("hardware information is missing a required section")
    normalized = {}
    for key in _HARDWARE_SINGLETON_SECTIONS:
        # CIM returns typed dataclasses inside singleton lists. Convert first,
        # then unwrap; otherwise the list item is not recognized as a dict and
        # valid hardware identity is replaced with {}.
        normalized[key] = _singleton_section(_json_value(value[key]))
    for key in _HARDWARE_ARRAY_SECTIONS:
        normalized[key] = _json_value(_array_section(value[key]))
    return normalized


def upsert_hardware_snapshot(db: Session, device_id: int, hardware: dict) -> WindowsHardwareSnapshot:
    """Upsert the latest complete hardware snapshot in the caller's transaction."""
    value = serialize_hardware_information(hardware)
    collected_at = windows_now()
    statement = pg_insert(WindowsHardwareSnapshot).values(device_id=device_id, collected_at=collected_at, **value).on_conflict_do_update(
        index_elements=[WindowsHardwareSnapshot.device_id],
        set_={"collected_at": collected_at, **value},
    ).returning(WindowsHardwareSnapshot.id)
    row_id = db.execute(statement).scalar_one()
    return db.query(WindowsHardwareSnapshot).filter(WindowsHardwareSnapshot.id == row_id).one()


def get_hardware_snapshot(db: Session, device_id: int) -> WindowsHardwareSnapshot | None:
    """Return the latest committed hardware snapshot for one device."""
    return db.scalars(select(WindowsHardwareSnapshot).where(WindowsHardwareSnapshot.device_id == device_id)).first()


def save_hardware_snapshot(db: Session, device_id: int, hardware: dict) -> WindowsHardwareSnapshot:
    """Persist a hardware snapshot and rollback this transaction on failure."""
    try:
        row = upsert_hardware_snapshot(db, device_id, hardware)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def serialize_network_interfaces(
    interfaces: Iterable[NetworkInterfaceResult],
) -> list[dict[str, object]]:
    """Convert typed CIM results to JSON-safe normalized snapshot data."""
    return [
        {
            "adapter_index": interface.adapter_index,
            "interface_index": interface.interface_index,
            "name": interface.name,
            "description": interface.description,
            "mac_address": interface.mac_address,
            "ipv4_addresses": list(interface.ipv4_addresses),
            "ipv6_addresses": list(interface.ipv6_addresses),
            "interface_status": interface.interface_status,
            "link_speed_bps": interface.link_speed_bps,
            "rx_bytes_per_sec": interface.rx_bytes_per_sec,
            "tx_bytes_per_sec": interface.tx_bytes_per_sec,
        }
        for interface in interfaces
    ]


def upsert_network_snapshot(
    db: Session,
    device_id: int,
    interfaces: Iterable[NetworkInterfaceResult],
) -> WindowsMetricSnapshot:
    """Upsert one complete network snapshot in the caller's transaction.

    The caller commits only after CIM collection and this operation succeed.
    Therefore a collection or persistence failure leaves the prior committed
    snapshot untouched when the caller rolls back.
    """
    value = serialize_network_interfaces(interfaces)
    collected_at = windows_now()
    statement = pg_insert(WindowsMetricSnapshot).values(
        device_id=device_id,
        module="network",
        collected_at=collected_at,
        data=value,
    ).on_conflict_do_update(
        index_elements=[WindowsMetricSnapshot.device_id, WindowsMetricSnapshot.module],
        set_={"collected_at": collected_at, "data": value},
    ).returning(WindowsMetricSnapshot.id)
    row_id = db.execute(statement).scalar_one()
    return db.query(WindowsMetricSnapshot).filter(WindowsMetricSnapshot.id == row_id).one()


def save_network_snapshot(
    db: Session,
    device_id: int,
    interfaces: Iterable[NetworkInterfaceResult],
) -> WindowsMetricSnapshot:
    """Persist a network snapshot and rollback this transaction on failure."""
    try:
        row = upsert_network_snapshot(db, device_id, interfaces)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def _event_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Windows event text field exceeds its limit")
    return value


def insert_system_events(
    db: Session,
    device_id: int,
    channel: str,
    events: Iterable[SystemEvent],
    *,
    collected_at: datetime | None = None,
    max_records: int = 500,
) -> int:
    """Atomically insert a bounded event batch; duplicates are ignored."""
    if channel != "System":
        raise ValueError("only the System channel is supported")
    rows = list(events)
    if len(rows) > max_records or max_records < 1 or max_records > 500:
        raise ValueError("event batch exceeds its limit")
    timestamp = collected_at or windows_now()
    values = [{
        "device_id": device_id,
        "channel": channel,
        "record_id": event.record_id,
        "time_created": datetime.fromisoformat(event.time_created.replace("Z", "+00:00")).replace(tzinfo=None),
        "event_id": event.event_id,
        "provider": _event_text(event.provider, 255),
        "level": _event_text(event.level, 80),
        "machine_name": _event_text(event.machine_name, 255),
        "message": _event_text(event.message, 1_000_000),
        "user_id": _event_text(event.user_id, 255),
        "collected_at": timestamp,
    } for event in rows]
    if not values:
        return 0
    statement = pg_insert(WindowsEventLog).values(values).on_conflict_do_nothing(
        index_elements=[WindowsEventLog.device_id, WindowsEventLog.channel, WindowsEventLog.record_id],
    ).returning(WindowsEventLog.record_id)
    result = db.execute(statement)
    # PostgreSQL rowcount is not reliable for INSERT ... ON CONFLICT. The
    # RETURNING stream contains exactly the rows inserted by this statement.
    return len(result.scalars().all())


def save_system_events(
    db: Session,
    device_id: int,
    channel: str,
    events: Iterable[SystemEvent],
    *,
    collected_at: datetime | None = None,
    max_records: int = 500,
) -> int:
    """Insert one event batch and commit only if the complete batch succeeds."""
    try:
        inserted = insert_system_events(db, device_id, channel, events, collected_at=collected_at, max_records=max_records)
        db.commit()
        return inserted
    except Exception:
        db.rollback()
        raise


def list_system_events(
    db: Session,
    device_id: int,
    *,
    channel: str = "System",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    event_ids: Iterable[int] = (),
    level: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[WindowsEventLog]:
    """Return bounded, explicitly filtered historical System events."""
    if channel != "System" or offset < 0 or not 1 <= limit <= 500:
        raise ValueError("invalid event retrieval bounds")
    ids = tuple(event_ids)
    if len(ids) > 100 or any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in ids):
        raise ValueError("invalid event ID filter")
    query = select(WindowsEventLog).where(WindowsEventLog.device_id == device_id, WindowsEventLog.channel == channel)
    if start_time is not None:
        query = query.where(WindowsEventLog.time_created >= start_time)
    if end_time is not None:
        query = query.where(WindowsEventLog.time_created <= end_time)
    if ids:
        query = query.where(WindowsEventLog.event_id.in_(ids))
    if level is not None:
        if len(level) > 80:
            raise ValueError("level filter is too long")
        query = query.where(WindowsEventLog.level == level)
    return list(db.scalars(query.order_by(WindowsEventLog.time_created.desc(), WindowsEventLog.id.desc()).offset(offset).limit(limit)))


def latest_system_event_time(db: Session, device_id: int) -> datetime | None:
    """Return the newest stored System event timestamp for incremental fetches."""
    return db.scalar(select(func.max(WindowsEventLog.time_created)).where(
        WindowsEventLog.device_id == device_id,
        WindowsEventLog.channel == "System",
    ))
