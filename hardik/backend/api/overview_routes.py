"""
Overview & Service Control API
================================

GET  /api/v1/overview
    Single endpoint that returns everything the Dashboard needs in one DB query.
    No SNMP polling, no live probes. Pure PostgreSQL read.
    Returns:
        summary     — device counts, alert counts, recent events
        devices     — all devices with latest metric, vendor, type
        alerts      — recent 50 open/acknowledged alerts
        events      — recent 20 events
        services    — current state of all background services

POST /api/v1/monitoring/kill-all
    Stops EVERY background service:
      - SNMPPollingEngine (APScheduler)
      - MonitorEngine (realtime ICMP ping loop)
      - Sets all monitoring_status=False on devices (opt-in flag)
    Returns: { killed: [...], stopped_devices: int }

GET  /api/v1/monitoring/services
    Returns running state of all background services without stopping anything.
"""

from __future__ import annotations

import logging
from threading import Lock
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case
from sqlalchemy.orm import Session, joinedload, load_only

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.services.device_health import derive_device_health
from backend.models.snmp import PollStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Overview & Service Control"])
_OVERVIEW_CACHE_TTL_SECONDS = 10
_OVERVIEW_HISTORY_MAX_ROWS = 5000
_overview_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_overview_cache_lock = Lock()

_POLLING_FAILURE_STATUSES = frozenset({
    PollStatus.TIMEOUT.value,
    PollStatus.AUTHENTICATION_FAILED.value,
    PollStatus.DEVICE_UNREACHABLE.value,
    PollStatus.OID_NOT_SUPPORTED.value,
    PollStatus.ERROR.value,
})
_POLLING_UNSUPPORTED_STATUSES = frozenset({
    PollStatus.NOT_SUPPORTED.value,
    PollStatus.OID_NOT_SUPPORTED.value,
})


def _classify_polling_rows(rows: list[Any]) -> dict[str, Any]:
    """Classify persisted attempts without conflating capability with failure."""
    counts = {
        "successful_attempts": 0, "unsupported_attempts": 0,
        "no_data_attempts": 0, "failed_attempts": 0,
        "unknown_attempts": 0,
    }
    last: dict[str, datetime | None] = {
        "success": None, "failure": None, "unsupported": None,
        "no_data": None, "unknown": None,
    }
    ordered = sorted(
        rows,
        key=lambda row: (
            _overview_timestamp(getattr(row, "created_at", None))
            or datetime.min.replace(tzinfo=timezone.utc),
            getattr(row, "id", 0) or 0,
        ),
        reverse=True,
    )
    for row in ordered:
        status = getattr(row, "status", None)
        if status == PollStatus.SUCCESS.value:
            category = "successful_attempts"
            last_key = "success"
        elif status in _POLLING_UNSUPPORTED_STATUSES:
            category = "unsupported_attempts"
            last_key = "unsupported"
        elif status == PollStatus.NO_DATA.value:
            category = "no_data_attempts"
            last_key = "no_data"
        elif status in _POLLING_FAILURE_STATUSES:
            category = "failed_attempts"
            last_key = "failure"
        else:
            category = "unknown_attempts"
            last_key = "unknown"
        counts[category] += 1
        if last[last_key] is None and getattr(row, "created_at", None) is not None:
            last[last_key] = row.created_at

    eligible = counts["successful_attempts"] + counts["failed_attempts"]
    result = {**counts, "total_attempts": sum(counts.values())}
    result["success_rate"] = (
        counts["successful_attempts"] / eligible if eligible else None
    )
    for key, value in last.items():
        result[f"last_{key}"] = value.isoformat() if value else None
    return result


def _overview_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _capability_entries(capability: Any, module: str, list_key: str) -> list[Any]:
    detail = capability.capability_detail if capability is not None else {}
    item = detail.get(module) if isinstance(detail, dict) else None
    if not isinstance(item, dict) or item.get("collection_status") != "SUCCESS":
        return []
    data = item.get("data")
    entries = data.get(list_key) if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else []


def _overview_network_counts(capabilities: list[Any]) -> dict[str, int]:
    """Aggregate successful, scheduler-authoritative capability snapshots."""
    neighbors: dict[tuple[Any, ...], str] = {}
    for cap in capabilities:
        for module in ("lldp", "cdp"):
            for entry in _capability_entries(cap, module, "neighbors"):
                if not isinstance(entry, dict):
                    continue
                key = (cap.device_id,
                       entry.get("local_port") or entry.get("local_interface"),
                       entry.get("remote_device") or entry.get("device_id") or entry.get("device"),
                       entry.get("remote_port") or entry.get("remote_interface") or entry.get("port"),
                       entry.get("mgmt_address") or entry.get("ip_address"))
                if any(value is not None for value in key[1:]) and neighbors.get(key) != "lldp":
                    neighbors[key] = module
    return {
        "lldp_neighbors": len(neighbors),
        "vlan_count": sum(len(_capability_entries(c, "vlan", "vlans")) for c in capabilities),
        "routing_entries": sum(len(_capability_entries(c, "routing", "routes")) for c in capabilities),
        "arp_entries": sum(len(_capability_entries(c, "arp", "entries")) for c in capabilities),
        "mac_entries": sum(len(_capability_entries(c, "mac_table", "entries")) for c in capabilities),
    }


def _select_current_interfaces(rows: list[Any], intervals: dict[int, int], now: datetime) -> list[dict[str, Any]]:
    """Select one deterministic, freshness-classified row per device/interface."""
    selected: dict[tuple[int, int], Any] = {}
    for row in sorted(rows, key=lambda item: (_overview_timestamp(item.polled_at) or datetime.min.replace(tzinfo=timezone.utc), item.id), reverse=True):
        selected.setdefault((row.device_id, row.interface_id), row)

    result: list[dict[str, Any]] = []
    for row in selected.values():
        measured_at = _overview_timestamp(row.polled_at)
        interval = intervals.get(row.device_id)
        age = max(0.0, (now - measured_at).total_seconds()) if measured_at else None
        fresh = measured_at is not None and interval is not None and age <= interval * 3
        result.append({
            "device_id": row.device_id,
            "interface_id": row.interface_id,
            "name": row.name,
            "oper_status": row.oper_status,
            "admin_status": row.admin_status,
            "speed_bps": row.speed_bps,
            "rx_mbps": row.rx_mbps,
            "tx_mbps": row.tx_mbps,
            "errors": row.errors,
            "discards": row.discards,
            "rx_packets": row.rx_packets,
            "tx_packets": row.tx_packets,
            "utilization_percent": row.utilization_percent,
            "polled_at": measured_at.isoformat() if measured_at else None,
            "freshness": "fresh" if fresh else ("stale" if measured_at else "missing"),
            "freshness_age_seconds": age,
            "freshness_interval_seconds": interval,
        })
    return result


