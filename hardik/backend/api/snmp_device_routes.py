
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
from backend.models import Device, DeviceCredential, Event, Interface, Vendor, DeviceType
from backend.models.snmp import LatestInterface, MonitoringStatus

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
    service = SNMPService(credentials=credentials, timeout=10.0, retries=3)
    return service.collect(device.ip_address)


def _collector_data(result: dict[str, Any], name: str) -> dict[str, Any]:
    """Extract a single collector's output from a full collect() result."""
    collectors = result.get("collectors") or {}
    return collectors.get(name) or {
        "collector": name, "supported": False,
        "reason": "Collector not present in poll result", "missing": [],
    }


def _persist_collect_result(device_id: int, result: dict[str, Any], db: Session) -> None:
    """Cache live/discovery collector output into latest tables and capability detail."""
    import asyncio
    from backend.services.snmp_polling import PollJob, SNMPPoller

    collectors = result.get("collectors") or {}
    if not isinstance(collectors, dict):
        return

    from backend.models.identity import DeviceCapabilities
    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    if cap is None:
        cap = DeviceCapabilities(device_id=device_id)
        db.add(cap)
    for name in ("system", "cpu", "memory", "storage", "interfaces", "environment", "inventory", "vlan", "lldp", "cdp", "routing", "arp", "mac_table", "firewall", "wireless", "topology"):
        attr = f"cap_{name}"
        if hasattr(cap, attr):
            setattr(cap, attr, collectors.get(name, {}).get("supported", False))
    cap.capability_detail = collectors
    cap.updated_at = datetime.utcnow()
    db.flush()

    poller = SNMPPoller(db)
    for module, collector in collectors.items():
        if not isinstance(collector, dict):
            continue
        job = PollJob(
            device_id=device_id,
            module_name=module,
            collector_name=module,
            interval_seconds=0,
            config_id=0,
        )
        asyncio.run(poller._persist_results(job, collector.get("data") or {}, collector.get("supported") is True))


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
    import logging
    logger = logging.getLogger(__name__)
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    logger.info(f"Test SNMP for device {device_id}: {device.ip_address}, cred: {cred.username if cred else None}")
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
        logger.info(f"Calling _live_collect for device {device_id}")
        result = _live_collect(device, cred)
        logger.info(f"_live_collect returned: reachable={result.get('reachable')}, snmp_enabled={result.get('snmp_enabled')}")
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
        logger.exception(f"Test SNMP failed for device {device_id}")
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

    _persist_collect_result(device.id, result, db)

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
    result = _live_collect(device, cred)
    _persist_collect_result(device_id, result, db)
    return result


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
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_enabled":  result.get("snmp_enabled"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "sys_object_id": result.get("sys_object_id"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        **_collector_data(result, "system"),
    }


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

    result   = _live_collect(device, cred)
    col      = _collector_data(result, "cpu")
    col_data = col.get("data") or {}

    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "cpu",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "overall_percent":  col_data.get("overall_percent"),
            "average_percent":  col_data.get("average_percent"),
            "per_core":         col_data.get("per_core", []),
            "core_count":       col_data.get("core_count", 0),
            "highest_core":     col_data.get("highest_core"),
            "lowest_core":      col_data.get("lowest_core"),
            "cpu_user":         col_data.get("cpu_user"),
            "cpu_system":       col_data.get("cpu_system"),
            "cpu_idle":         col_data.get("cpu_idle"),
            "load_avg":         col_data.get("load_avg"),
            "display":          col_data.get("display"),
            "source":           col_data.get("source"),
        },
        "history": history,
    }


# ---------------------------------------------------------------------------
# Memory, Storage, Interfaces, Environment, LLDP, Routing, VLANs
# ---------------------------------------------------------------------------

@router.get("/snmp/devices/{device_id}/memory")
def get_snmp_memory(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "memory")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "memory",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "total_bytes":         col_data.get("total_bytes"),
            "used_bytes":          col_data.get("used_bytes"),
            "free_bytes":          col_data.get("free_bytes"),
            "cached_bytes":        col_data.get("cached_bytes"),
            "buffer_bytes":        col_data.get("buffer_bytes"),
            "swap_total_bytes":    col_data.get("swap_total_bytes"),
            "swap_free_bytes":     col_data.get("swap_free_bytes"),
            "utilization_percent": col_data.get("utilization_percent"),
            "display":             col_data.get("display"),
            "source":              col_data.get("source"),
        },
    }


