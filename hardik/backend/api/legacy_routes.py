"""Legacy router — exposes the old Flask URL prefixes so that existing
callers (``/api/inventory``, ``/api/discovery/modules``,
``/api/discovery/summary``) keep working without code changes.

Register in ``backend/main.py`` as::

    from backend.api.legacy_routes import router as legacy_router
    app.include_router(legacy_router)  # no extra prefix
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Legacy (backward-compatible)"])

# Path to the backend-owned discovery service inventory file.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_MODULES = [
    "01_ip_discovery",
    "02_icmp_discovery",
    "03_tcp_discovery",
    "04_arp_discovery",
    "05_dns_discovery",
    "06_http_discovery",
    "07_snmp_discovery",
    "08_ssh_discovery",
    "09_wmi_discovery",
    "10_device_profiler",
    "11_icmp_monitor",
    "12_snmp_monitor",
    "13_syslog_collector",
    "14_trap_receiver",
    "15_alert_engine",
    "16_event_engine",
    "17_topology_engine",
]


def _load_inventory() -> dict:
    from config import JSON_FILE  # type: ignore  (resolved from hardik root)

    path = _BACKEND_ROOT / JSON_FILE
    if not path.exists():
        return {"devices": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@router.get("/api/inventory")
def legacy_inventory():
    return JSONResponse(_load_inventory())


@router.get("/api/discovery/modules")
def legacy_modules():
    return JSONResponse({"modules": _MODULES})


@router.get("/api/discovery/summary")
def legacy_summary():
    from monitoring_services import MonitoringServices  # type: ignore

    payload = _load_inventory()
    devices = payload.get("devices", [])
    summary = MonitoringServices().summarize(devices)
    return JSONResponse({**summary, "device_count": len(devices)})