def _aggregate_current_traffic(rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    fresh = [row for row in rows if row["freshness"] == "fresh"]
    rx = [row["rx_mbps"] for row in fresh if row["rx_mbps"] is not None]
    tx = [row["tx_mbps"] for row in fresh if row["tx_mbps"] is not None]
    return (sum(rx) if rx else None, sum(tx) if tx else None)


# ---------------------------------------------------------------------------
# Single overview endpoint — ONE DB round-trip for the entire Dashboard
# ---------------------------------------------------------------------------

@router.get("/overview")
def get_overview(
    hours: int = Query(default=24, ge=1, le=168),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("dashboard:read")),
) -> dict[str, Any]:
    """
    Return everything the Dashboard needs in a single call.
    All data comes from PostgreSQL — no live SNMP, no ping.
    Frontend caches this and never calls individual list endpoints.
    """
    from backend.cache.redis_cache import get_json, set_json  # noqa: PLC0415
    from backend.models import (  # noqa: PLC0415
        Alert, Device, DeviceMetric, DeviceStatusHistory, DeviceType, Event, Interface,
        Vendor, DeviceCredential,
    )
    from backend.models.snmp import (  # noqa: PLC0415
        LatestCPU, LatestMemory, LatestStorage, LatestInterface,
        LatestEnvironment, InterfaceStatistic, PollingHistory,
        MonitoringConfig, OIDCache,
    )
    from backend.models.identity import DeviceCapabilities  # noqa: PLC0415

    now_ts = datetime.utcnow().timestamp()
    redis_key = f"nms:overview:v1:hours:{hours}"
    if not force_refresh:
        redis_value = get_json(redis_key)
        if isinstance(redis_value, dict):
            return redis_value
        with _overview_cache_lock:
            cached = _overview_cache.get(hours)
            if cached and now_ts - cached[0] < _OVERVIEW_CACHE_TTL_SECONDS:
                return cached[1]

    since_24h = datetime.utcnow() - timedelta(hours=hours)

    # ── devices (with vendor and type joined) ──────────────────────────────
    device_rows = (
        db.query(Device)
        .options(
            load_only(
                Device.id, Device.hostname, Device.ip_address, Device.mac_address,
                Device.status, Device.monitoring_status, Device.vendor_id,
                Device.device_type_id, Device.model, Device.serial_number,
                Device.firmware_version, Device.uptime_seconds, Device.last_seen,
                Device.created_at, Device.site_id,
            ),
            joinedload(Device.vendor).load_only(Vendor.id, Vendor.vendor_name),
            joinedload(Device.device_type).load_only(DeviceType.id, DeviceType.name),
        )
        .filter(Device.deleted_at.is_(None))
        .order_by(Device.hostname)
        .all()
    )
    device_ids = [device.id for device in device_rows]

    # Historical availability for the selected dashboard window. For each
    # device, carry the last known state into the window and accumulate the
    # time spent online across status transitions.
    availability_start = since_24h
    availability_end = datetime.utcnow()
    status_rows = db.query(DeviceStatusHistory).filter(
        DeviceStatusHistory.device_id.in_(device_ids),
        DeviceStatusHistory.timestamp < availability_end,
    ).order_by(DeviceStatusHistory.device_id, DeviceStatusHistory.timestamp.asc(), DeviceStatusHistory.id.asc()).all() if device_ids else []
    status_by_device: dict[int, list[DeviceStatusHistory]] = {}
    for row in status_rows:
        status_by_device.setdefault(row.device_id, []).append(row)
    online_seconds = 0.0
    monitored_seconds = 0.0
    for device in device_rows:
        rows = status_by_device.get(device.id, [])
        before = [row for row in rows if row.timestamp < availability_start]
        inside = [row for row in rows if availability_start <= row.timestamp < availability_end]
        state = (before[-1].new_status if before else device.status or "unknown").lower()
        cursor = availability_start
        for row in inside:
            transition = max(0.0, (row.timestamp - cursor).total_seconds())
            monitored_seconds += transition
            if state in ("online", "up"):
                online_seconds += transition
            state = (row.new_status or "unknown").lower()
            cursor = row.timestamp
        transition = max(0.0, (availability_end - cursor).total_seconds())
        monitored_seconds += transition
        if state in ("online", "up"):
            online_seconds += transition
    historical_availability = (online_seconds / monitored_seconds * 100) if monitored_seconds else None

    # ── latest metric per device (one query) ──────────────────────────────
    from sqlalchemy import func  # noqa: PLC0415
    # Subquery: max metric id per device
    sub = (
        db.query(
            DeviceMetric.device_id,
            func.max(DeviceMetric.id).label("max_id"),
        )
        .group_by(DeviceMetric.device_id)
        .subquery()
    )
    latest_metrics_raw = (
        db.query(DeviceMetric)
        .options(load_only(
            DeviceMetric.device_id, DeviceMetric.cpu_usage, DeviceMetric.memory_usage,
            DeviceMetric.temperature, DeviceMetric.latency, DeviceMetric.packet_loss,
            DeviceMetric.created_at,
        ))
        .join(sub, DeviceMetric.id == sub.c.max_id)
        .filter(DeviceMetric.device_id.in_(device_ids))
        .all()
    )
    metric_by_device: dict[int, DeviceMetric] = {m.device_id: m for m in latest_metrics_raw} if device_ids else {}

    # Range-based performance averages for the dashboard gauges. These are
    # calculated from every persisted metric sample in the selected window,
    # rather than averaging only the latest reading from each device.
    performance_average = db.query(
        func.avg(DeviceMetric.cpu_usage).label("avg_cpu"),
        func.avg(DeviceMetric.memory_usage).label("avg_memory"),
    ).filter(
        DeviceMetric.created_at >= since_24h,
        DeviceMetric.device_id.in_(device_ids),
    ).one() if device_ids else None
    performance_sample_count = db.query(func.count(DeviceMetric.id)).filter(
        DeviceMetric.created_at >= since_24h,
        DeviceMetric.device_id.in_(device_ids),
    ).scalar() if device_ids else 0

    # ── interface counts per device ────────────────────────────────────────
    # Keep this query simple and portable. The previous cast-based aggregate
    # broke on SQLite/PostgreSQL type handling and was unused anyway.
    iface_counts = db.query(
        Interface.device_id,
        func.count(Interface.id).label("total"),
        func.coalesce(func.sum(case((Interface.status == "up", 1), else_=0)), 0).label("up"),
    ).filter(Interface.device_id.in_(device_ids)).group_by(Interface.device_id).all() if device_ids else []
    iface_counts_by_device = {row.device_id: row for row in iface_counts}

    # ── SNMP credential versions ───────────────────────────────────────────
    cred_versions: dict[int, str] = {
        c.device_id: c.snmp_version or ""
        for c in db.query(DeviceCredential.device_id, DeviceCredential.snmp_version)
        .filter(DeviceCredential.device_id.in_(device_ids)).all()
    }

    # ── build device list ──────────────────────────────────────────────────
    devices_out: list[dict[str, Any]] = []
    total = online = offline = 0
    health_counts = {state: 0 for state in ("online", "offline", "degraded", "stale", "unknown")}
    for dev in device_rows:
        total += 1
        health = derive_device_health(db, dev)
        derived_status = health["status"]
        health_counts[derived_status] += 1
        if derived_status == "online": online += 1
        elif derived_status == "offline": offline += 1

        met = metric_by_device.get(dev.id)
        interface_count = iface_counts_by_device.get(dev.id)
        devices_out.append({
            "id":               dev.id,
            "hostname":         dev.hostname,
            "ip_address":       dev.ip_address,
            "mac_address":      dev.mac_address,
            "status":           dev.status,
            "health":           health,
            "monitoring_status": dev.monitoring_status,
            "vendor":           dev.vendor.vendor_name if dev.vendor else None,
            "device_type":      dev.device_type.name if dev.device_type else None,
            "model":            dev.model,
            "serial_number":    dev.serial_number,
            "firmware_version": dev.firmware_version,
            "uptime_seconds":   dev.uptime_seconds,
            "last_seen":        dev.last_seen.isoformat() if dev.last_seen else None,
            "created_at":       dev.created_at.isoformat() if dev.created_at else None,
            "site_id":          dev.site_id,
            "snmp_version":     cred_versions.get(dev.id),
            "interface_count":  int(interface_count.total or 0) if interface_count else 0,
            "interfaces_up":    int(interface_count.up or 0) if interface_count else 0,
            "cpu_usage":        met.cpu_usage if met else None,
            "memory_usage":     met.memory_usage if met else None,
            "temperature":      met.temperature if met else None,
            "latency":          met.latency if met else None,
            "packet_loss":      met.packet_loss if met else None,
            "metric_at":        met.created_at.isoformat() if met else None,
        })

    # ── alerts ─────────────────────────────────────────────────────────────
    alert_rows = (
        db.query(Alert)
        .options(load_only(
            Alert.id, Alert.device_id, Alert.severity, Alert.title,
            Alert.description, Alert.status, Alert.created_at,
        ))
        .filter(
            Alert.status.in_(["open", "acknowledged"]),
            Alert.deleted_at.is_(None),
            Alert.created_at >= since_24h,
        )
        .order_by(Alert.created_at.desc())
        .limit(50)
        .all()
    )
    active_alerts   = len(alert_rows)
    critical_alerts = sum(1 for a in alert_rows if a.severity == "critical")

    # Exact timestamp correlation: count an alert once when the same device
    # has an outage transition or high performance sample within +/- 5 min.
    correlation_window = timedelta(minutes=5)
    correlation_metrics = db.query(DeviceMetric).filter(
        DeviceMetric.device_id.in_(device_ids),
        DeviceMetric.created_at >= since_24h - correlation_window,
        DeviceMetric.created_at <= datetime.utcnow() + correlation_window,
    ).all() if device_ids else []
    offline_events_by_device: dict[int, list[datetime]] = {}
    for row in status_rows:
        if str(row.new_status or "").lower() in ("offline", "down"):
            offline_events_by_device.setdefault(row.device_id, []).append(row.timestamp)
    high_metrics_by_device: dict[int, list[datetime]] = {}
    for row in correlation_metrics:
        if (row.cpu_usage is not None and row.cpu_usage >= 85) or (row.memory_usage is not None and row.memory_usage >= 85):
            high_metrics_by_device.setdefault(row.device_id, []).append(row.created_at)
    correlated_outage_alerts = 0
    correlated_performance_alerts = 0
    for alert in alert_rows:
        if alert.device_id is None or alert.created_at is None:
            continue
        if any(abs(alert.created_at - timestamp) <= correlation_window for timestamp in offline_events_by_device.get(alert.device_id, [])):
            correlated_outage_alerts += 1
        if any(abs(alert.created_at - timestamp) <= correlation_window for timestamp in high_metrics_by_device.get(alert.device_id, [])):
            correlated_performance_alerts += 1

    alerts_out = [
        {
            "id":          a.id,
            "device_id":   a.device_id,
            "severity":    a.severity,
            "title":       a.title,
            "description": a.description,
            "status":      a.status,
            "created_at":  a.created_at.isoformat() if a.created_at else None,
        }
        for a in alert_rows
    ]

    # ── recent events ──────────────────────────────────────────────────────
    event_rows = (
        db.query(Event)
        .options(load_only(
            Event.id, Event.device_id, Event.event_type,
            Event.description, Event.timestamp,
        ))
        .filter(Event.timestamp >= since_24h, Event.deleted_at.is_(None))
        .order_by(Event.timestamp.desc())
        .limit(20)
        .all()
    )
    events_out = [
        {
            "id":          e.id,
            "device_id":   e.device_id,
            "event_type":  e.event_type,
            "description": e.description,
            "timestamp":   e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in event_rows
    ]

    # Normalized SNMP data is read from latest_* and history tables. This
    # endpoint never polls devices, so dashboard refreshes cannot create jobs.
    latest_cpu = {
        row.device_id: row for row in db.query(LatestCPU).options(load_only(
            LatestCPU.device_id, LatestCPU.utilization_percent, LatestCPU.load_avg,
        )).filter(LatestCPU.device_id.in_(device_ids)).all()
    } if device_ids else {}
    latest_memory = {
        row.device_id: row for row in db.query(LatestMemory).options(load_only(
            LatestMemory.device_id, LatestMemory.utilization_percent,
        )).filter(LatestMemory.device_id.in_(device_ids)).all()
    } if device_ids else {}
    latest_storage = db.query(LatestStorage).options(load_only(
        LatestStorage.device_id, LatestStorage.mount_name,
        LatestStorage.utilization_percent, LatestStorage.polled_at,
    )).filter(LatestStorage.device_id.in_(device_ids)).all() if device_ids else []
    latest_interface_rows = db.query(LatestInterface).options(load_only(
        LatestInterface.id,
        LatestInterface.device_id, LatestInterface.interface_id, LatestInterface.name,
        LatestInterface.oper_status, LatestInterface.admin_status, LatestInterface.speed_bps,
        LatestInterface.rx_mbps, LatestInterface.tx_mbps, LatestInterface.errors,
        LatestInterface.discards, LatestInterface.rx_packets, LatestInterface.tx_packets,
        LatestInterface.utilization_percent, LatestInterface.polled_at,
    )).filter(LatestInterface.device_id.in_(device_ids)).order_by(
        LatestInterface.polled_at.desc(), LatestInterface.id.desc()
    ).all() if device_ids else []
    interface_configs = db.query(MonitoringConfig.device_id, MonitoringConfig.interval_seconds).filter(
        MonitoringConfig.device_id.in_(device_ids),
        MonitoringConfig.module_name == "interfaces",
        MonitoringConfig.enabled.is_(True),
    ).all() if device_ids else []
    interface_intervals: dict[int, int] = {}
    for config in interface_configs:
        current = interface_intervals.get(config.device_id)
        interface_intervals[config.device_id] = min(current, config.interval_seconds) if current is not None else config.interval_seconds
    latest_environment = db.query(LatestEnvironment).options(load_only(
        LatestEnvironment.device_id, LatestEnvironment.sensor_name,
        LatestEnvironment.sensor_type, LatestEnvironment.value,
        LatestEnvironment.unit, LatestEnvironment.status, LatestEnvironment.polled_at,
    )).filter(LatestEnvironment.device_id.in_(device_ids)).all() if device_ids else []
    interface_stats = db.query(InterfaceStatistic).options(load_only(
        InterfaceStatistic.device_id, InterfaceStatistic.rx_mbps,
        InterfaceStatistic.tx_mbps, InterfaceStatistic.utilization_percent,
        InterfaceStatistic.created_at,
    )).filter(InterfaceStatistic.created_at >= since_24h).order_by(
        InterfaceStatistic.created_at.desc()
    ).limit(_OVERVIEW_HISTORY_MAX_ROWS).all()
    interface_stats.reverse()
    polling_rows = db.query(PollingHistory).options(load_only(
        PollingHistory.id, PollingHistory.device_id, PollingHistory.created_at,
        PollingHistory.status, PollingHistory.collector, PollingHistory.error,
    )).filter(PollingHistory.created_at >= since_24h).order_by(PollingHistory.created_at.desc()).all()
    device_by_id = {device.id: device for device in device_rows}

    storage_by_device: dict[int, list[dict[str, Any]]] = {}
    for row in latest_storage:
        storage_by_device.setdefault(row.device_id, []).append({
            "mount_name": row.mount_name,
            "utilization_percent": row.utilization_percent,
            "polled_at": row.polled_at.isoformat() if row.polled_at else None,
        })
    environment_by_device: dict[int, list[dict[str, Any]]] = {}
    for row in latest_environment:
        environment_by_device.setdefault(row.device_id, []).append({
            "sensor_name": row.sensor_name, "sensor_type": row.sensor_type,
            "value": row.value, "unit": row.unit, "status": row.status,
            "polled_at": row.polled_at.isoformat() if row.polled_at else None,
        })
    interface_rows = _select_current_interfaces(
        latest_interface_rows, interface_intervals, datetime.now(timezone.utc)
    )
    for row in interface_rows:
        row["device_name"] = device_by_id.get(row["device_id"]).hostname if device_by_id.get(row["device_id"]) else None
    current_rx, current_tx = _aggregate_current_traffic(interface_rows)
    latest_poll_by_device: dict[int, dict[str, Any]] = {}
    for row in polling_rows:
        latest_poll_by_device.setdefault(row.device_id, {
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "status": row.status, "collector": row.collector, "error": row.error,
        })
    top_devices: dict[int, dict[str, Any]] = {}
    for row in interface_rows:
        if row["freshness"] != "fresh":
            continue
        item = top_devices.setdefault(row["device_id"], {
            "device_id": row["device_id"], "device_name": row["device_name"], "rx_mbps": None, "tx_mbps": None,
        })
        if row["rx_mbps"] is not None:
            item["rx_mbps"] = (item["rx_mbps"] or 0) + row["rx_mbps"]
        if row["tx_mbps"] is not None:
            item["tx_mbps"] = (item["tx_mbps"] or 0) + row["tx_mbps"]
    alert_counts = {severity: sum(1 for alert in alert_rows if alert.severity == severity) for severity in ("critical", "high", "medium", "low", "warning", "info")}
    type_counts: dict[str, int] = {}
    for device in device_rows:
        type_name = device.device_type.name if device.device_type else "Other"
        type_counts[type_name] = type_counts.get(type_name, 0) + 1
    dashboard_counts = db.query(
        db.query(func.count(MonitoringConfig.id)).filter(MonitoringConfig.enabled.is_(True)).scalar_subquery().label("configured_jobs"),
        db.query(func.count(OIDCache.id)).filter(OIDCache.supported.is_(False)).scalar_subquery().label("unsupported_oids"),
    ).one()
    capabilities = db.query(DeviceCapabilities).filter(
        DeviceCapabilities.device_id.in_(device_ids),
    ).all() if device_ids else []
    network_counts = _overview_network_counts(capabilities)
    # Some deployments populate the SNMP latest tables but do not retain
    # DeviceMetric history. Keep the gauges useful in that case by falling
    # back to the latest per-device SNMP values.
    avg_cpu = performance_average.avg_cpu if performance_average else None
    avg_memory = performance_average.avg_memory if performance_average else None
    if avg_cpu is None:
        cpu_values = [row.utilization_percent for row in latest_cpu.values() if row.utilization_percent is not None]
        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else None
    if avg_memory is None:
        memory_values = [row.utilization_percent for row in latest_memory.values() if row.utilization_percent is not None]
        avg_memory = sum(memory_values) / len(memory_values) if memory_values else None

    normalized = {
        "performance": {
            "avg_cpu": float(avg_cpu) if avg_cpu is not None else None,
            "avg_memory": float(avg_memory) if avg_memory is not None else None,
            "sample_count": int(performance_sample_count or 0),
        },
        "correlation": {
            "window_minutes": 5,
            "correlated_outage_alerts": correlated_outage_alerts,
            "correlated_performance_alerts": correlated_performance_alerts,
        },
        "devices": {
            str(device.id): {
                "cpu": latest_cpu.get(device.id).utilization_percent if latest_cpu.get(device.id) else None,
                "memory": latest_memory.get(device.id).utilization_percent if latest_memory.get(device.id) else None,
                "load": latest_cpu.get(device.id).load_avg if latest_cpu.get(device.id) else None,
                "uptime_seconds": device.uptime_seconds,
                "storage": storage_by_device.get(device.id, []),
                "environment": environment_by_device.get(device.id, []),
                "last_poll": latest_poll_by_device.get(device.id),
            } for device in device_rows
        },
        "interfaces": interface_rows,
        "traffic_history": [{
            "timestamp": _overview_timestamp(row.created_at).isoformat() if row.created_at else None,
            "device_id": row.device_id, "rx_mbps": row.rx_mbps, "tx_mbps": row.tx_mbps,
            "utilization_percent": row.utilization_percent,
        } for row in interface_stats],
        "traffic": {
            "rx_mbps": current_rx,
            "tx_mbps": current_tx,
            "fresh_interface_count": sum(1 for row in interface_rows if row["freshness"] == "fresh"),
            "interface_count": len(interface_rows),
            "top_devices": sorted(top_devices.values(), key=lambda item: item["rx_mbps"] + item["tx_mbps"], reverse=True)[:8],
            "top_interfaces": sorted(interface_rows, key=lambda item: (item["rx_mbps"] or 0) + (item["tx_mbps"] or 0), reverse=True)[:8],
        },
        "polling": {
            **(polling_summary := _classify_polling_rows(polling_rows)),
            "success": polling_summary["successful_attempts"],
            "failure": polling_summary["failed_attempts"],
            "active_jobs": dashboard_counts.configured_jobs,
            "configured_jobs": dashboard_counts.configured_jobs,
            "enabled_jobs": dashboard_counts.configured_jobs,
            "collector_failures": polling_summary["failed_attempts"],
            "unsupported_oids": dashboard_counts.unsupported_oids,
        },
        "interface_summary": {
            "total": len(interface_rows),
            "up": sum(1 for row in interface_rows if str(row["oper_status"]).lower() in ("up", "upward")),
            "down": sum(1 for row in interface_rows if str(row["oper_status"]).lower() in ("down", "downward")),
            "errors": sum(row["errors"] or 0 for row in interface_rows),
            "drops": sum(row["discards"] or 0 for row in interface_rows),
        },
        "alerts_by_severity": alert_counts,
        "device_types": type_counts,
        "network": {
            "lldp_neighbors": network_counts["lldp_neighbors"],
            "vlan_count": network_counts["vlan_count"],
            "routing_entries": network_counts["routing_entries"],
            "arp_entries": network_counts["arp_entries"],
            "mac_entries": network_counts["mac_entries"],
            "topology_nodes": len(device_rows),
        },
    }

    # ── background service status ──────────────────────────────────────────
    services = _get_service_states()

    payload = {
        "summary": {
            "total_devices":    total,
            "online_devices":   online,
            "offline_devices":  offline,
            "warning_devices":  total - online - offline,
            "health_counts":     health_counts,
            "active_alerts":    active_alerts,
            "critical_alerts":  critical_alerts,
            "recent_events":    len(event_rows),
            "historical_availability_pct": round(historical_availability, 2) if historical_availability is not None else None,
        },
        "devices":  devices_out,
        "alerts":   alerts_out,
        "events":   events_out,
        "normalized": normalized,
        "services": services,
        "fetched_at": datetime.utcnow().isoformat(),
    }
    with _overview_cache_lock:
        _overview_cache[hours] = (now_ts, payload)
    # Keep the dashboard snapshot short-lived. The in-process cache is 10s;
    # using the global Redis TTL here could otherwise serve an old overview
    # long after a new poll has been persisted.
    set_json(redis_key, payload, ttl_seconds=_OVERVIEW_CACHE_TTL_SECONDS)
    return payload


# ---------------------------------------------------------------------------
# Kill all background services
# ---------------------------------------------------------------------------

@router.post("/monitoring/kill-all")
def kill_all_services(
    request: Request,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("monitoring:execute")),
) -> dict[str, Any]:
    """
    Stop every background monitoring service immediately.

    Services stopped:
      1. SNMPPollingEngine   — APScheduler interval jobs
      2. MonitorEngine       — ICMP ping background thread
      3. Auto-refresh flag   — frontend should read this and stop polling

    Does NOT delete any data. Devices remain in DB.
    Does NOT set monitoring_status=False — that is a manual opt-out.
    """
    killed: list[str] = []
    errors: list[str] = []

    # ── 1. SNMPPollingEngine ───────────────────────────────────────────────
    try:
        polling: Any = getattr(request.app.state, "snmp_polling", None)
        if polling is not None:
            polling.shutdown()
            request.app.state.snmp_polling = None
            killed.append("snmp_polling_engine")
            logger.info("kill_all: SNMPPollingEngine stopped")
        else:
            killed.append("snmp_polling_engine (was not running)")
    except Exception as exc:
        errors.append(f"snmp_polling_engine: {exc}")
        logger.error("kill_all: SNMPPollingEngine stop failed: %s", exc)

    # ── 2. MonitorEngine (ICMP realtime ping) ─────────────────────────────
    try:
        from backend.services.realtime_monitor import get_engine  # noqa: PLC0415
        engine = get_engine()
        stopped = engine.stop_all()
        # Also signal the internal stop event so the loop thread exits
        engine._stop_event.set()
        killed.append(f"realtime_monitor ({stopped} devices removed)")
        logger.info("kill_all: MonitorEngine stopped, %d devices cleared", stopped)
    except Exception as exc:
        errors.append(f"realtime_monitor: {exc}")
        logger.error("kill_all: MonitorEngine stop failed: %s", exc)

    # ── 3. Mark all devices as monitoring paused (non-destructive flag) ───
    try:
        from backend.models import Device  # noqa: PLC0415
        paused_count = (
            db.query(Device)
            .filter(Device.deleted_at.is_(None), Device.monitoring_status.is_(True))
            .update({"monitoring_status": False})
        )
        db.commit()
        killed.append(f"device_polling_flags ({paused_count} devices paused)")
        logger.info("kill_all: %d device monitoring_status flags set to False", paused_count)
    except Exception as exc:
        db.rollback()
        errors.append(f"device_flags: {exc}")
        logger.error("kill_all: Device flag update failed: %s", exc)

    return {
        "success": len(errors) == 0,
        "killed":  killed,
        "errors":  errors,
        "message": "All monitoring services stopped. Restart the backend to resume automatic polling.",
        "stopped_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Service status (read-only)
# ---------------------------------------------------------------------------

@router.get("/monitoring/services")
def get_service_states_endpoint(
    request: Request,
    _: Any = Depends(require_permission("dashboard:read")),
) -> dict[str, Any]:
    """Return running state of all background services."""
    return _get_service_states(request)


@router.post("/monitoring/polling/start")
async def start_polling_service(
    request: Request,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("dashboard:read")),
) -> dict[str, Any]:
    """Recover the scheduler when the API process is alive but polling was stopped.

    Only enabled configs are restored; explicitly disabled jobs remain disabled.
    """
    from backend.services.snmp_polling import get_polling_scheduler

    if not getattr(request.app.state, "scheduler_lease_owned", False):
        return _get_service_states(request)
    scheduler = await get_polling_scheduler()
    request.app.state.snmp_polling = scheduler
    return _get_service_states(request)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_service_states(request: Request | None = None) -> dict[str, Any]:
    """Inspect every background service and return its current state."""
    # SNMP polling
    snmp_running = False
    snmp_jobs    = 0
    lease_owned = False
    polling = None
    registered_job_ids: list[str] = []
    registered_job_details: list[dict[str, Any]] = []
    try:
        if request is not None:
            polling = getattr(request.app.state, "snmp_polling", None)
            lease_owned = bool(getattr(request.app.state, "scheduler_lease_owned", False))
            if polling is not None and polling.scheduler is not None:
                snmp_running = polling.scheduler.running
                jobs = polling.scheduler.get_jobs()
                snmp_jobs = len(jobs)
                registered_job_ids, registered_job_details = _registered_job_observability(jobs)
        else:
            # Called from overview (no request ref) — try importing app
            from backend.main import app  # noqa: PLC0415
            polling = getattr(app.state, "snmp_polling", None)
            lease_owned = bool(getattr(app.state, "scheduler_lease_owned", False))
            if polling is not None and polling.scheduler is not None:
                snmp_running = polling.scheduler.running
                jobs = polling.scheduler.get_jobs()
                snmp_jobs = len(jobs)
                registered_job_ids, registered_job_details = _registered_job_observability(jobs)
    except Exception:
        pass

    # Realtime monitor
    monitor_running  = False
    monitor_devices  = 0
    monitor_summary: dict[str, Any] = {}
    try:
        from backend.services.realtime_monitor import get_engine  # noqa: PLC0415
        engine = get_engine()
        summary = engine.get_summary()
        monitor_running = summary.get("loop_running", False)
        monitor_devices = summary.get("total_monitored", 0)
        monitor_summary = summary
    except Exception:
        pass

    return {
        "snmp_polling": {
            "running":   snmp_running,
            "job_count": snmp_jobs,
            "scheduler_running": snmp_running,
            "scheduler_state": "running" if snmp_running else "stopped",
            "lease_owned": lease_owned,
            "registered_jobs": snmp_jobs,
            "registered_job_ids": registered_job_ids,
            "registered_job_details": registered_job_details,
            "active_jobs": getattr(polling, "active_jobs", 0) if polling else 0,
            "last_job_started_at": getattr(polling, "last_job_started_at", None).isoformat().replace("+00:00", "Z") if getattr(polling, "last_job_started_at", None) else None,
            "last_job_finished_at": getattr(polling, "last_job_finished_at", None).isoformat().replace("+00:00", "Z") if getattr(polling, "last_job_finished_at", None) else None,
            "last_job_success_at": getattr(polling, "last_job_success_at", None).isoformat().replace("+00:00", "Z") if getattr(polling, "last_job_success_at", None) else None,
            "last_job_failure_at": getattr(polling, "last_job_failure_at", None).isoformat().replace("+00:00", "Z") if getattr(polling, "last_job_failure_at", None) else None,
            "recent_failure_count": getattr(polling, "recent_failure_count", 0) if polling else 0,
            "label":     "SNMP Polling Engine (APScheduler)",
        },
        "realtime_monitor": {
            "running":       monitor_running,
            "device_count":  monitor_devices,
            "summary":       monitor_summary,
            "label":         "Realtime ICMP Monitor",
        },
        "any_running": snmp_running or monitor_running,
    }