@router.get("/snmp/devices/{device_id}/storage")
def get_snmp_storage(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "storage")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "storage",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "volume_count": col_data.get("volume_count", 0),
            "volumes":      col_data.get("volumes", []),
        },
    }


@router.get("/snmp/devices/{device_id}/interfaces")
def get_snmp_interfaces(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "interfaces")
    col_data = col.get("data") or {}
    live_interfaces = col_data.get("interfaces", [])
    previous_by_index = {
        row.if_index: row
        for row in db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()
        if row.if_index is not None
    }
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    enriched_interfaces = []
    for iface in live_interfaces:
        if not isinstance(iface, dict):
            enriched_interfaces.append(iface)
            continue
        if_index = iface.get("ifIndex") or iface.get("if_index")
        latest = previous_by_index.get(if_index)
        merged = dict(iface)
        in_octets = iface.get("in_octets") or iface.get("rx_octets") or iface.get("hc_in_octets")
        out_octets = iface.get("out_octets") or iface.get("tx_octets") or iface.get("hc_out_octets")
        rx_mbps = iface.get("rx_mbps")
        tx_mbps = iface.get("tx_mbps")

        if latest:
            merged.setdefault("interface_id", latest.interface_id)
            merged.setdefault("rx_octets", in_octets if in_octets is not None else latest.rx_octets)
            merged.setdefault("tx_octets", out_octets if out_octets is not None else latest.tx_octets)
            merged.setdefault("rx_packets", latest.rx_packets)
            merged.setdefault("tx_packets", latest.tx_packets)
            if latest.polled_at and in_octets is not None and latest.rx_octets is not None:
                elapsed = max((now - latest.polled_at).total_seconds(), 0)
                if elapsed > 0:
                    from backend.snmp.statistics_engine import counter_delta
                    rx_mbps = round(counter_delta(float(in_octets), float(latest.rx_octets)) * 8 / elapsed / 1_000_000, 3)
            if latest.polled_at and out_octets is not None and latest.tx_octets is not None:
                elapsed = max((now - latest.polled_at).total_seconds(), 0)
                if elapsed > 0:
                    from backend.snmp.statistics_engine import counter_delta
                    tx_mbps = round(counter_delta(float(out_octets), float(latest.tx_octets)) * 8 / elapsed / 1_000_000, 3)

            speed_bps = iface.get("speed_bps") or latest.speed_bps
            utilization = latest.utilization_percent
            if speed_bps and (rx_mbps is not None or tx_mbps is not None):
                utilization = round(((rx_mbps or 0) + (tx_mbps or 0)) * 1_000_000 / float(speed_bps) * 100, 2)

            merged["rx_mbps"] = rx_mbps
            merged["tx_mbps"] = tx_mbps
            merged["utilization_percent"] = utilization
            merged["errors"] = latest.errors
            merged["discards"] = latest.discards
            merged["polled_at"] = now.isoformat()
        enriched_interfaces.append(merged)

    _persist_collect_result(device_id, result, db)
    db.commit()
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "interfaces",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "interface_count": col_data.get("interface_count", 0),
            "up_count":        col_data.get("up_count", 0),
            "down_count":      col_data.get("down_count", 0),
            "interfaces":      enriched_interfaces,
        },
    }


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
    col      = _collector_data(result, "environment")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "environment",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "temperatures":   col_data.get("temperatures", []),
            "fans":           col_data.get("fans", []),
            "power_supplies": col_data.get("power_supplies", []),
            "voltages":       col_data.get("voltages", []),
            "currents":       col_data.get("currents", []),
            "other_sensors":  col_data.get("other_sensors", []),
            "sensor_count":   col_data.get("sensor_count", 0),
            "alarm_count":    col_data.get("alarm_count", 0),
            "health":         col_data.get("health", "ok"),
        },
    }


