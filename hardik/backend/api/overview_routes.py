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
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Overview & Service Control"])


# ---------------------------------------------------------------------------
# Single overview endpoint — ONE DB round-trip for the entire Dashboard
# ---------------------------------------------------------------------------

@router.get("/overview")
def get_overview(
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

    since_24h = datetime.utcnow() - timedelta(hours=24)

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
    iface_counts_raw = (
        db.query(Interface.device_id, func.count(Interface.id).label("total"),
                 func.sum(
                     func.cast(Interface.status == "up", db.bind.dialect.name == "postgresql" and "int" or "integer")
                 ).label("up"))
        .group_by(Interface.device_id)
        .all()
    )
    # Simpler approach — just count total; up-count via Python
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

    # ── background service status ──────────────────────────────────────────
    services = _get_service_states()

    return {
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
        "services": services,
        "fetched_at": datetime.utcnow().isoformat(),
    }


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