def _registered_job_observability(jobs: list[Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """Extract safe metadata from live APScheduler jobs without side effects."""
    details: list[dict[str, Any]] = []
    for job in jobs:
        args = list(getattr(job, "args", ()) or ())
        details.append({
            "job_id": str(getattr(job, "id", "")),
            "next_run_at": getattr(job, "next_run_time", None).isoformat() if getattr(job, "next_run_time", None) else None,
            "config_id": args[3] if len(args) > 3 else None,
            "device_id": args[0] if len(args) > 0 else None,
            "module_name": args[1] if len(args) > 1 else None,
        })
    details.sort(key=lambda item: item["job_id"])
    return [item["job_id"] for item in details], details


# ---------------------------------------------------------------------------
# Daily Network Monitoring Report — single endpoint, all 24h data
# ---------------------------------------------------------------------------

@router.get("/reports/daily")
def get_daily_report(
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("reports:read")),
) -> dict[str, Any]:
    """
    Return all data needed for the Daily Network Monitoring Report.
    Covers the previous 24 hours. All sections included. Pure DB read.
    """
    from backend.models import (  # noqa: PLC0415
        Alert, Device, DeviceMetric, DeviceStatusHistory,
        Event, Interface, Vendor, DeviceType,
    )
    from sqlalchemy import func  # noqa: PLC0415

    now   = datetime.utcnow()
    since = now - timedelta(hours=24)
    report_date = now.strftime("%Y-%m-%d")
    period_label = f"{since.strftime('%Y-%m-%d %H:%M')} UTC  →  {now.strftime('%Y-%m-%d %H:%M')} UTC"

    # ── 1. DEVICE AVAILABILITY ────────────────────────────────────────────
    all_devices = (
        db.query(Device)
        .filter(Device.deleted_at.is_(None))
        .all()
    )
    total_devices = len(all_devices)
    online_devices  = sum(1 for d in all_devices if d.status == "online")
    offline_devices = sum(1 for d in all_devices if d.status == "offline")
    warning_devices = total_devices - online_devices - offline_devices
    avail_pct = round(online_devices / total_devices * 100, 2) if total_devices else 0.0

    # Devices that went down in the last 24h
    downtime_events = (
        db.query(DeviceStatusHistory)
        .filter(
            DeviceStatusHistory.timestamp >= since,
            DeviceStatusHistory.new_status == "offline",
        )
        .all()
    )
    devices_with_downtime = list({e.device_id for e in downtime_events})
    downtime_detail = []
    for dev in all_devices:
        if dev.id in devices_with_downtime or dev.status == "offline":
            downtime_detail.append({
                "id":             dev.id,
                "hostname":       dev.hostname,
                "ip_address":     dev.ip_address,
                "status":         dev.status,
                "downtime_secs":  dev.downtime_seconds,
                "last_seen":      dev.last_seen.isoformat() if dev.last_seen else None,
            })

    availability_section = {
        "total_devices":        total_devices,
        "online":               online_devices,
        "offline":              offline_devices,
        "warning":              warning_devices,
        "availability_pct":     avail_pct,
        "devices_with_downtime": downtime_detail,
        "downtime_events_24h":  len(downtime_events),
    }

    # ── 2. PERFORMANCE MONITORING ─────────────────────────────────────────
    metrics_24h = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.created_at >= since)
        .all()
    )

    def _avg(values: list[float]) -> float | None:
        cleaned = [v for v in values if v is not None]
        return round(sum(cleaned) / len(cleaned), 2) if cleaned else None

    def _max(values: list[float]) -> float | None:
        cleaned = [v for v in values if v is not None]
        return round(max(cleaned), 2) if cleaned else None

    cpu_values     = [m.cpu_usage    for m in metrics_24h if m.cpu_usage    is not None]
    mem_values     = [m.memory_usage for m in metrics_24h if m.memory_usage is not None]
    disk_values    = [m.disk_usage   for m in metrics_24h if m.disk_usage   is not None]
    latency_values = [m.latency      for m in metrics_24h if m.latency      is not None]
    loss_values    = [m.packet_loss  for m in metrics_24h if m.packet_loss  is not None]
    bw_values      = [m.bandwidth_usage for m in metrics_24h if m.bandwidth_usage is not None]

    # Per-device averages for top-N tables
    device_cpu: dict[int, list[float]] = {}
    device_mem: dict[int, list[float]] = {}
    device_latency: dict[int, list[float]] = {}
    for m in metrics_24h:
        if m.cpu_usage    is not None: device_cpu.setdefault(m.device_id, []).append(m.cpu_usage)
        if m.memory_usage is not None: device_mem.setdefault(m.device_id, []).append(m.memory_usage)
        if m.latency      is not None: device_latency.setdefault(m.device_id, []).append(m.latency)

    dev_map = {d.id: d for d in all_devices}

    def _top_devices(d_map: dict[int, list[float]], n: int = 5) -> list[dict]:
        avgs = {did: round(sum(vals)/len(vals), 2) for did, vals in d_map.items() if vals}
        top  = sorted(avgs.items(), key=lambda x: x[1], reverse=True)[:n]
        return [
            {
                "device_id": did,
                "hostname":  dev_map[did].hostname if did in dev_map else f"Device-{did}",
                "ip":        dev_map[did].ip_address if did in dev_map else "—",
                "avg_value": avg,
                "max_value": round(max(d_map[did]), 2),
            }
            for did, avg in top
        ]

    performance_section = {
        "sample_count":       len(metrics_24h),
        "cpu":     { "avg": _avg(cpu_values),     "max": _max(cpu_values),     "samples": len(cpu_values) },
        "memory":  { "avg": _avg(mem_values),     "max": _max(mem_values),     "samples": len(mem_values) },
        "disk":    { "avg": _avg(disk_values),    "max": _max(disk_values),    "samples": len(disk_values) },
        "latency": { "avg": _avg(latency_values), "max": _max(latency_values), "samples": len(latency_values) },
        "packet_loss": { "avg": _avg(loss_values), "max": _max(loss_values),   "samples": len(loss_values) },
        "bandwidth":   { "avg": _avg(bw_values),   "max": _max(bw_values),    "samples": len(bw_values) },
        "top_cpu_devices":     _top_devices(device_cpu),
        "top_mem_devices":     _top_devices(device_mem),
        "top_latency_devices": _top_devices(device_latency),
    }

    # ── 3. INTERFACE DETAILS ──────────────────────────────────────────────
    all_interfaces = db.query(Interface).all()
    if_total   = len(all_interfaces)
    if_up      = sum(1 for i in all_interfaces if i.status == "up")
    if_down    = sum(1 for i in all_interfaces if i.status == "down")

    # High traffic interfaces (top 10 by traffic_in + traffic_out)
    high_traffic = sorted(
        [i for i in all_interfaces if (i.traffic_in or 0) + (i.traffic_out or 0) > 0],
        key=lambda x: (x.traffic_in or 0) + (x.traffic_out or 0),
        reverse=True,
    )[:10]

    # Interfaces with errors
    error_ifaces = [i for i in all_interfaces if i.packet_errors > 0]

    interfaces_section = {
        "total":      if_total,
        "up":         if_up,
        "down":       if_down,
        "high_traffic": [
            {
                "id":           i.id,
                "name":         i.interface_name,
                "device_id":    i.device_id,
                "hostname":     dev_map.get(i.device_id, None) and dev_map[i.device_id].hostname or "—",
                "status":       i.status,
                "traffic_in":   i.traffic_in,
                "traffic_out":  i.traffic_out,
                "speed":        i.speed,
                "last_updated": i.last_updated.isoformat() if i.last_updated else None,
            }
            for i in high_traffic
        ],
        "interfaces_with_errors": [
            {
                "id":            i.id,
                "name":          i.interface_name,
                "device_id":     i.device_id,
                "hostname":      dev_map.get(i.device_id) and dev_map[i.device_id].hostname or "—",
                "packet_errors": i.packet_errors,
                "status":        i.status,
            }
            for i in error_ifaces
        ],
        "down_interfaces": [
            {
                "id":       i.id,
                "name":     i.interface_name,
                "device":   dev_map.get(i.device_id) and dev_map[i.device_id].hostname or "—",
                "speed":    i.speed,
            }
            for i in all_interfaces if i.status == "down"
        ],
    }

    # ── 4. ALERTS & EVENTS ────────────────────────────────────────────────
    alerts_24h = (
        db.query(Alert)
        .filter(Alert.created_at >= since, Alert.deleted_at.is_(None))
        .all()
    )
    sev_counts: dict[str, int] = {}
    for a in alerts_24h:
        sev_counts[a.severity] = sev_counts.get(a.severity, 0) + 1

    resolved_24h   = sum(1 for a in alerts_24h if a.status == "resolved")
    open_alerts     = sum(1 for a in alerts_24h if a.status in ("open", "acknowledged"))

    # Top devices by alert count
    dev_alert_count: dict[int, int] = {}
    for a in alerts_24h:
        if a.device_id:
            dev_alert_count[a.device_id] = dev_alert_count.get(a.device_id, 0) + 1
    top_alert_devices = sorted(dev_alert_count.items(), key=lambda x: x[1], reverse=True)[:5]

    events_24h = (
        db.query(Event)
        .filter(Event.timestamp >= since, Event.deleted_at.is_(None))
        .all()
    )
    event_type_counts: dict[str, int] = {}
    for e in events_24h:
        event_type_counts[e.event_type] = event_type_counts.get(e.event_type, 0) + 1

    alerts_section = {
        "total_alerts_24h":  len(alerts_24h),
        "by_severity":       sev_counts,
        "resolved":          resolved_24h,
        "open":              open_alerts,
        "critical":          sev_counts.get("critical", 0),
        "high":              sev_counts.get("high", 0),
        "warning":           sev_counts.get("warning", 0),
        "info":              sev_counts.get("info", 0),
        "top_alert_devices": [
            {
                "device_id": did,
                "hostname":  dev_map[did].hostname if did in dev_map else f"Device-{did}",
                "ip":        dev_map[did].ip_address if did in dev_map else "—",
                "count":     cnt,
            }
            for did, cnt in top_alert_devices
        ],
        "recent_alerts": [
            {
                "id":          a.id,
                "severity":    a.severity,
                "title":       a.title,
                "description": a.description,
                "status":      a.status,
                "device_id":   a.device_id,
                "hostname":    dev_map[a.device_id].hostname if a.device_id and a.device_id in dev_map else "—",
                "created_at":  a.created_at.isoformat() if a.created_at else None,
            }
            for a in sorted(alerts_24h, key=lambda x: x.created_at or datetime.min, reverse=True)[:20]
        ],
        "total_events_24h":  len(events_24h),
        "event_types":       event_type_counts,
    }

    # ── 5. INCIDENTS & STATUS HISTORY ─────────────────────────────────────
    status_changes_24h = (
        db.query(DeviceStatusHistory)
        .filter(DeviceStatusHistory.timestamp >= since)
        .order_by(DeviceStatusHistory.timestamp.desc())
        .all()
    )
    incidents_section = {
        "total_status_changes": len(status_changes_24h),
        "went_offline":  sum(1 for s in status_changes_24h if s.new_status == "offline"),
        "came_online":   sum(1 for s in status_changes_24h if s.new_status == "online"),
        "changes": [
            {
                "device_id":  s.device_id,
                "hostname":   dev_map[s.device_id].hostname if s.device_id in dev_map else "—",
                "ip":         dev_map[s.device_id].ip_address if s.device_id in dev_map else "—",
                "old_status": s.old_status,
                "new_status": s.new_status,
                "reason":     s.change_reason,
                "timestamp":  s.timestamp.isoformat() if s.timestamp else None,
            }
            for s in status_changes_24h[:30]
        ],
    }

    # ── 6. TOP / BOTTOM PERFORMERS ────────────────────────────────────────
    top_performers = {
        "top_cpu":     _top_devices(device_cpu),
        "top_memory":  _top_devices(device_mem),
        "top_latency": _top_devices(device_latency),
        "max_downtime": sorted(
            [
                {
                    "device_id":    d.id,
                    "hostname":     d.hostname,
                    "ip":           d.ip_address,
                    "status":       d.status,
                    "downtime_sec": d.downtime_seconds,
                }
                for d in all_devices if d.downtime_seconds > 0
            ],
            key=lambda x: x["downtime_sec"],
            reverse=True,
        )[:5],
        "max_alerts": [
            {
                "device_id": did,
                "hostname":  dev_map[did].hostname if did in dev_map else f"Device-{did}",
                "ip":        dev_map[did].ip_address if did in dev_map else "—",
                "alerts":    cnt,
            }
            for did, cnt in top_alert_devices
        ],
    }

    # ── 7. DAILY SUMMARY ──────────────────────────────────────────────────
    issues = []
    if offline_devices > 0:
        issues.append(f"{offline_devices} device(s) currently offline")
    if sev_counts.get("critical", 0) > 0:
        issues.append(f"{sev_counts['critical']} critical alert(s) generated")
    if if_down > 0:
        issues.append(f"{if_down} interface(s) currently down")
    if len(error_ifaces) > 0:
        issues.append(f"{len(error_ifaces)} interface(s) with packet errors")
    if open_alerts > 0:
        issues.append(f"{open_alerts} alert(s) remain unresolved")

    health_score = round(
        (avail_pct * 0.4)
        + (max(0, 100 - sev_counts.get("critical", 0) * 20) * 0.3)
        + (round(if_up / if_total * 100, 1) if if_total else 100) * 0.3,
        1,
    )
    overall_health = "GOOD" if health_score >= 80 else "WARNING" if health_score >= 60 else "CRITICAL"

    daily_summary = {
        "overall_health":   overall_health,
        "health_score":     health_score,
        "availability_pct": avail_pct,
        "issues":           issues if issues else ["No major issues observed"],
        "devices_needing_attention": [
            {"device_id": d.id, "hostname": d.hostname, "ip": d.ip_address, "status": d.status, "reason": "Currently offline"}
            for d in all_devices if d.status == "offline"
        ] + [
            {"device_id": d["device_id"], "hostname": d["hostname"], "ip": d["ip"], "status": "online", "reason": f"Generated {dev_alert_count.get(d['device_id'], 0)} alert(s)"}
            for d in top_performers["max_alerts"][:3]
        ],
    }

    # ── 8. RECOMMENDATIONS ────────────────────────────────────────────────
    recs = []
    if offline_devices > 0:
        names = [d["hostname"] for d in downtime_detail[:3]]
        recs.append({"priority": "CRITICAL", "message": f"Investigate offline device(s): {', '.join(names)}. Check power, connectivity, and SNMP credentials."})
    if sev_counts.get("critical", 0) > 0:
        recs.append({"priority": "CRITICAL", "message": f"{sev_counts['critical']} critical alert(s) unresolved. Immediate action required."})
    if open_alerts > 0:
        recs.append({"priority": "HIGH", "message": f"{open_alerts} open alert(s) need review and resolution."})
    if len(error_ifaces) > 0:
        names = [i.interface_name for i in error_ifaces[:3]]
        recs.append({"priority": "HIGH", "message": f"Interfaces with errors: {', '.join(names)}. Review cable/SFP health and switch logs."})
    if if_down > 0:
        recs.append({"priority": "HIGH", "message": f"{if_down} interface(s) are administratively or operationally down. Verify if intentional."})
    avg_cpu = _avg(cpu_values)
    if avg_cpu and avg_cpu > 70:
        recs.append({"priority": "WARNING", "message": f"Average CPU utilization is {avg_cpu}% — consider load balancing or hardware upgrade."})
    avg_mem = _avg(mem_values)
    if avg_mem and avg_mem > 80:
        recs.append({"priority": "WARNING", "message": f"Average memory utilization is {avg_mem}% — monitor for memory exhaustion."})
    if not recs:
        recs.append({"priority": "INFO", "message": "Network is operating within normal parameters. Continue routine monitoring."})

    return {
        "report_date":          report_date,
        "period":               period_label,
        "generated_at":         now.isoformat(),
        "availability":         availability_section,
        "performance":          performance_section,
        "interfaces":           interfaces_section,
        "alerts":               alerts_section,
        "incidents":            incidents_section,
        "top_performers":       top_performers,
        "daily_summary":        daily_summary,
        "recommendations":      recs,
    }
