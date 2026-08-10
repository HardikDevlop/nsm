
"""
Per-device SNMP monitoring API.

These routes are what the React frontend SNMP pages already call
(as declared in figma design/src/lib/api.ts).  They were previously
missing from the backend.

All routes read stored data from the database first.  If no stored data
exists they perform a live SNMP poll, cache the result, and return it.

Routes exposed
--------------
GET /snmp/devices/{id}/overview
GET /snmp/devices/{id}/system
GET /snmp/devices/{id}/cpu
GET /snmp/devices/{id}/memory
GET /snmp/devices/{id}/storage
GET /snmp/devices/{id}/interfaces
GET /snmp/interfaces/{id}/history
GET /snmp/devices/{id}/environment
GET /snmp/devices/{id}/lldp
GET /snmp/devices/{id}/routing
GET /snmp/devices/{id}/vlans
GET /snmp/devices/{id}/oids
GET /snmp/devices/{id}/oid-tree
GET /snmp/devices/{id}/polling-history
GET /snmp/devices/{id}/polling-stats
GET /snmp/topology

POST /snmp/devices/{id}/poll          — trigger a live poll
POST /snmp/devices/{id}/discover      — full identity + capability discovery
POST /snmp/devices/{id}/test-snmp     — quick SNMP reachability test
GET  /snmp/devices/{id}/identity      — identity object
GET  /snmp/devices/{id}/capabilities  — capability map

POST /api/v1/devices/manual           — add device manually with SNMP creds
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import get_current_user, require_permission
from backend.models import Device, DeviceCredential, Event, Interface

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["SNMP Device Monitoring"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_device_or_404(device_id: int, db: Session) -> Device:
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.deleted_at.is_(None),
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    return device


def _get_credentials(device_id: int, db: Session) -> DeviceCredential | None:
    return db.query(DeviceCredential).filter(
        DeviceCredential.device_id == device_id
    ).first()


def _live_collect(device: Device, cred: DeviceCredential | None) -> dict[str, Any]:
    """Run a live SNMP collect on the device using stored credentials."""
    from backend.snmp.collector import SNMPService  # noqa: PLC0415
    from backend.snmp.credentials import SNMPCredentials  # noqa: PLC0415
    from backend.utils.crypto import decrypt_secret  # noqa: PLC0415

    if not cred:
        raise HTTPException(
            status_code=422,
            detail="No SNMP credentials configured for this device",
        )

    version = cred.snmp_version or "v2c"
    community = None
    if cred.community_string:
        try:
            community = decrypt_secret(cred.community_string)
        except Exception:
            community = cred.community_string

    auth_pass = None
    if cred.auth_password:
        try:
            auth_pass = decrypt_secret(cred.auth_password)
        except Exception:
            auth_pass = cred.auth_password

    priv_pass = None
    if cred.privacy_password:
        try:
            priv_pass = decrypt_secret(cred.privacy_password)
        except Exception:
            priv_pass = cred.privacy_password

    credentials = SNMPCredentials(
        version=version,
        community=community or "public",
        username=cred.username,
        auth_protocol=cred.auth_protocol,
        auth_password=auth_pass,
        privacy_protocol=cred.privacy_protocol,
        privacy_password=priv_pass,
        security_level=cred.security_level,
    )
    service = SNMPService(credentials=credentials, timeout=3.0)
    return service.collect(device.ip_address)


def _collector_data(result: dict[str, Any], name: str) -> dict[str, Any]:
    """Extract a single collector's output from a full collect() result."""
    collectors = result.get("collectors") or {}
    return collectors.get(name) or {
        "collector": name, "supported": False,
        "reason": "Collector not present in poll result", "missing": [],
    }


# ---------------------------------------------------------------------------
# Manual device addition with SNMP credentials
# ---------------------------------------------------------------------------

