"""Single derived device-health contract.

This module does not mutate Device.status. It derives current health from the
persisted ICMP liveness marker and independent SNMP module evidence.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Device
from backend.models.snmp import MonitoringConfig, MonitoringStatus, PollingHistory, PollStatus
from backend.utils.time import utc_now

STALE_MULTIPLIER = 3


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # Most of the existing PostgreSQL DateTime columns are naive but contain
    # India-local time (see the model timestamp helpers). Treating those
    # values as UTC makes every fresh poll look ~5h30m old and incorrectly
    # derives STALE health.
    return value if value.tzinfo else value.replace(tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)


def _age(value: datetime | None, now: datetime) -> float | None:
    value = _aware(value)
    return max(0.0, (now - value).total_seconds()) if value else None


def _snmp_utc_aware(value: datetime | None) -> datetime | None:
    """Normalize SNMP scheduler timestamps, whose legacy naive values are UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _snmp_age(value: datetime | None, now: datetime) -> float | None:
    normalized = _snmp_utc_aware(value)
    return max(0.0, (now - normalized).total_seconds()) if normalized else None


def _icmp_age(value: datetime | None, now: datetime) -> float | None:
    """Age realtime ICMP evidence stored as naive UTC in legacy columns."""
    if value is None:
        return None
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return max(0.0, (now - normalized).total_seconds())


def _icmp_health_evidence(device: Device, now: datetime, interval: int) -> tuple[str, float | None]:
    if device.last_icmp_attempt_at is not None:
        age = _icmp_age(device.last_icmp_attempt_at, now)
        if age is not None and age <= interval * STALE_MULTIPLIER:
            return ("reachable" if device.last_icmp_status == "reachable" else "unreachable", age)
        return "stale", age
    age = _icmp_age(device.last_seen, now)
    if age is not None and age <= interval * STALE_MULTIPLIER:
        return ("reachable" if device.status == "online" else "unreachable" if device.status == "offline" else "stale"), age
    return ("stale" if device.monitoring_status and age is not None else "unknown"), age


def derive_device_health(db: Session, device: Device, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    configs = db.query(MonitoringConfig).filter(MonitoringConfig.device_id == device.id).all()
    enabled = [c for c in configs if c.enabled]
    icmp_enabled = bool(device.monitoring_status)
    icmp_interval = min((c.interval_seconds for c in enabled), default=60)
    icmp, icmp_age = _icmp_health_evidence(device, now, icmp_interval)

    snmp_rows = []
    for config in enabled:
        last = db.query(PollingHistory).filter(
            PollingHistory.device_id == device.id,
            PollingHistory.collector == config.module_name,
        ).order_by(PollingHistory.created_at.desc(), PollingHistory.id.desc()).first()
        last_success = db.query(PollingHistory).filter(
            PollingHistory.device_id == device.id,
            PollingHistory.collector == config.module_name,
            PollingHistory.status == PollStatus.SUCCESS.value,
        ).order_by(PollingHistory.created_at.desc(), PollingHistory.id.desc()).first()
        success_age = _snmp_age(last_success.created_at if last_success else None, now)
        fresh = success_age is not None and success_age <= config.interval_seconds * STALE_MULTIPLIER
        snmp_rows.append({"config": config, "last": last, "last_success": last_success, "age": success_age, "fresh": fresh})

    if not enabled:
        snmp_health = "disabled"
    elif any(r["config"].status == MonitoringStatus.NOT_SUPPORTED.value for r in snmp_rows):
        snmp_health = "unsupported"
    elif any(r["fresh"] and r["last_success"] for r in snmp_rows) and not any(r["config"].status == MonitoringStatus.ERROR.value for r in snmp_rows):
        snmp_health = "healthy"
    elif any(r["config"].status == MonitoringStatus.ERROR.value or (r["last"] and r["last"].status != PollStatus.SUCCESS.value) for r in snmp_rows):
        snmp_health = "failed"
    else:
        snmp_health = "stale"

    if icmp_enabled and icmp == "unreachable":
        status, reason = "offline", "Recent ICMP liveness failure"
    elif icmp_enabled and icmp == "stale":
        status, reason = "stale", "ICMP liveness evidence exceeded the configured freshness window"
    elif icmp_enabled and icmp == "unknown":
        status, reason = "unknown", "No successful ICMP liveness evidence is available"
    elif snmp_health in {"failed", "stale"}:
        status, reason = "degraded", f"ICMP is reachable; SNMP is {snmp_health}"
    elif icmp == "reachable" or snmp_health == "healthy":
        status, reason = "online", "Recent liveness/monitoring evidence is available"
    else:
        status, reason = "unknown", "Insufficient current monitoring evidence"

    latest = max((r["last"] for r in snmp_rows if r["last"]), key=lambda x: _snmp_utc_aware(x.created_at) or datetime.min.replace(tzinfo=timezone.utc), default=None)
    latest_success = max((r["last_success"] for r in snmp_rows if r["last_success"]), key=lambda x: _snmp_utc_aware(x.created_at) or datetime.min.replace(tzinfo=timezone.utc), default=None)
    return {
        "status": status, "last_known_status": device.status, "health_source": "icmp+snmp",
        "health_reason": reason, "last_seen": device.last_seen,
        "last_success_at": latest_success.created_at if latest_success else None,
        "last_failure_at": max((r["last"].created_at for r in snmp_rows if r["last"] and r["last"].status != PollStatus.SUCCESS.value), default=None),
        "last_attempt_at": latest.created_at if latest else None,
        "next_poll_at": min((r["config"].next_poll_at for r in snmp_rows if r["config"].next_poll_at), default=None),
        "age_seconds": _snmp_age(latest_success.created_at, now) if latest_success else icmp_age,
        "expected_interval_seconds": icmp_interval,
        "is_stale": status == "stale" or snmp_health == "stale",
        "freshness_status": "fresh" if status == "online" else status,
        "icmp_health": {"status": icmp, "age_seconds": icmp_age, "enabled": icmp_enabled},
        "snmp_health": {"status": snmp_health, "enabled": bool(enabled)},
    }