@router.get("/snmp/devices/{device_id}/lldp")
def get_snmp_lldp(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "lldp")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "lldp",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "neighbor_count": col_data.get("neighbor_count", 0),
            "neighbors":      col_data.get("neighbors", []),
            "local_ports":    col_data.get("local_ports", {}),
        },
    }


@router.get("/snmp/devices/{device_id}/routing")
def get_snmp_routing(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "routing")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "routing",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "route_count":       col_data.get("route_count", 0),
            "protocol_summary":  col_data.get("protocol_summary", {}),
            "routes":            col_data.get("routes", []),
        },
    }


@router.get("/snmp/devices/{device_id}/vlans")
def get_snmp_vlans(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "vlan")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "vlan",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "vlan_count": col_data.get("vlan_count", 0),
            "vlans":      col_data.get("vlans", []),
        },
    }


@router.get("/snmp/devices/{device_id}/cdp")
def get_snmp_cdp(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "cdp")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "cdp",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "neighbor_count": col_data.get("neighbor_count", 0),
            "neighbors":      col_data.get("neighbors", []),
        },
    }


@router.get("/snmp/devices/{device_id}/arp")
def get_snmp_arp(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "arp")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "arp",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "entry_count": col_data.get("entry_count", 0),
            "entries":     col_data.get("entries", []),
        },
    }


@router.get("/snmp/devices/{device_id}/mac-table")
def get_snmp_mac_table(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "mac_table")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "mac_table",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "entry_count": col_data.get("entry_count", 0),
            "vlan_aware":  col_data.get("vlan_aware", False),
            "entries":     col_data.get("entries", []),
        },
    }


@router.get("/snmp/devices/{device_id}/inventory")
def get_snmp_inventory(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "inventory")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "inventory",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "total_count":   col_data.get("total_count", 0),
            "fru_count":     col_data.get("fru_count", 0),
            "chassis":       col_data.get("chassis"),
            "modules":       col_data.get("modules", []),
            "power_supplies":col_data.get("power_supplies", []),
            "fans":          col_data.get("fans", []),
            "sensors":       col_data.get("sensors", []),
            "ports":         col_data.get("ports", []),
            "cpus":          col_data.get("cpus", []),
            "other":         col_data.get("other", []),
        },
    }


@router.get("/snmp/devices/{device_id}/health")
def get_snmp_health(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "health")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "health",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "status":       col_data.get("status"),
            "reachable":    col_data.get("reachable"),
            "snmp_enabled": col_data.get("snmp_enabled"),
            "alarm_count":  col_data.get("alarm_count", 0),
            "details":      col_data.get("details"),
        },
    }


@router.get("/snmp/devices/{device_id}/firewall")
def get_snmp_firewall(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "firewall")
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "firewall",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data":          col.get("data") or {},
    }


@router.get("/snmp/devices/{device_id}/wireless")
def get_snmp_wireless(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col = _collector_data(result, "wireless")
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "wireless",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data":          col.get("data") or {},
    }


@router.get("/snmp/devices/{device_id}/device-topology")
def get_snmp_device_topology(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db))
    col      = _collector_data(result, "topology")
    col_data = col.get("data") or {}
    return {
        "api_version":   result.get("api_version", "2.0"),
        "ip":            result.get("ip"),
        "reachable":     result.get("reachable"),
        "snmp_version":  result.get("snmp_version"),
        "vendor":        result.get("vendor"),
        "device_type":   result.get("device_type"),
        "hostname":      result.get("hostname"),
        "collection_ms": result.get("collection_ms"),
        "device_id":     device_id,
        "collector":     "topology",
        "supported":     col.get("supported", False),
        "timestamp":     col.get("timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "node_count":    col_data.get("node_count", 0),
            "link_count":    col_data.get("link_count", 0),
            "source":        col_data.get("source"),
            "sources_used":  col_data.get("sources_used", []),
            "nodes":         col_data.get("nodes", []),
            "links":         col_data.get("links", []),
        },
    }