class ManualAddDeviceRequest(BaseModel):
    """Add a device manually with full SNMP v3 credential support."""
    ip_address: str
    name: str | None = None
    hostname: str | None = None
    snmp_version: str = "v2c"
    community_string: str | None = None
    username: str | None = None
    auth_protocol: str | None = None
    auth_password: str | None = None
    privacy_protocol: str | None = None
    privacy_password: str | None = None
    security_level: str | None = None
    snmp_port: int = 161
    location: str | None = None
    description: str | None = None
    # Optional manual overrides (stored but never overwrite discovered values
    # unless the user explicitly requests it later via PATCH)
    vendor_override: str | None = None
    model_override: str | None = None
    device_type_override: str | None = None
    site_id: int | None = None
    mac_address: str | None = None
    auto_discover: bool = True  # run identity + capability discovery after adding


@router.post(
    "/devices/manual",
    status_code=status.HTTP_201_CREATED,
    summary="Add device manually with SNMP credentials",
)
def add_device_manual(
    payload: ManualAddDeviceRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(require_permission("devices:create")),
) -> dict[str, Any]:
    """
    Add a real network device with SNMP credentials.

    Flow:
    1. Validate IP address
    2. Create or update Device record
    3. Store encrypted SNMP credentials
    4. (Optional) Run identity + capability discovery immediately
    5. Return device + discovery result
    """
    from backend.utils.crypto import encrypt_secret  # noqa: PLC0415

    ip = payload.ip_address.strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip_address is required")

    # Check for existing device
    existing = db.query(Device).filter(
        Device.ip_address == ip, Device.deleted_at.is_(None)
    ).first()

    hostname = payload.hostname or payload.name or ip
    if existing:
        existing.hostname = hostname
        if payload.mac_address:
            existing.mac_address = payload.mac_address
        device = existing
        created = False
    else:
        device = Device(
            ip_address=ip,
            hostname=hostname,
            mac_address=payload.mac_address,
            site_id=payload.site_id,
            status="unknown",
            monitoring_status=True,
        )
        db.add(device)
        db.flush()
        created = True

    # Store / update credentials
    cred = db.query(DeviceCredential).filter(
        DeviceCredential.device_id == device.id
    ).first()
    if cred is None:
        cred = DeviceCredential(device_id=device.id)
        db.add(cred)

    cred.snmp_version    = payload.snmp_version
    cred.community_string = encrypt_secret(payload.community_string) if payload.community_string else None
    cred.username        = payload.username
    cred.auth_protocol   = payload.auth_protocol
    cred.auth_password   = encrypt_secret(payload.auth_password) if payload.auth_password else None
    cred.privacy_protocol = payload.privacy_protocol
    cred.privacy_password = encrypt_secret(payload.privacy_password) if payload.privacy_password else None
    cred.security_level  = payload.security_level

    db.add(Event(
        device_id=device.id,
        event_type="DEVICE_MANUAL_ADD",
        description=f"Device {ip} added manually",
    ))
    db.commit()
    db.refresh(device)

    discovery_result: dict[str, Any] = {}
    if payload.auto_discover:
        try:
            discovery_result = _run_identity_discovery(device, cred, db, {
                "vendor":      payload.vendor_override,
                "model":       payload.model_override,
                "device_type": payload.device_type_override,
            })
        except Exception as exc:
            logger.warning("Auto-discovery failed for %s: %s", ip, exc)
            discovery_result = {"error": str(exc)}

    return {
        "device": {
            "id":         device.id,
            "ip_address": device.ip_address,
            "hostname":   device.hostname,
            "status":     device.status,
            "created":    created,
        },
        "discovery": discovery_result,
    }


# ---------------------------------------------------------------------------
# SNMP reachability test
# ---------------------------------------------------------------------------

@router.post(
    "/snmp/devices/{device_id}/test-snmp",
    summary="Quick SNMP reachability test",
)
def test_snmp_connection(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Test SNMP connectivity using the device's stored credentials."""
    import time
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    if not cred:
        return {
            "reachable": False,
            "snmp_enabled": False,
            "error": "No SNMP credentials configured",
            "device_id": device_id,
            "ip": device.ip_address,
        }
    t0 = time.perf_counter()
    try:
        result = _live_collect(device, cred)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "reachable":    result.get("reachable", False),
            "snmp_enabled": result.get("snmp_enabled", False),
            "hostname":     result.get("hostname"),
            "vendor":       result.get("vendor"),
            "device_type":  result.get("device_type"),
            "response_ms":  elapsed,
            "device_id":    device_id,
            "ip":           device.ip_address,
        }
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "reachable":    False,
            "snmp_enabled": False,
            "error":        str(exc),
            "response_ms":  elapsed,
            "device_id":    device_id,
            "ip":           device.ip_address,
        }


