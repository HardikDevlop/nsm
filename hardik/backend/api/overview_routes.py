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
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Overview & Service Control"])
_OVERVIEW_CACHE_TTL_SECONDS = 10
_overview_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_overview_cache_lock = Lock()


# ---------------------------------------------------------------------------
# Single overview endpoint — ONE DB round-trip for the entire Dashboard
# ---------------------------------------------------------------------------

@router.get("/overview")
def get_overview(
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("dashboard:read")),
) -> dict[str, Any]:
    """
    Return everything the Dashboard needs in a single call.
    All data comes from PostgreSQL — no live SNMP, no ping.
    Frontend caches this and never calls individual list endpoints.
    """
    from backend.models import (  # noqa: PLC0415
        Alert, Device, DeviceMetric, DeviceType, Event, Interface,
        Vendor, DeviceCredential,
    )
    from backend.models.snmp import (  # noqa: PLC0415
        LatestCPU, LatestMemory, LatestStorage, LatestInterface,
        LatestEnvironment, InterfaceStatistic, PollingHistory,
        MonitoringConfig, OIDCache, LLDPNeighbor, VLANInformation,
        RoutingEntry,
    )

    now_ts = datetime.utcnow().timestamp()
    with _overview_cache_lock:
        cached = _overview_cache.get(hours)
        if cached and now_ts - cached[0] < _OVERVIEW_CACHE_TTL_SECONDS:
            return cached[1]

    since_24h = datetime.utcnow() - timedelta(hours=hours)

    # ── devices (with vendor and type joined) ──────────────────────────────
    device_rows = (
        db.query(Device)
        .filter(Device.deleted_at.is_(None))
        .order_by(Device.hostname)
        .all()
    )

    # ── latest metric per device (one query) ──────────────────────────────
    from sqlalchemy import func  # noqa: PLC0415
    from sqlalchemy.orm import aliased  # noqa: PLC0415

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
        .join(sub, DeviceMetric.id == sub.c.max_id)
        .all()
    )
    metric_by_device: dict[int, DeviceMetric] = {m.device_id: m for m in latest_metrics_raw}

    # ── interface counts per device ────────────────────────────────────────
    # Keep this query simple and portable. The previous cast-based aggregate
    # broke on SQLite/PostgreSQL type handling and was unused anyway.
    iface_raw2 = db.query(Interface.device_id, Interface.status).all()
    iface_total: dict[int, int] = {}
    iface_up: dict[int, int] = {}
    for row in iface_raw2:
        iface_total[row.device_id] = iface_total.get(row.device_id, 0) + 1
        if row.status == "up":
            iface_up[row.device_id] = iface_up.get(row.device_id, 0) + 1

    # ── vendor lookup ──────────────────────────────────────────────────────
    vendors = {v.id: v.vendor_name for v in db.query(Vendor).all()}
    dtypes  = {t.id: t.name for t in db.query(DeviceType).all()}

    # ── SNMP credential versions ───────────────────────────────────────────
    cred_versions: dict[int, str] = {
        c.device_id: c.snmp_version or ""
        for c in db.query(DeviceCredential.device_id, DeviceCredential.snmp_version).all()
    }

    # ── build device list ──────────────────────────────────────────────────
    devices_out: list[dict[str, Any]] = []
    total = online = offline = 0
    for dev in device_rows:
        total += 1
        if dev.status == "online":   online  += 1
        elif dev.status == "offline": offline += 1

        met = metric_by_device.get(dev.id)
        devices_out.append({
            "id":               dev.id,
            "hostname":         dev.hostname,
            "ip_address":       dev.ip_address,
            "mac_address":      dev.mac_address,
            "status":           dev.status,
            "monitoring_status": dev.monitoring_status,
            "vendor":           vendors.get(dev.vendor_id or 0),
            "device_type":      dtypes.get(dev.device_type_id or 0),
            "model":            dev.model,
            "serial_number":    dev.serial_number,
            "firmware_version": dev.firmware_version,
            "uptime_seconds":   dev.uptime_seconds,
            "last_seen":        dev.last_seen.isoformat() if dev.last_seen else None,
            "created_at":       dev.created_at.isoformat() if dev.created_at else None,
            "site_id":          dev.site_id,
            "snmp_version":     cred_versions.get(dev.id),
            "interface_count":  iface_total.get(dev.id, 0),
            "interfaces_up":    iface_up.get(dev.id, 0),
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
        .filter(Alert.status.in_(["open", "acknowledged"]), Alert.deleted_at.is_(None))
        .order_by(Alert.created_at.desc())
        .limit(50)
        .all()
    )
    active_alerts   = len(alert_rows)
    critical_alerts = sum(1 for a in alert_rows if a.severity == "critical")

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
    latest_cpu = {row.device_id: row for row in db.query(LatestCPU).all()}
    latest_memory = {row.device_id: row for row in db.query(LatestMemory).all()}
    latest_storage = db.query(LatestStorage).all()
    latest_interfaces = db.query(LatestInterface).all()
    latest_environment = db.query(LatestEnvironment).all()
    interface_stats = db.query(InterfaceStatistic).filter(InterfaceStatistic.created_at >= since_24h).order_by(InterfaceStatistic.created_at.asc()).all()
    polling_rows = db.query(PollingHistory).filter(PollingHistory.created_at >= since_24h).order_by(PollingHistory.created_at.desc()).all()
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
    interface_rows = [{
        "device_id": row.device_id,
        "device_name": device_by_id.get(row.device_id).hostname if device_by_id.get(row.device_id) else None,
        "interface_id": row.interface_id, "name": row.name,
        "oper_status": row.oper_status, "admin_status": row.admin_status,
        "speed_bps": row.speed_bps, "rx_mbps": row.rx_mbps, "tx_mbps": row.tx_mbps,
        "errors": row.errors, "discards": row.discards,
        "rx_packets": row.rx_packets, "tx_packets": row.tx_packets,
        "utilization_percent": row.utilization_percent,
        "polled_at": row.polled_at.isoformat() if row.polled_at else None,
    } for row in latest_interfaces]
    latest_poll_by_device: dict[int, dict[str, Any]] = {}
    for row in polling_rows:
        latest_poll_by_device.setdefault(row.device_id, {
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "status": row.status, "collector": row.collector, "error": row.error,
        })
    top_devices: dict[int, dict[str, Any]] = {}
    for row in interface_rows:
        item = top_devices.setdefault(row["device_id"], {
            "device_id": row["device_id"], "device_name": row["device_name"], "rx_mbps": 0, "tx_mbps": 0,
        })
        item["rx_mbps"] += row["rx_mbps"] or 0
        item["tx_mbps"] += row["tx_mbps"] or 0
    alert_counts = {severity: sum(1 for alert in alert_rows if alert.severity == severity) for severity in ("critical", "high", "medium", "low", "warning", "info")}
    type_counts: dict[str, int] = {}
    for device in device_rows:
        type_name = dtypes.get(device.device_type_id or 0) or "Other"
        type_counts[type_name] = type_counts.get(type_name, 0) + 1
    normalized = {
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
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "device_id": row.device_id, "rx_mbps": row.rx_mbps, "tx_mbps": row.tx_mbps,
            "utilization_percent": row.utilization_percent,
        } for row in interface_stats],
        "traffic": {
            "rx_mbps": sum(row["rx_mbps"] or 0 for row in interface_rows),
            "tx_mbps": sum(row["tx_mbps"] or 0 for row in interface_rows),
            "top_devices": sorted(top_devices.values(), key=lambda item: item["rx_mbps"] + item["tx_mbps"], reverse=True)[:8],
            "top_interfaces": sorted(interface_rows, key=lambda item: (item["rx_mbps"] or 0) + (item["tx_mbps"] or 0), reverse=True)[:8],
        },
        "polling": {
            "success": sum(1 for row in polling_rows if row.status == "success"),
            "failure": sum(1 for row in polling_rows if row.status != "success"),
            "last_success": next((row.created_at.isoformat() for row in polling_rows if row.status == "success" and row.created_at), None),
            "last_failure": next((row.created_at.isoformat() for row in polling_rows if row.status != "success" and row.created_at), None),
            "active_jobs": db.query(MonitoringConfig).filter(MonitoringConfig.enabled.is_(True)).count(),
            "collector_failures": sum(1 for row in polling_rows if row.status not in ("success", "no_data")),
            "unsupported_oids": db.query(OIDCache).filter(OIDCache.supported.is_(False)).count(),
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
            "lldp_neighbors": db.query(LLDPNeighbor).count(),
            "vlan_count": db.query(VLANInformation).count(),
            "routing_entries": db.query(RoutingEntry).count(),
            "arp_entries": None, "mac_entries": None, "topology_nodes": len(device_rows),
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
            "active_alerts":    active_alerts,
            "critical_alerts":  critical_alerts,
            "recent_events":    len(event_rows),
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


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_service_states(request: Request | None = None) -> dict[str, Any]:
    """Inspect every background service and return its current state."""
    # SNMP polling
    snmp_running = False
    snmp_jobs    = 0
    try:
        if request is not None:
            polling = getattr(request.app.state, "snmp_polling", None)
            if polling is not None and polling.scheduler is not None:
                snmp_running = polling.scheduler.running
                snmp_jobs    = len(polling.scheduler.get_jobs())
        else:
            # Called from overview (no request ref) — try importing app
            from backend.main import app  # noqa: PLC0415
            polling = getattr(app.state, "snmp_polling", None)
            if polling is not None and polling.scheduler is not None:
                snmp_running = polling.scheduler.running
                snmp_jobs    = len(polling.scheduler.get_jobs())
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