@router.get("/snmp/devices/{device_id}/oids")
def get_snmp_oids(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> list[dict[str, Any]]:
    """Returns OID cache entries as flat list — matches SNMPOIDCacheEntry[] expectation."""
    from backend.models.snmp import OIDCache  # noqa
    rows = db.query(OIDCache).filter(OIDCache.device_id == device_id).all()
    return [{
        "id":             r.id,
        "device_id":      device_id,
        "oid":            r.oid,
        "oid_name":       r.label,
        "value":          None,
        "type":           None,
        "mib":            None,
        "supported":      r.supported,
        "last_seen":      datetime.utcnow().isoformat(),
        "vendor_specific": False,
    } for r in rows]


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


# ---------------------------------------------------------------------------
# Monitoring Configuration CRUD
# ---------------------------------------------------------------------------

class MonitoringConfigRequest(BaseModel):
    module_name: str
    interval_seconds: int = 60


class MonitoringConfigUpdateRequest(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None


@router.get("/snmp/devices/{device_id}/monitoring")
def get_device_monitoring_configs(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> list[dict[str, Any]]:
    """Get all monitoring configurations for a device."""
    from backend.services.snmp_polling import get_polling_scheduler
    import asyncio

    scheduler = asyncio.run(get_polling_scheduler())
    return asyncio.run(scheduler.get_device_jobs(device_id))


@router.post("/snmp/devices/{device_id}/monitoring/{module}/start")
def start_module_monitoring(
    device_id: int,
    module: str,
    payload: MonitoringConfigRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Start monitoring a specific module on a device."""
    from backend.services.snmp_polling import get_polling_scheduler, ALLOWED_INTERVALS
    import asyncio

    if payload.interval_seconds not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Allowed: {ALLOWED_INTERVALS}")

    # Validate module is supported
    from backend.models.identity import DeviceCapabilities
    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    if cap:
        cap_map = cap.to_map()
        if not cap_map.get(module, False):
            raise HTTPException(status_code=400, detail=f"Module {module} not supported by this device")

    scheduler = asyncio.run(get_polling_scheduler())
    config = asyncio.run(scheduler.add_job(device_id, module, payload.interval_seconds))
    return {
        "device_id": config.device_id,
        "module_name": config.module_name,
        "enabled": config.enabled,
        "interval_seconds": config.interval_seconds,
        "status": config.status,
        "message": f"Monitoring started for {module}",
    }


@router.post("/snmp/devices/{device_id}/monitoring/{module}/stop")
def stop_module_monitoring(
    device_id: int,
    module: str,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Stop monitoring a specific module on a device."""
    from backend.services.snmp_polling import get_polling_scheduler
    import asyncio

    scheduler = asyncio.run(get_polling_scheduler())
    stopped = asyncio.run(scheduler.stop_job(device_id, module))
    return {
        "device_id": device_id,
        "module_name": module,
        "stopped": stopped,
        "message": f"Monitoring stopped for {module}" if stopped else f"No monitoring job found for {module}",
    }


@router.put("/snmp/devices/{device_id}/monitoring/{module}")
def update_module_monitoring(
    device_id: int,
    module: str,
    payload: MonitoringConfigUpdateRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Update monitoring configuration (interval, enabled) for a module."""
    from backend.services.snmp_polling import get_polling_scheduler, ALLOWED_INTERVALS
    import asyncio

    if payload.interval_seconds is not None and payload.interval_seconds not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Allowed: {ALLOWED_INTERVALS}")

    scheduler = asyncio.run(get_polling_scheduler())

    if payload.interval_seconds is not None:
        updated = asyncio.run(scheduler.update_job_interval(device_id, module, payload.interval_seconds))
        if not updated:
            raise HTTPException(status_code=404, detail="Monitoring config not found")

    status = asyncio.run(scheduler.get_job_status(device_id, module))
    if not status:
        raise HTTPException(status_code=404, detail="Monitoring config not found")

    # Handle enable/disable
    if payload.enabled is not None:
        if payload.enabled:
            # Start if not running
            if status["status"] != "running":
                asyncio.run(scheduler.add_job(device_id, module, status["interval_seconds"]))
        else:
            # Stop if running
            if status["status"] == "running":
                asyncio.run(scheduler.stop_job(device_id, module))
        status = asyncio.run(scheduler.get_job_status(device_id, module))

    return status


@router.get("/snmp/devices/{device_id}/monitoring/{module}/status")
def get_module_monitoring_status(
    device_id: int,
    module: str,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Get monitoring status for a specific module."""
    from backend.services.snmp_polling import get_polling_scheduler
    import asyncio

    scheduler = asyncio.run(get_polling_scheduler())
    status = asyncio.run(scheduler.get_job_status(device_id, module))
    if not status:
        raise HTTPException(status_code=404, detail="Monitoring config not found")
    return status


# ---------------------------------------------------------------------------
# Latest Metrics Endpoints (DB-backed, no live SNMP)
# ---------------------------------------------------------------------------

@router.get("/snmp/devices/{device_id}/metrics/latest")
def get_latest_metrics(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Get all latest metrics for a device (from latest-value tables)."""
    from backend.models.snmp import LatestCPU, LatestMemory, LatestStorage, LatestInterface, LatestEnvironment

    cpu = db.query(LatestCPU).filter(LatestCPU.device_id == device_id).first()
    mem = db.query(LatestMemory).filter(LatestMemory.device_id == device_id).first()
    storage = db.query(LatestStorage).filter(LatestStorage.device_id == device_id).all()
    interfaces = db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()
    env = db.query(LatestEnvironment).filter(LatestEnvironment.device_id == device_id).all()

    return {
        "device_id": device_id,
        "cpu": {
            "utilization_percent": cpu.utilization_percent if cpu else None,
            "per_core": cpu.per_core if cpu else {},
            "load_avg": cpu.load_avg if cpu else {},
            "polled_at": cpu.polled_at.isoformat() if cpu and cpu.polled_at else None,
        } if cpu else None,
        "memory": {
            "total_bytes": mem.total_bytes if mem else None,
            "used_bytes": mem.used_bytes if mem else None,
            "free_bytes": mem.free_bytes if mem else None,
            "cached_bytes": mem.cached_bytes if mem else None,
            "buffer_bytes": mem.buffer_bytes if mem else None,
            "swap_total": mem.swap_total if mem else None,
            "swap_free": mem.swap_free if mem else None,
            "utilization_percent": mem.utilization_percent if mem else None,
            "polled_at": mem.polled_at.isoformat() if mem and mem.polled_at else None,
        } if mem else None,
        "storage": [
            {
                "volume_id": s.volume_id,
                "mount_name": s.mount_name,
                "total_bytes": s.total_bytes,
                "used_bytes": s.used_bytes,
                "free_bytes": s.free_bytes,
                "utilization_percent": s.utilization_percent,
                "type_label": s.type_label,
                "polled_at": s.polled_at.isoformat() if s.polled_at else None,
            }
            for s in storage
        ],
        "interfaces": [
            {
                "interface_id": i.interface_id,
                "if_index": i.if_index,
                "name": i.name,
                "oper_status": i.oper_status,
                "admin_status": i.admin_status,
                "speed_bps": i.speed_bps,
                "rx_mbps": i.rx_mbps,
                "tx_mbps": i.tx_mbps,
                "rx_octets": i.rx_octets,
                "tx_octets": i.tx_octets,
                "rx_packets": i.rx_packets,
                "tx_packets": i.tx_packets,
                "errors": i.errors,
                "discards": i.discards,
                "utilization_percent": i.utilization_percent,
                "polled_at": i.polled_at.isoformat() if i.polled_at else None,
            }
            for i in interfaces
        ],
        "environment": [
            {
                "sensor_id": e.sensor_id,
                "sensor_name": e.sensor_name,
                "sensor_type": e.sensor_type,
                "value": e.value,
                "unit": e.unit,
                "status": e.status,
                "polled_at": e.polled_at.isoformat() if e.polled_at else None,
            }
            for e in env
        ],
    }


@router.get("/snmp/devices/{device_id}/cpu/latest")
def get_latest_cpu(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    from backend.models.snmp import LatestCPU
    cpu = db.query(LatestCPU).filter(LatestCPU.device_id == device_id).first()
    if not cpu:
        return {"device_id": device_id, "supported": False, "message": "No CPU data yet"}
    return {
        "device_id": device_id,
        "supported": True,
        "current_usage": cpu.utilization_percent,
        "per_core": cpu.per_core,
        "load_avg": cpu.load_avg,
        "last_poll": cpu.polled_at.isoformat() if cpu.polled_at else None,
    }


@router.get("/snmp/devices/{device_id}/memory/latest")
def get_latest_memory(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    from backend.models.snmp import LatestMemory
    mem = db.query(LatestMemory).filter(LatestMemory.device_id == device_id).first()
    if not mem:
        return {"device_id": device_id, "supported": False, "message": "No memory data yet"}
    return {
        "device_id": device_id,
        "supported": True,
        "total_bytes": mem.total_bytes,
        "used_bytes": mem.used_bytes,
        "free_bytes": mem.free_bytes,
        "cached_bytes": mem.cached_bytes,
        "buffer_bytes": mem.buffer_bytes,
        "swap_total": mem.swap_total,
        "swap_free": mem.swap_free,
        "utilization_percent": mem.utilization_percent,
        "last_poll": mem.polled_at.isoformat() if mem.polled_at else None,
    }


@router.get("/snmp/devices/{device_id}/interfaces/latest")
def get_latest_interfaces(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> list[dict[str, Any]]:
    from backend.models.snmp import LatestInterface
    interfaces = db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()
    return [
        {
            "interface_id": i.interface_id,
            "if_index": i.if_index,
            "name": i.name,
            "oper_status": i.oper_status,
            "admin_status": i.admin_status,
            "speed_bps": i.speed_bps,
            "rx_mbps": i.rx_mbps,
            "tx_mbps": i.tx_mbps,
            "rx_octets": i.rx_octets,
            "tx_octets": i.tx_octets,
            "rx_packets": i.rx_packets,
            "tx_packets": i.tx_packets,
            "errors": i.errors,
            "discards": i.discards,
            "utilization_percent": i.utilization_percent,
            "last_poll": i.polled_at.isoformat() if i.polled_at else None,
        }
        for i in interfaces
    ]


@router.get("/snmp/devices/{device_id}/storage/latest")
def get_latest_storage(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> list[dict[str, Any]]:
    from backend.models.snmp import LatestStorage
    storage = db.query(LatestStorage).filter(LatestStorage.device_id == device_id).all()
    return [
        {
            "volume_id": s.volume_id,
            "mount_name": s.mount_name,
            "total_bytes": s.total_bytes,
            "used_bytes": s.used_bytes,
            "free_bytes": s.free_bytes,
            "utilization_percent": s.utilization_percent,
            "type_label": s.type_label,
            "last_poll": s.polled_at.isoformat() if s.polled_at else None,
        }
        for s in storage
    ]


@router.get("/snmp/devices/{device_id}/environment/latest")
def get_latest_environment(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> list[dict[str, Any]]:
    from backend.models.snmp import LatestEnvironment
    env = db.query(LatestEnvironment).filter(LatestEnvironment.device_id == device_id).all()
    return [
        {
            "sensor_id": e.sensor_id,
            "sensor_name": e.sensor_name,
            "sensor_type": e.sensor_type,
            "value": e.value,
            "unit": e.unit,
            "status": e.status,
            "last_poll": e.polled_at.isoformat() if e.polled_at else None,
        }
        for e in env
    ]


# ---------------------------------------------------------------------------
# Optimized Device List & Details Endpoints
# ---------------------------------------------------------------------------

@router.get("/snmp/devices")
def list_snmp_devices_optimized(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    snmp_status: str | None = Query(default=None),
    monitoring_status: str | None = Query(default=None),
    device_type: str | None = Query(default=None),
    vendor: str | None = Query(default=None),
    model: str | None = Query(default=None),
    hostname: str | None = Query(default=None),
    sort_by: str = Query(default="id"),
    sort_order: str = Query(default="asc"),
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Optimized paginated device list with all info needed for the device list page."""
    from backend.models.identity import DeviceIdentity, DeviceCapabilities
    from backend.models.snmp import MonitoringConfig
    from sqlalchemy import or_, func

    query = db.query(Device).filter(Device.deleted_at.is_(None))

    # Join with credentials to only show SNMP-configured devices
    query = query.join(DeviceCredential, DeviceCredential.device_id == Device.id)

    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Device.ip_address.ilike(search_term),
            Device.hostname.ilike(search_term),
            Device.mac_address.ilike(search_term),
        ))

    # Filters
    if status:
        query = query.filter(Device.status == status)
    if device_type:
        query = query.filter(Device.device_type.has(DeviceType.name == device_type))
    if vendor:
        query = query.filter(Device.vendor.has(Vendor.vendor_name == vendor))
    if model:
        query = query.filter(Device.model.ilike(f"%{model}%"))
    if hostname:
        query = query.filter(Device.hostname.ilike(f"%{hostname}%"))

    # SNMP status filter (from identity)
    if snmp_status:
        query = query.join(DeviceIdentity, DeviceIdentity.device_id == Device.id, isouter=True)
        if snmp_status == "verified":
            query = query.filter(DeviceIdentity.vendor.isnot(None))
        elif snmp_status == "error":
            query = query.filter(DeviceIdentity.vendor.is_(None))

    # Monitoring status filter
    if monitoring_status:
        query = query.join(MonitoringConfig, MonitoringConfig.device_id == Device.id, isouter=True)
        if monitoring_status == "running":
            query = query.filter(MonitoringConfig.status == "running")
        elif monitoring_status == "stopped":
            query = query.filter(or_(MonitoringConfig.status == "stopped", MonitoringConfig.id.is_(None)))

    # Sorting
    sort_column = getattr(Device, sort_by, Device.id)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    total = query.count()
    devices = query.offset((page - 1) * page_size).limit(page_size).all()

    # Build response with all needed data
    items = []
    for d in devices:
        # Get identity
        di = db.query(DeviceIdentity).filter(DeviceIdentity.device_id == d.id).first()
        # Get capabilities
        dc = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == d.id).first()
        # Get monitoring configs
        configs = db.query(MonitoringConfig).filter(MonitoringConfig.device_id == d.id).all()
        modules_monitored = sum(1 for c in configs if c.enabled and c.status == "running")

        vendor_name = d.vendor.vendor_name if d.vendor else (di.vendor if di else None)
        snmp_status_val = "verified" if di and di.vendor else "unknown"

        items.append({
            "id": d.id,
            "name": d.hostname,
            "ip_address": d.ip_address,
            "hostname": d.hostname,
            "device_type": d.device_type.name if d.device_type else None,
            "model": d.model,
            "serial_number": d.serial_number,
            "firmware": d.firmware_version,
            "mac_address": d.mac_address,
            "status": d.status,
            "snmp_version": d.credentials[0].snmp_version if d.credentials else None,
            "snmp_status": snmp_status_val,
            "monitoring_enabled": any(c.enabled for c in configs),
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "last_poll_at": max((c.last_poll_at for c in configs if c.last_poll_at), default=None),
            "modules_monitored": modules_monitored,
        })

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/snmp/devices/{device_id}")
def get_device_details(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Get complete device details from DB (no live SNMP)."""
    from backend.models.identity import DeviceIdentity, DeviceCapabilities
    from backend.models.snmp import MonitoringConfig, SNMPCredential, LatestCPU, LatestMemory, LatestStorage, LatestInterface, LatestEnvironment, PollingHistory
    from backend.models import Interface, Vendor, DeviceType

    device = db.query(Device).filter(Device.id == device_id, Device.deleted_at.is_(None)).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    di = db.query(DeviceIdentity).filter(DeviceIdentity.device_id == device_id).first()
    dc = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    configs = db.query(MonitoringConfig).filter(MonitoringConfig.device_id == device_id).all()
    cred = db.query(SNMPCredential).filter(SNMPCredential.device_id == device_id).first()

    # Latest metrics
    cpu = db.query(LatestCPU).filter(LatestCPU.device_id == device_id).first()
    mem = db.query(LatestMemory).filter(LatestMemory.device_id == device_id).first()
    storage = db.query(LatestStorage).filter(LatestStorage.device_id == device_id).all()
    interfaces = db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()
    env = db.query(LatestEnvironment).filter(LatestEnvironment.device_id == device_id).all()

    # Polling history (last 10)
    poll_history = db.query(PollingHistory).filter(
        PollingHistory.device_id == device_id
    ).order_by(PollingHistory.id.desc()).limit(10).all()

    return {
        "device": {
            "id": device.id,
            "name": device.hostname,
            "ip_address": device.ip_address,
            "hostname": device.hostname,
            "description": device.model,
            "device_type": device.device_type.name if device.device_type else None,
            "vendor": device.vendor.vendor_name if device.vendor else (di.vendor if di else None),
            "model": device.model,
            "serial_number": device.serial_number,
            "firmware": device.firmware_version,
            "mac_address": device.mac_address,
            "status": device.status,
            "monitoring_status": device.monitoring_status,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "uptime_seconds": device.uptime_seconds,
        },
        "snmp": {
            "version": cred.snmp_version if cred else None,
            "port": 161,
            "status": "verified" if di and di.vendor else "unknown",
            "last_test_at": None,
        },
        "capabilities": dc.to_map() if dc else {},
        "monitoring": [
            {
                "module_name": c.module_name,
                "enabled": c.enabled,
                "interval_seconds": c.interval_seconds,
                "status": c.status,
                "last_started_at": c.last_started_at.isoformat() if c.last_started_at else None,
                "last_stopped_at": c.last_stopped_at.isoformat() if c.last_stopped_at else None,
                "last_poll_at": c.last_poll_at.isoformat() if c.last_poll_at else None,
                "next_poll_at": c.next_poll_at.isoformat() if c.next_poll_at else None,
                "error_message": c.error_message,
            }
            for c in configs
        ],
        "latest_metrics": {
            "cpu": {
                "utilization_percent": cpu.utilization_percent if cpu else None,
                "per_core": cpu.per_core if cpu else {},
                "load_avg": cpu.load_avg if cpu else {},
                "polled_at": cpu.polled_at.isoformat() if cpu and cpu.polled_at else None,
            } if cpu else None,
            "memory": {
                "total_bytes": mem.total_bytes if mem else None,
                "used_bytes": mem.used_bytes if mem else None,
                "free_bytes": mem.free_bytes if mem else None,
                "utilization_percent": mem.utilization_percent if mem else None,
                "polled_at": mem.polled_at.isoformat() if mem and mem.polled_at else None,
            } if mem else None,
            "storage": [
                {
                    "volume_id": s.volume_id,
                    "mount_name": s.mount_name,
                    "total_bytes": s.total_bytes,
                    "used_bytes": s.used_bytes,
                    "free_bytes": s.free_bytes,
                    "utilization_percent": s.utilization_percent,
                    "type_label": s.type_label,
                    "polled_at": s.polled_at.isoformat() if s.polled_at else None,
                }
                for s in storage
            ],
            "interfaces": [
                {
                    "interface_id": i.interface_id,
                    "if_index": i.if_index,
                    "name": i.name,
                    "oper_status": i.oper_status,
                    "admin_status": i.admin_status,
                    "speed_bps": i.speed_bps,
                    "rx_mbps": i.rx_mbps,
                    "tx_mbps": i.tx_mbps,
                    "utilization_percent": i.utilization_percent,
                    "polled_at": i.polled_at.isoformat() if i.polled_at else None,
                }
                for i in interfaces
            ],
            "environment": [
                {
                    "sensor_id": e.sensor_id,
                    "sensor_name": e.sensor_name,
                    "sensor_type": e.sensor_type,
                    "value": e.value,
                    "unit": e.unit,
                    "status": e.status,
                    "polled_at": e.polled_at.isoformat() if e.polled_at else None,
                }
                for e in env
            ],
        },
        "polling_history": [
            {
                "id": p.id,
                "collector": p.collector,
                "status": p.status,
                "duration_ms": p.duration_ms,
                "error": p.error,
                "timestamp": p.created_at.isoformat() if p.created_at else None,
            }
            for p in poll_history
        ],
    }