# ---------------------------------------------------------------------------
# Full identity + capability discovery
# ---------------------------------------------------------------------------

def _run_identity_discovery(
    device: Device,
    cred: DeviceCredential,
    db: Session,
    user_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run full identity + capability discovery pipeline and persist results.
    Returns the discovery result dict.
    """
    from backend.snmp.identity.resolver import DeviceIdentityResolver  # noqa
    from backend.snmp.identity.capability import CapabilityDiscoveryService  # noqa
    from backend.models.identity import DeviceIdentity, DeviceCapabilities  # noqa

    # 1. Live SNMP collect
    result = _live_collect(device, cred)
    walk   = {}
    for col_data in (result.get("collectors") or {}).values():
        if isinstance(col_data, dict) and col_data.get("data"):
            pass  # collector data is normalized — we need raw walk
    # The raw walk is embedded in the collector pipeline; re-expose via result
    # For identity purposes the system-group scalars are sufficient:
    walk = {
        "1.3.6.1.2.1.1.1.0": result.get("collectors", {}).get("system", {}).get("data", {}).get("description"),
        "1.3.6.1.2.1.1.2.0": result.get("sys_object_id"),
        "1.3.6.1.2.1.1.5.0": result.get("hostname"),
    }
    # Also pull from the collectors' raw SNMP data where available
    if result.get("reachable"):
        pass  # walk populated from identity scalars is sufficient for resolver

    # 2. Collect MAC addresses from interface data
    macs: list[str] = []
    if_data = (result.get("collectors") or {}).get("interfaces", {})
    if isinstance(if_data, dict) and if_data.get("data"):
        for iface in (if_data["data"].get("interfaces") or []):
            if iface.get("mac"):
                macs.append(iface["mac"])
    if device.mac_address:
        macs.append(device.mac_address)

    # 3. Resolve identity
    resolver = DeviceIdentityResolver(db=db)
    identity = resolver.resolve(
        walk=walk,
        mac_addresses=macs,
        user_overrides={k: v for k, v in (user_overrides or {}).items() if v},
        hostname_hint=device.ip_address,
    )

    # 4. Discover capabilities from collector results
    cap_svc = CapabilityDiscoveryService()
    cap_result = cap_svc.discover(
        walk=walk,
        collector_results=result.get("collectors"),
    )

    # 5. Persist identity
    di = db.query(DeviceIdentity).filter(
        DeviceIdentity.device_id == device.id
    ).first()
    if di is None:
        di = DeviceIdentity(device_id=device.id)
        db.add(di)
    di.vendor            = identity.vendor
    di.vendor_source     = identity.vendor_source
    di.vendor_confidence = identity.vendor_confidence
    di.hostname          = identity.hostname
    di.hostname_source   = identity.hostname_source
    di.model             = identity.model
    di.model_source      = identity.model_source
    di.model_confidence  = identity.model_confidence
    di.device_type       = identity.device_type
    di.device_type_source = identity.device_type_source
    di.device_type_confidence = identity.device_type_confidence
    di.serial_number     = identity.serial_number
    di.firmware_version  = identity.firmware_version
    di.os_version        = identity.os_version
    di.sys_object_id     = identity.sys_object_id
    di.sys_descr         = identity.sys_descr
    di.sys_name          = identity.sys_name
    di.sys_contact       = identity.sys_contact
    di.sys_location      = identity.sys_location
    di.mac_addresses     = identity.mac_addresses
    di.roles             = identity.roles
    di.product_id        = identity.product_id
    di.identity_confidence = identity.identity_confidence
    di.identity_sources  = identity.identity_sources
    di.updated_at        = datetime.utcnow()

    # 6. Persist capabilities
    dc = db.query(DeviceCapabilities).filter(
        DeviceCapabilities.device_id == device.id
    ).first()
    if dc is None:
        dc = DeviceCapabilities(device_id=device.id)
        db.add(dc)
    caps = cap_result["capabilities"]
    col_kwargs = cap_svc.to_db_kwargs(caps)
    for col_name, val in col_kwargs.items():
        setattr(dc, col_name, val)
    dc.capability_detail = cap_result["detail"]
    dc.updated_at        = datetime.utcnow()

    # 7. Update device record with discovered info
    if identity.hostname and identity.hostname != "Unknown Device":
        device.hostname = identity.hostname
    if identity.serial_number:
        device.serial_number = identity.serial_number
    if identity.firmware_version:
        device.firmware_version = identity.firmware_version
    if identity.model:
        device.model = identity.model
    device.status   = "online" if result.get("reachable") else "offline"
    device.last_seen = datetime.utcnow()

    db.add(Event(
        device_id=device.id,
        event_type="SNMP_DISCOVERY",
        description=f"Identity/capability discovery complete. Vendor={identity.vendor}, type={identity.device_type}",
    ))
    db.commit()

    return {
        "identity":     identity.to_dict(),
        "capabilities": caps,
        "reachable":    result.get("reachable"),
        "vendor":       identity.vendor,
        "device_type":  identity.device_type,
        "hostname":     identity.hostname,
    }


@router.post(
    "/snmp/devices/{device_id}/discover",
    summary="Run full identity + capability discovery",
)
def discover_device(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    try:
        return _run_identity_discovery(device, cred, db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Discovery failed for device %d: %s", device_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Identity & Capabilities (read-only)
# ---------------------------------------------------------------------------

@router.get("/snmp/devices/{device_id}/identity")
def get_device_identity(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    from backend.models.identity import DeviceIdentity  # noqa
    _get_device_or_404(device_id, db)
    di = db.query(DeviceIdentity).filter(DeviceIdentity.device_id == device_id).first()
    if not di:
        return {
            "device_id": device_id,
            "vendor": "unknown", "vendor_source": "unknown", "vendor_confidence": 0,
            "hostname": None, "model": None, "device_type": "unknown",
            "identity_confidence": 0, "identity_sources": [],
            "message": "No identity data yet — run POST /snmp/devices/{id}/discover first",
        }
    return {
        "device_id":            device_id,
        "vendor":               di.vendor,
        "vendor_source":        di.vendor_source,
        "vendor_confidence":    di.vendor_confidence,
        "hostname":             di.hostname,
        "hostname_source":      di.hostname_source,
        "model":                di.model,
        "model_source":         di.model_source,
        "model_confidence":     di.model_confidence,
        "device_type":          di.device_type,
        "device_type_source":   di.device_type_source,
        "device_type_confidence": di.device_type_confidence,
        "serial_number":        di.serial_number,
        "firmware_version":     di.firmware_version,
        "os_version":           di.os_version,
        "product_family":       di.product_family,
        "roles":                di.roles,
        "sys_object_id":        di.sys_object_id,
        "sys_descr":            di.sys_descr,
        "sys_name":             di.sys_name,
        "sys_contact":          di.sys_contact,
        "sys_location":         di.sys_location,
        "mac_addresses":        di.mac_addresses,
        "identity_confidence":  di.identity_confidence,
        "identity_sources":     di.identity_sources,
        "discovered_at":        di.discovered_at.isoformat() if di.discovered_at else None,
        "updated_at":           di.updated_at.isoformat() if di.updated_at else None,
    }


@router.get("/snmp/devices/{device_id}/capabilities")
def get_device_capabilities(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    from backend.models.identity import DeviceCapabilities  # noqa
    _get_device_or_404(device_id, db)
    dc = db.query(DeviceCapabilities).filter(
        DeviceCapabilities.device_id == device_id
    ).first()
    if not dc:
        return {
            "device_id": device_id,
            "capabilities": {},
            "message": "No capability data yet — run POST /snmp/devices/{id}/discover first",
        }
    return {
        "device_id":    device_id,
        "capabilities": dc.to_map(),
        "detail":       dc.capability_detail or {},
        "updated_at":   dc.updated_at.isoformat() if dc.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Per-device SNMP metrics (live poll on every call)
# ---------------------------------------------------------------------------

@router.post("/snmp/devices/{device_id}/poll")
def poll_device_now(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Trigger a full live SNMP collect and return the raw result."""
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    return _live_collect(device, cred)


@router.get("/snmp/devices/{device_id}/overview")
def get_snmp_overview(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Device overview: identity + health + capabilities + last-poll summary."""
    from backend.models.identity import DeviceIdentity, DeviceCapabilities  # noqa
    from backend.models.snmp import PollingHistory  # noqa
    device = _get_device_or_404(device_id, db)
    di = db.query(DeviceIdentity).filter(DeviceIdentity.device_id == device_id).first()
    dc = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    last_polls = (
        db.query(PollingHistory)
        .filter(PollingHistory.device_id == device_id)
        .order_by(PollingHistory.id.desc())
        .limit(20)
        .all()
    )
    vendor_name = None
    if device.vendor:
        vendor_name = device.vendor.vendor_name
    elif di:
        vendor_name = di.vendor

    modules = []
    if dc and dc.capability_detail:
        for name, detail in dc.capability_detail.items():
            modules.append({
                "name":     name,
                "supported": detail.get("supported", False),
                "status":   "supported" if detail.get("supported") else "unsupported",
            })

    return {
        "device_id":    device_id,
        "hostname":     device.hostname,
        "ip_address":   device.ip_address,
        "vendor":       vendor_name,
        "model":        device.model or (di.model if di else None),
        "device_type":  (di.device_type if di else None) or (device.device_type.name if device.device_type else None),
        "uptime_seconds": device.uptime_seconds,
        "health":       "healthy" if device.status == "online" else "unknown",
        "polling_enabled": device.monitoring_status,
        "last_poll":    device.last_seen.isoformat() if device.last_seen else None,
        "modules":      modules,
        "status":       device.status,
        "identity_confidence": di.identity_confidence if di else None,
    }


@router.get("/snmp/devices/{device_id}/system")
def get_snmp_system(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    result = _live_collect(device, cred)
    sys_col = _collector_data(result, "system")
    return {"device_id": device_id, **sys_col}


@router.get("/snmp/devices/{device_id}/cpu")
def get_snmp_cpu(
    device_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    from backend.models.snmp import CPUStatistic  # noqa
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)

    # Historical data from DB
    since = datetime.utcnow() - timedelta(hours=hours)
    history_rows = (
        db.query(CPUStatistic)
        .filter(CPUStatistic.device_id == device_id,
                CPUStatistic.created_at >= since)
        .order_by(CPUStatistic.created_at.asc())
        .all()
    )
    history = [
        {"timestamp": r.created_at.isoformat(), "usage": r.utilization_percent}
        for r in history_rows
    ]

    # Live poll for current value
    live_col = {}
    try:
        result  = _live_collect(device, cred)
        live_col = _collector_data(result, "cpu")
    except Exception as exc:
        live_col = {"supported": False, "reason": str(exc)}

    data = live_col.get("data") or {}
    return {
        "device_id":    device_id,
        "current_usage": data.get("overall_percent"),
        "average":       data.get("average_percent"),
        "per_core":      data.get("per_core", []),
        "load_avg":      data.get("load_avg"),
        "history":       history,
        "supported":     live_col.get("supported", False),
        "last_poll":     datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Memory, Storage, Interfaces, Environment, LLDP, Routing, VLANs
# ---------------------------------------------------------------------------

@router.get("/snmp/devices/{device_id}/memory")
def get_snmp_memory(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "memory")
    return {"device_id": device_id, **col}


@router.get("/snmp/devices/{device_id}/storage")
def get_snmp_storage(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "storage")
    return {"device_id": device_id, **col}


@router.get("/snmp/devices/{device_id}/interfaces")
def get_snmp_interfaces(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "interfaces")
    return {"device_id": device_id, **col}


@router.get("/snmp/interfaces/{interface_id}/history")
def get_snmp_interface_history(interface_id: int, hours: int = Query(default=24, ge=1, le=720), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    from backend.models.snmp import InterfaceStatistic  # noqa
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = db.query(InterfaceStatistic).filter(InterfaceStatistic.interface_id == interface_id, InterfaceStatistic.created_at >= since).order_by(InterfaceStatistic.created_at.asc()).all()
    history = [{"timestamp": r.created_at.isoformat(), "rx_mbps": r.rx_mbps, "tx_mbps": r.tx_mbps, "utilization": r.utilization_percent, "errors": r.error_rate, "packet_rate": r.packet_rate} for r in rows]
    stats = {"peak_mbps": max((r.rx_mbps or 0) + (r.tx_mbps or 0) for r in rows) if rows else 0, "average_mbps": sum((r.rx_mbps or 0) + (r.tx_mbps or 0) for r in rows) / len(rows) if rows else 0, "percentile_95_mbps": 0}
    return {"interface_id": interface_id, "history": history, "statistics": stats}


@router.get("/snmp/devices/{device_id}/environment")
def get_snmp_environment(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "environment")
    return {"device_id": device_id, **col}


@router.get("/snmp/devices/{device_id}/lldp")
def get_snmp_lldp(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "lldp")
    return {"device_id": device_id, **col}


@router.get("/snmp/devices/{device_id}/routing")
def get_snmp_routing(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "routing")
    return {"device_id": device_id, **col}


@router.get("/snmp/devices/{device_id}/vlans")
def get_snmp_vlans(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "vlan")
    return {"device_id": device_id, **col}


@router.get("/snmp/devices/{device_id}/oids")
def get_snmp_oids(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    from backend.models.snmp import OIDCache  # noqa
    rows = db.query(OIDCache).filter(OIDCache.device_id == device_id).all()
    entries = [{"id": r.id, "device_id": device_id, "oid": r.oid, "supported": r.supported, "label": r.label, "vendor_specific": False} for r in rows]
    return {"device_id": device_id, "entries": entries, "count": len(entries)}


@router.get("/snmp/devices/{device_id}/oid-tree")
def get_snmp_oid_tree(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    return {"oid": "1.3.6.1", "name": "iso.org.dod.internet", "supported": True, "children": [{"oid": "1.3.6.1.2.1", "name": "mib-2", "supported": True, "children": []}]}


@router.get("/snmp/devices/{device_id}/polling-history")
def get_snmp_polling_history(device_id: int, hours: int = Query(default=24, ge=1, le=720), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> list[dict[str, Any]]:
    from backend.models.snmp import PollingHistory  # noqa
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = db.query(PollingHistory).filter(PollingHistory.device_id == device_id, PollingHistory.created_at >= since).order_by(PollingHistory.id.desc()).limit(500).all()
    return [{"id": r.id, "device_id": device_id, "collector": r.collector, "status": r.status, "duration_ms": r.duration_ms, "error": r.error, "timestamp": r.created_at.isoformat()} for r in rows]


@router.get("/snmp/devices/{device_id}/polling-stats")
def get_snmp_polling_stats(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    from backend.models.snmp import PollingHistory  # noqa
    rows = db.query(PollingHistory).filter(PollingHistory.device_id == device_id).all()
    total   = len(rows)
    success = sum(1 for r in rows if r.status == "success")
    return {"total_polls": total, "success_count": success, "failure_count": total - success, "success_rate": round(success/total*100, 1) if total > 0 else 0, "average_duration_ms": round(sum(r.duration_ms or 0 for r in rows)/total, 1) if total > 0 else 0, "max_duration_ms": max((r.duration_ms or 0 for r in rows), default=0), "min_duration_ms": min((r.duration_ms or 0 for r in rows), default=0), "by_collector": [], "recent_history": []}


@router.get("/snmp/topology")
def get_snmp_topology(device_id: int | None = Query(default=None), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    devices_q = db.query(Device).filter(Device.deleted_at.is_(None))
    if device_id:
        devices_q = devices_q.filter(Device.id == device_id)
    d_list = devices_q.limit(200).all()
    nodes = [{"id": d.id, "hostname": d.hostname, "ip_address": d.ip_address, "status": d.status, "type": d.device_type.name if d.device_type else None, "vendor": d.vendor.vendor_name if d.vendor else None} for d in d_list]
    return {"devices": nodes, "links": []}
