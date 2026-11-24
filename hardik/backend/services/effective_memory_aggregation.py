"""Read-only mixed-source aggregation of fresh persisted memory samples."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.linux_monitoring.models import LinuxServer, LinuxServerCurrentMetric
from backend.models import Device
from backend.models.identity import DeviceCapabilities
from backend.models.snmp import LatestMemory, MonitoringConfig


FRESHNESS_SECONDS = 540
_OPERATIONAL_MEMORY_STATUSES = {"running"}
_LINUX_STORAGE_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None, *, naive_timezone=timezone.utc) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=naive_timezone).astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def _linux_as_utc(value: datetime | None) -> datetime | None:
    """Normalize Linux's naive Asia/Kolkata persistence timestamps."""
    return _as_utc(value, naive_timezone=_LINUX_STORAGE_TIMEZONE)


def _valid_percent(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
        and 0 <= float(value) <= 100
    )


def _normalized_ip(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(ip_address(str(value).strip()))
    except ValueError:
        return str(value).strip().lower() or None


def _fresh(value: datetime | None, evaluated_at: datetime, limit: timedelta) -> bool:
    timestamp = _as_utc(value)
    if timestamp is None:
        return False
    age = evaluated_at - timestamp
    return timedelta(0) <= age <= limit


def _memory_capability(capabilities: Any) -> dict[str, Any]:
    detail = getattr(capabilities, "capability_detail", None) or {}
    memory = detail.get("memory") if isinstance(detail, dict) else None
    return memory if isinstance(memory, dict) else {}


def _linux_memory_sample(row: Any) -> tuple[float | None, str, str]:
    """Select canonical Linux memory, falling back to the legacy field.

    Both values are snapshots from the same current-metric row, so the row's
    collected_at timestamp is the freshness authority for either value.
    """
    details = getattr(row, "details", None) or {}
    memory = details.get("memory") if isinstance(details, dict) else None
    canonical = memory.get("canonical") if isinstance(memory, dict) else None
    if isinstance(canonical, dict):
        value = canonical.get("usage_percent")
        if canonical.get("status") == "ok" and _valid_percent(value):
            return float(value), str(canonical.get("source") or "net-snmp-extend"), str(
                canonical.get("semantic") or "linux_proc_meminfo_memavailable"
            )

    legacy = getattr(row, "memory_percent", None)
    if _valid_percent(legacy):
        return float(legacy), "linux-legacy-db", "ucd_snmp_memtotalreal_memavailreal"
    return None, "", ""


def build_effective_memory_aggregate(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Evaluate fresh persisted Linux and normalized SNMP memory samples."""
    evaluated_at = _as_utc(now) or _utc_now()
    limit = timedelta(seconds=FRESHNESS_SECONDS)
    candidates: list[dict[str, Any]] = []
    stale_candidates: list[dict[str, Any]] = []
    exclusions = {
        "legacy_source": 0,
        "stale": 0,
        "unavailable": 0,
        "unsupported": 0,
        "invalid": 0,
        "duplicate": 0,
        "snmp_missing_config": 0,
        "snmp_missing_latest": 0,
        "snmp_unsupported": 0,
        "snmp_stale": 0,
        "snmp_invalid": 0,
    }

    linux_rows = db.query(LinuxServer, LinuxServerCurrentMetric).outerjoin(
        LinuxServerCurrentMetric,
        LinuxServerCurrentMetric.linux_server_id == LinuxServer.id,
    ).filter(
        LinuxServer.deleted_at.is_(None),
        LinuxServer.enabled.is_(True),
        LinuxServer.status == "active",
    ).all()
    for server, row in linux_rows:
        percent, source, semantic = _linux_memory_sample(row) if row else (None, "", "")
        collected = getattr(row, "collected_at", None) if row else None
        timestamp = _linux_as_utc(collected)
        if not _valid_percent(percent) or timestamp is None:
            exclusions["invalid"] += 1
            continue
        if not _fresh(timestamp, evaluated_at, limit):
            exclusions["stale"] += 1
            if _valid_percent(percent) and timestamp is not None:
                stale_candidates.append({"percent": float(percent), "collected_at": timestamp})
            continue
        candidates.append({
            "key": f"linux:{server.id}",
            "platform": "linux",
            "inventory_id": server.id,
            "ip": _normalized_ip(server.ip_address),
            "percent": float(percent),
            "collected_at": timestamp,
            "source": source,
            "semantic": semantic,
            "priority": 0,
        })

    snmp_rows = db.query(Device, LatestMemory, MonitoringConfig, DeviceCapabilities).outerjoin(
        LatestMemory, LatestMemory.device_id == Device.id,
    ).outerjoin(
        MonitoringConfig,
        (MonitoringConfig.device_id == Device.id) & (MonitoringConfig.module_name == "memory"),
    ).outerjoin(
        DeviceCapabilities,
        DeviceCapabilities.device_id == Device.id,
    ).filter(
        Device.deleted_at.is_(None),
        Device.monitoring_status.is_(True),
        Device.status == "active",
    ).all()
    rows_by_device: dict[Any, list[tuple[Any, Any, Any, Any]]] = {}
    for row in snmp_rows:
        device = row[0]
        rows_by_device.setdefault(device.id, []).append(row)

    def config_rank(config: Any) -> tuple[int, int, str, int]:
        if config is None:
            return (-1, -1, "", -1)
        status = str(getattr(config, "status", "")).lower()
        return (
            int(bool(getattr(config, "enabled", False) and status in _OPERATIONAL_MEMORY_STATUSES)),
            int(bool(getattr(config, "enabled", False))),
            status,
            int(getattr(config, "id", 0) or 0),
        )

    for device_rows in rows_by_device.values():
        device, latest, _, capabilities = device_rows[0]
        configs = [row[2] for row in device_rows if row[2] is not None]
        config = max(configs, key=config_rank) if configs else None
        if config is None:
            exclusions["snmp_missing_config"] += 1
            continue
        if latest is None:
            exclusions["snmp_missing_latest"] += 1
            continue
        if not getattr(config, "enabled", False) or str(getattr(config, "status", "")).lower() not in _OPERATIONAL_MEMORY_STATUSES:
            exclusions["snmp_unsupported"] += 1
            continue
        memory = _memory_capability(capabilities)
        data = memory.get("data") if isinstance(memory.get("data"), dict) else {}
        if memory.get("supported") is not True or memory.get("collection_status") != "SUCCESS":
            exclusions["snmp_unsupported"] += 1
            continue
        source = data.get("source")
        if not isinstance(source, str) or not source:
            exclusions["snmp_unsupported"] += 1
            continue
        percent = getattr(latest, "utilization_percent", None)
        timestamp = _as_utc(getattr(latest, "polled_at", None))
        if not _valid_percent(percent) or timestamp is None:
            exclusions["snmp_invalid"] += 1
            continue
        if not _fresh(getattr(latest, "polled_at", None), evaluated_at, limit):
            exclusions["snmp_stale"] += 1
            if _valid_percent(percent) and timestamp is not None:
                stale_candidates.append({"percent": float(percent), "collected_at": timestamp})
            continue
        candidates.append({
            "key": f"snmp:{device.id}",
            "platform": "snmp",
            "inventory_id": device.id,
            "ip": _normalized_ip(device.ip_address),
            "percent": float(percent),
            "collected_at": timestamp,
            "source": source,
            "semantic": "snmp_normalized_memory_utilization",
            "priority": 1,
        })

    selected: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        identity = f"ip:{candidate['ip']}" if candidate.get("ip") else f"key:{candidate['key']}"
        previous = selected.get(identity)
        if previous is None:
            selected[identity] = candidate
            continue
        ranking = (candidate["priority"], -candidate["collected_at"].timestamp())
        previous_ranking = (previous["priority"], -previous["collected_at"].timestamp())
        if ranking < previous_ranking:
            selected[identity] = candidate
        exclusions["duplicate"] += 1

    included = list(selected.values())
    average = sum(item["percent"] for item in included) / len(included) if included else None
    stale_average = (
        sum(item["percent"] for item in stale_candidates) / len(stale_candidates)
        if stale_candidates else None
    )
    eligible = len(candidates)
    excluded = sum(exclusions.values())
    return {
        "average_percent": average,
        "stale_average_percent": stale_average,
        "reporting_count": len(included),
        "eligible_count": eligible,
        "excluded_count": excluded,
        "as_of": evaluated_at.isoformat(),
        "status": "ok" if included and excluded == 0 else ("partial" if included else "no_data"),
        "source": "mixed-source-memory",
        "semantic": "mixed_source_memory_utilization",
        "freshness_interval_seconds": {"linux": FRESHNESS_SECONDS, "snmp": FRESHNESS_SECONDS},
        "exclusions": exclusions,
        "devices": [
            {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in item.items() if k not in {"ip", "priority"}}
            for item in included
        ],
    }
