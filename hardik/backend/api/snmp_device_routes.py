
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
import time
import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import BackgroundTasks, APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload, load_only

from backend.database.session import SessionLocal, get_db
from backend.dependencies import get_current_user, require_permission
from backend.auth.authorization import can_access_site, get_accessible_site_ids
from backend.models import Device, DeviceCredential, Event, Vendor, DeviceType
from backend.models.identity import DeviceCapabilities, DeviceIdentity
from backend.models.snmp import DeviceInterface, LatestInterface
from backend.snmp.normalizer import mac as canonical_mac
from backend.utils.time import as_utc, utc_now
from backend.services.device_health import derive_monitoring_state

logger = logging.getLogger(__name__)

def _require_site_scope(
    device_id: int | None = None,
    interface_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> None:
    """Enforce site scope for authenticated SNMP device/interface routes."""
    resolved_device_id = device_id
    if resolved_device_id is None and interface_id is not None:
        interface = db.query(DeviceInterface).filter(DeviceInterface.id == interface_id).first()
        resolved_device_id = interface.device_id if interface else None
    if resolved_device_id is None:
        return
    device = db.query(Device).filter(Device.id == resolved_device_id, Device.deleted_at.is_(None)).first()
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Device {resolved_device_id} not found")


router = APIRouter(prefix="/api/v1", tags=["SNMP Device Monitoring"], dependencies=[Depends(_require_site_scope)])
MAX_SNMP_TABLE_ROWS = 500


def _interface_api_elapsed(now: datetime, previous: datetime | None) -> float:
    if previous is None:
        return 0
    return (as_utc(now, legacy="UTC_NAIVE") - as_utc(previous, legacy="UTC_NAIVE")).total_seconds()


def _topology_revision(db: Session) -> dict[str, str]:
    """Return a stable revision for shared inventory and topology state."""
    devices = db.query(Device).filter(Device.deleted_at.is_(None)).order_by(Device.id).limit(200).all()
    inventory = [{
        "id": row.id,
        "hostname": row.hostname,
        "ip": row.ip_address,
        "mac": row.mac_address,
        "model": row.model,
        "status": row.status,
        "topology_metadata": row.topology_metadata or {},
    } for row in devices]
    capability_map = {
        row.device_id: row
        for row in db.query(DeviceCapabilities).filter(
            DeviceCapabilities.device_id.in_([row.id for row in devices])
        ).all()
    } if devices else {}
    topology = _latest_cached_topology(capability_map) or {}
    snapshot_at = str(topology.get("timestamp") or topology.get("collected_at") or "")
    payload = json.dumps({"inventory": inventory, "snapshot_at": snapshot_at}, sort_keys=True, default=str)
    return {
        "revision": hashlib.sha256(payload.encode()).hexdigest()[:16],
        # Server time at which this revision was observed. Clients render this
        # consistently from one ISO value instead of their local refresh time.
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class TopologySnapshotPayload(BaseModel):
    device_id: int
    devices: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    collected_at: str
    source: str = "live_refresh"


def _topology_timestamp_is_newer(candidate: str, current: str | None) -> bool:
    """Prevent an older collector response from replacing a newer snapshot."""
    if not current:
        return True
    try:
        candidate_dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        current_dt = datetime.fromisoformat(current.replace("Z", "+00:00"))
        if candidate_dt.tzinfo is None:
            candidate_dt = candidate_dt.replace(tzinfo=timezone.utc)
        if current_dt.tzinfo is None:
            current_dt = current_dt.replace(tzinfo=timezone.utc)
        return candidate_dt >= current_dt
    except (TypeError, ValueError):
        # An unparseable candidate must not displace a valid persisted time.
        return bool(candidate and not current)


def _topology_identity(value: Any, *, link: bool = False) -> tuple[str, ...]:
    """Build a stable identity without depending on collector-specific fields."""
    if not isinstance(value, dict):
        return ("",)
    if link:
        source = value.get("from") or value.get("source") or value.get("source_node") or value.get("source_id")
        target = value.get("to") or value.get("target") or value.get("target_node") or value.get("target_id")
        local = value.get("localPort") or value.get("local_port") or value.get("source_port")
        remote = value.get("remotePort") or value.get("remote_port") or value.get("target_port")
        if source or target or local or remote:
            return ("link", str(source or ""), str(target or ""), str(local or ""), str(remote or ""))
        return ("link-id", str(value.get("id") or ""))
    for field in ("id", "device_id", "ip_address", "ip", "mac_address", "mac", "hostname", "name"):
        current = value.get(field)
        if current is not None and str(current).strip():
            return (field, str(current).strip().lower())
    return ("node", "")


def _topology_link_endpoints(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return ("", "")
    source = value.get("from") or value.get("source") or value.get("source_node") or value.get("source_id")
    target = value.get("to") or value.get("target") or value.get("target_node") or value.get("target_id")
    return (str(source or ""), str(target or ""))


def _topology_positive_removal(value: Any) -> bool:
    """Only explicit fresh removal evidence may delete a persisted entity."""
    if not isinstance(value, dict):
        return False
    return any(value.get(field) is True for field in ("removed", "deleted", "disappeared", "removal_confirmed")) or value.get("present") is False


def _merge_collector_topology(
    existing_devices: list[dict[str, Any]],
    existing_links: list[dict[str, Any]],
    fresh_devices: list[dict[str, Any]],
    fresh_links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge a partial collector cycle over the last complete topology."""
    devices = [dict(item) for item in existing_devices if isinstance(item, dict)]
    links = [dict(item) for item in existing_links if isinstance(item, dict)]

    for candidate in fresh_devices:
        if not isinstance(candidate, dict):
            continue
        identity = _topology_identity(candidate)
        index = next((i for i, item in enumerate(devices) if _topology_identity(item) == identity), None)
        if _topology_positive_removal(candidate):
            if index is not None:
                devices.pop(index)
            continue
        if index is None:
            devices.append(dict(candidate))
        else:
            devices[index] = {**devices[index], **candidate}

    for candidate in fresh_links:
        if not isinstance(candidate, dict):
            continue
        identity = _topology_identity(candidate, link=True)
        index = next((i for i, item in enumerate(links) if _topology_identity(item, link=True) == identity), None)
        if index is None and candidate.get("id"):
            same_id = [i for i, item in enumerate(links) if item.get("id") == candidate.get("id")]
            if len(same_id) == 1:
                index = same_id[0]
        if index is None:
            endpoints = _topology_link_endpoints(candidate)
            same_endpoints = [i for i, item in enumerate(links) if _topology_link_endpoints(item) == endpoints and endpoints != ("", "")]
            if len(same_endpoints) == 1:
                index = same_endpoints[0]
        if _topology_positive_removal(candidate):
            if index is not None:
                links.pop(index)
            continue
        if index is None:
            links.append(dict(candidate))
        else:
            links[index] = {**links[index], **candidate}
    return devices, links


def _persist_topology_snapshot(
    db: Session,
    device_id: int,
    devices: list[dict[str, Any]],
    links: list[dict[str, Any]],
    collected_at: str,
    source: str = "live_refresh",
) -> bool:
    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    if cap is None:
        cap = DeviceCapabilities(device_id=device_id, capability_detail={})
        db.add(cap)
        db.flush()
    detail = dict(cap.capability_detail or {})
    current = detail.get("topology") if isinstance(detail.get("topology"), dict) else {}
    current_timestamp = current.get("timestamp") or current.get("collected_at")
    if not _topology_timestamp_is_newer(collected_at, current_timestamp):
        logger.info(
            "[TOPOLOGY-BE] persist ignored device_id=%s row_id=%s candidate_timestamp=%s "
            "current_timestamp=%s nodes=%s links=%s accepted=False",
            device_id,
            cap.id,
            collected_at,
            current_timestamp,
            len(devices),
            len(links),
        )
        return False
    if source == "collector":
        current_data = current.get("data") if isinstance(current.get("data"), dict) else {}
        devices, links = _merge_collector_topology(
            current_data.get("nodes") or [],
            current_data.get("links") or [],
            devices,
            links,
        )
    detail["topology"] = {
        **current,
        "supported": True,
        "data": {"nodes": devices, "links": links},
        "timestamp": collected_at,
        "collected_at": collected_at,
        "source": source,
    }
    cap.cap_topology = True
    cap.capability_detail = detail
    cap.updated_at = datetime.utcnow()
    db.flush()
    logger.info(
        "[TOPOLOGY-BE] persist accepted device_id=%s row_id=%s timestamp=%s nodes=%s links=%s accepted=True",
        device_id,
        cap.id,
        collected_at,
        len(devices),
        len(links),
    )
    return True


def _latest_cached_topology(capabilities: dict[int, DeviceCapabilities]) -> dict[str, Any] | None:
    """Return the newest non-empty topology snapshot across active devices."""
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for capability in capabilities.values():
        topology = (capability.capability_detail or {}).get("topology")
        if not isinstance(topology, dict):
            continue
        data = topology.get("data") or {}
        if not data.get("nodes") and not data.get("links"):
            continue
        raw_timestamp = topology.get("timestamp") or topology.get("collected_at")
        try:
            timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            timestamp = datetime.min.replace(tzinfo=timezone.utc)
        candidates.append((timestamp, topology))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None

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


def _get_credentials_map(device_ids: list[int], db: Session) -> dict[int, DeviceCredential]:
    if not device_ids:
        return {}
    rows = (
        db.query(DeviceCredential)
        .options(load_only(
            DeviceCredential.id,
            DeviceCredential.device_id,
            DeviceCredential.snmp_version,
            DeviceCredential.community_string,
            DeviceCredential.username,
            DeviceCredential.auth_protocol,
            DeviceCredential.auth_password,
            DeviceCredential.privacy_protocol,
            DeviceCredential.privacy_password,
            DeviceCredential.security_level,
            DeviceCredential.snmp_port,
        ))
        .filter(DeviceCredential.device_id.in_(device_ids))
        .order_by(DeviceCredential.id.asc())
        .all()
    )
    by_device_id: dict[int, DeviceCredential] = {}
    for row in rows:
        by_device_id.setdefault(row.device_id, row)
    return by_device_id


def _live_collect(
    device: Device,
    cred: DeviceCredential | None,
    domain: str | None = None,
    *,
    acquire_guard: bool = True,
) -> dict[str, Any]:
    """Run a live SNMP collect on the device using stored credentials."""
    from backend.snmp.collector import SNMPService  # noqa: PLC0415
    from backend.snmp.credentials import SNMPCredentials  # noqa: PLC0415
    from backend.utils.crypto import decrypt_secret  # noqa: PLC0415
    from backend.observability import record_snmp_duration  # noqa: PLC0415
    from backend.services.snmp_poll_guard import poll_guard  # noqa: PLC0415

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
        port=getattr(cred, "snmp_port", None) or 161,
    )
    service = SNMPService(credentials=credentials)
    guard = poll_guard(device.id, domain or "__full__", blocking=False) if acquire_guard else None
    if guard is not None and not guard.__enter__():
        guard.__exit__(None, None, None)
        raise HTTPException(status_code=409, detail="Poll already in progress for this device and module")
    snmp_started = time.perf_counter()
    try:
        if not domain:
            return service.collect(device.ip_address)

        # collect_domain returns the collector payload directly, while the HTTP
        # routes use the same stable envelope as a full collection. Keep the
        # envelope here so every module route can read its real data consistently.
        domain_result = service.collect_domain(device.ip_address, domain)
        return {
            "api_version": "2.0",
            "ip": device.ip_address,
            "reachable": domain_result.get("supported") is not False,
            "snmp_enabled": True,
            "snmp_version": version,
            "vendor": device.vendor.vendor_name if device.vendor else None,
            "device_type": device.device_type.name if device.device_type else None,
            "hostname": device.hostname,
            "collection_ms": domain_result.get("collection_ms", 0),
            "collectors": {domain: domain_result},
            "unsupported": [] if domain_result.get("supported") else [domain],
        }
    finally:
        record_snmp_duration((time.perf_counter() - snmp_started) * 1000)
        if guard is not None:
            guard.__exit__(None, None, None)


def _collector_data(result: dict[str, Any], name: str) -> dict[str, Any]:
    """Extract a single collector's output from a full collect() result."""
    collectors = result.get("collectors") or {}
    return collectors.get(name) or {
        "collector": name, "supported": False,
        "reason": "Collector not present in poll result", "missing": [],
    }


def _known_device_mac(device: Device, db: Session) -> str | None:
    """Return the best MAC already known for a device, without another SNMP poll."""
    if device.mac_address:
        return str(device.mac_address)

    identity_macs = (
        db.query(DeviceIdentity.mac_addresses)
        .filter(DeviceIdentity.device_id == device.id)
        .scalar()
    ) or []
    if isinstance(identity_macs, list):
        return next((str(value) for value in identity_macs if value), None)
    return None


def _infer_topology_type(device: Device | None, node: dict[str, Any]) -> str | None:
    text = " ".join(
        part.lower()
        for part in [
            str(node.get("hostname") or ""),
            str(node.get("name") or ""),
            str(node.get("vendor") or ""),
            str(node.get("model") or ""),
            str(node.get("device_type") or ""),
            str(device.device_type.name if device and device.device_type else ""),
        ]
        if part
    )
    if any(token in text for token in ("nvr", "dvr", "cctv", "camera")):
        return "server"
    if any(token in text for token in ("firewall", "fortigate")):
        return "firewall"
    if any(token in text for token in ("router", "gateway")):
        return "router"
    if any(token in text for token in ("access point", "wireless")):
        return "access-point"
    if "switch" in text:
        return "switch"
    if any(token in text for token in ("server", "linux")):
        return "server"
    return node.get("device_type") or (device.device_type.name if device and device.device_type else None)


def _normalize_mac(value: Any) -> str:
    return canonical_mac(value) or ""


def _display_mac(value: Any) -> str | None:
    """Return a stable human-readable MAC without assuming a vendor format."""
    normalized = _normalize_mac(value).replace(":", "")
    if len(normalized) != 12:
        return str(value) if value else None
    return ":".join(normalized[index:index + 2] for index in range(0, 12, 2)).upper()


def _ip_sort_key(value: Any) -> tuple[Any, ...]:
    text_value = str(value)
    parts = text_value.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return (0, *(int(part) for part in parts))
    return (1, text_value)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _load_device_identity_maps(db: Session, devices: list[Device]) -> dict[str, dict[str, Any]]:
    identities = db.query(DeviceIdentity).filter(DeviceIdentity.device_id.in_([device.id for device in devices])).all()
    by_device_id: dict[str, dict[str, Any]] = {}
    by_mac: dict[str, dict[str, Any]] = {}
    by_hostname: dict[str, dict[str, Any]] = {}
    by_sys_name: dict[str, dict[str, Any]] = {}

    device_by_id = {str(device.id): device for device in devices}

    for identity in identities:
        device = device_by_id.get(str(identity.device_id))
        payload = {
            "device": device,
            "identity": identity,
            "hostname": _first_non_empty(identity.hostname, identity.sys_name, device.hostname if device else None),
            "ip_address": device.ip_address if device else None,
            "vendor": _first_non_empty(identity.vendor, device.vendor.vendor_name if device and device.vendor else None),
            "model": _first_non_empty(identity.model, device.model),
            "device_type": _first_non_empty(identity.device_type, device.device_type.name if device and device.device_type else None),
            "sys_name": identity.sys_name,
            "sys_descr": identity.sys_descr,
            "mac_addresses": identity.mac_addresses or [],
        }
        by_device_id[str(identity.device_id)] = payload
        if payload["hostname"]:
            by_hostname[payload["hostname"].lower()] = payload
        if identity.sys_name:
            by_sys_name[identity.sys_name.lower()] = payload
        for mac in identity.mac_addresses or []:
            norm = _normalize_mac(mac)
            if norm:
                by_mac[norm] = payload

    return {
        "by_device_id": by_device_id,
        "by_mac": by_mac,
        "by_hostname": by_hostname,
        "by_sys_name": by_sys_name,
    }


def _enrich_lldp_neighbors(db: Session, device: Device, neighbors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    devices = db.query(Device).filter(Device.deleted_at.is_(None)).limit(500).all()
    identity_maps = _load_device_identity_maps(db, devices)
    by_ip = {d.ip_address: d for d in devices}
    by_mac = {_normalize_mac(d.mac_address): d for d in devices if d.mac_address}
    enriched_neighbors: list[dict[str, Any]] = []

    for neighbor in neighbors:
        row = dict(neighbor)
        remote_mac = row.get("remote_chassis_id") or row.get("remote_mac")
        remote_ip = row.get("mgmt_address") or row.get("remote_mgmt_ip")
        remote_name = row.get("remote_sys_name") or row.get("remote_system_name") or row.get("remote_device")
        identity = None
        matching_device = None

        norm_mac = _normalize_mac(remote_mac)
        if norm_mac:
          matching_device = by_mac.get(norm_mac)
        if not matching_device and remote_ip:
          matching_device = by_ip.get(str(remote_ip))
        if matching_device:
            identity = identity_maps["by_device_id"].get(str(matching_device.id))
        if not identity and norm_mac:
            identity = identity_maps["by_mac"].get(norm_mac)
        if not identity and remote_name:
            identity = identity_maps["by_hostname"].get(str(remote_name).lower()) or identity_maps["by_sys_name"].get(str(remote_name).lower())

        row["remote_device"] = _first_non_empty(
            row.get("remote_device"),
            row.get("remote_system_name"),
            row.get("remote_sys_name"),
            identity.get("hostname") if identity else None,
            matching_device.hostname if matching_device else None,
            remote_name,
            remote_ip,
            remote_mac,
        )
        row["remote_system_name"] = _first_non_empty(
            row.get("remote_system_name"),
            row.get("remote_sys_name"),
            identity.get("sys_name") if identity else None,
            matching_device.hostname if matching_device else None,
            remote_name,
        )
        row["remote_sys_name"] = _first_non_empty(
            row.get("remote_sys_name"),
            row.get("remote_system_name"),
            identity.get("sys_name") if identity else None,
            matching_device.hostname if matching_device else None,
            remote_name,
        )
        row["remote_mgmt_ip"] = _first_non_empty(
            row.get("remote_mgmt_ip"),
            row.get("mgmt_address"),
            identity.get("ip_address") if identity else None,
            matching_device.ip_address if matching_device else None,
            remote_ip,
        )
        row["mgmt_address"] = _first_non_empty(
            row.get("mgmt_address"),
            row.get("remote_mgmt_ip"),
            identity.get("ip_address") if identity else None,
            matching_device.ip_address if matching_device else None,
            remote_ip,
        )
        row["capabilities"] = row.get("capabilities") or row.get("capabilities_supported") or row.get("capabilities_enabled") or []
        row["remote_chassis_id"] = _display_mac(remote_mac) if remote_mac else row.get("remote_chassis_id")
        enriched_neighbors.append(row)

    return enriched_neighbors


def _enrich_topology_node(
    node: dict[str, Any],
    matching_device: Device | None,
    identity_maps: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    node_mac = node.get("mac_address") or node.get("mac")
    node_hostname = _first_non_empty(node.get("hostname"), node.get("name"), node.get("sys_name"), node.get("sysName"))
    node_ip = _first_non_empty(node.get("ip_address"), node.get("ip"), node.get("management_ip"))
    identity = None
    if matching_device:
        identity = identity_maps["by_device_id"].get(str(matching_device.id))
    if not identity:
        norm_mac = _normalize_mac(node_mac)
        if norm_mac:
            identity = identity_maps["by_mac"].get(norm_mac)
    if not identity and node_hostname:
        identity = identity_maps["by_hostname"].get(node_hostname.lower()) or identity_maps["by_sys_name"].get(node_hostname.lower())

    merged = dict(node)
    if identity:
        merged["hostname"] = _first_non_empty(identity.get("hostname"), merged.get("hostname"), merged.get("name"))
        merged["ip_address"] = _first_non_empty(merged.get("ip_address"), merged.get("ip"), identity.get("ip_address"))
        merged["vendor"] = _first_non_empty(merged.get("vendor"), identity.get("vendor"))
        merged["model"] = _first_non_empty(merged.get("model"), identity.get("model"))
        merged["sys_name"] = identity.get("sys_name")
        merged["sys_descr"] = identity.get("sys_descr")
        merged["device_type"] = _first_non_empty(merged.get("device_type"), identity.get("device_type"))
        if identity.get("mac_addresses") and not merged.get("mac_addresses"):
            merged["mac_addresses"] = identity.get("mac_addresses")
    if matching_device:
        merged["hostname"] = _first_non_empty(merged.get("hostname"), matching_device.hostname)
        merged["ip_address"] = _first_non_empty(merged.get("ip_address"), matching_device.ip_address)
        merged["vendor"] = _first_non_empty(merged.get("vendor"), matching_device.vendor.vendor_name if matching_device.vendor else None)
        merged["model"] = _first_non_empty(merged.get("model"), matching_device.model)
        merged["device_type"] = _first_non_empty(merged.get("device_type"), matching_device.device_type.name if matching_device.device_type else None)
        if matching_device.mac_address and not merged.get("mac_address"):
            merged["mac_address"] = matching_device.mac_address
    merged["hostname"] = _first_non_empty(merged.get("hostname"), node_hostname, node_ip, node_mac, "UNKNOWN")
    merged["ip_address"] = _first_non_empty(merged.get("ip_address"), node_ip)
    merged["mac_address"] = _first_non_empty(merged.get("mac_address"), node_mac)
    merged["display_name"] = _first_non_empty(merged.get("hostname"), merged.get("model"), merged.get("mac_address"), merged.get("ip_address"))
    merged["device_type"] = _infer_topology_type(matching_device, merged) or merged.get("device_type")
    if merged["device_type"] in {"nvr", "dvr", "camera"}:
        merged["device_type"] = "server"
    return merged


def _persist_collect_result(device_id: int, result: dict[str, Any], db: Session) -> None:
    """Cache live/discovery collector output into latest tables and capability detail."""
    import asyncio
    from backend.services.snmp_polling import PollJob, SNMPPoller

    collectors = result.get("collectors") or {}
    if not isinstance(collectors, dict):
        return

    # System data can contain a MAC learned from the existing IF-MIB walk.
    # Keep the inventory/detail APIs backed by the same persisted value.
    system_data = (collectors.get("system") or {}).get("data") or {}
    discovered_mac = system_data.get("mac_address")
    interface_data = (collectors.get("interfaces") or {}).get("data") or {}
    interface_rows = interface_data.get("interfaces") if isinstance(interface_data, dict) else []
    if not discovered_mac and isinstance(interface_rows, list):
        discovered_mac = next(
            (row.get("mac") for row in interface_rows if isinstance(row, dict) and row.get("mac")),
            None,
        )
    if discovered_mac:
        stored_device = db.query(Device).filter(Device.id == device_id).first()
        if stored_device and not stored_device.mac_address:
            stored_device.mac_address = str(discovered_mac)

    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    if cap is None:
        cap = DeviceCapabilities(device_id=device_id)
        db.add(cap)
    # Domain polls contain only the requested collector. Do not mark every
    # other module unsupported or discard its previously discovered detail.
    detail = dict(cap.capability_detail or {})
    for name, collector in collectors.items():
        if not isinstance(collector, dict):
            continue
        attr = f"cap_{name}"
        if hasattr(cap, attr):
            setattr(cap, attr, collector.get("supported", False))
        if name == "topology":
            existing_topology = detail.get("topology") if isinstance(detail.get("topology"), dict) else {}
            candidate_timestamp = collector.get("timestamp") or datetime.utcnow().isoformat()
            current_timestamp = existing_topology.get("timestamp") or existing_topology.get("collected_at")
            if not _topology_timestamp_is_newer(candidate_timestamp, current_timestamp):
                continue
            candidate_data = collector.get("data") if isinstance(collector.get("data"), dict) else {}
            if collector.get("supported") is not True or not (candidate_data.get("nodes") or candidate_data.get("links")):
                continue
            current_data = existing_topology.get("data") if isinstance(existing_topology.get("data"), dict) else {}
            merged_nodes, merged_links = _merge_collector_topology(
                current_data.get("nodes") or [],
                current_data.get("links") or [],
                candidate_data.get("nodes") or [],
                candidate_data.get("links") or [],
            )
            collector = {
                **collector,
                "data": {**candidate_data, "nodes": merged_nodes, "links": merged_links},
            }
        existing = detail.get(name) if isinstance(detail.get(name), dict) else {}
        candidate_data = collector.get("data") if isinstance(collector.get("data"), dict) else {}
        candidate_supported = collector.get("supported") is True
        preserve_data = not candidate_supported and bool(existing.get("data"))
        detail[name] = {
            **existing,
            **collector,
            "data": existing.get("data") if preserve_data else candidate_data,
            "collection_status": "SUCCESS" if candidate_supported else "FAILED",
            "last_good_timestamp": existing.get("timestamp") if preserve_data else collector.get("timestamp"),
        }
    cap.capability_detail = detail
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
    auto_discover: bool = False  # keep create fast; run discovery only when explicitly requested


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
    from backend.services.alerting import create_device_added_alert  # noqa: PLC0415

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
    cred.snmp_port       = payload.snmp_port or 161

    db.add(Event(
        device_id=device.id,
        event_type="DEVICE_MANUAL_ADD",
        description=f"Device {ip} added manually",
    ))
    if created:
        create_device_added_alert(
            db,
            device.id,
            device.hostname,
            device.ip_address,
            "SNMP",
            device.status,
            device.mac_address,
            payload.snmp_version,
        )
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


def _persist_domain_result(device_id: int, result: dict[str, Any], domain: str, db: Session) -> None:
    """Merge one lightweight domain result without erasing other cached modules."""
    collectors = result.get("collectors") or {}
    collector = collectors.get(domain)
    if not isinstance(collector, dict):
        return
    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    if cap is None:
        cap = DeviceCapabilities(device_id=device_id, capability_detail={})
        db.add(cap)
    detail = dict(cap.capability_detail or {})
    existing = detail.get(domain) if isinstance(detail.get(domain), dict) else {}
    candidate_data = collector.get("data") if isinstance(collector.get("data"), dict) else {}
    candidate_supported = collector.get("supported") is True
    candidate_has_rows = bool(
        candidate_data.get("entries")
        or candidate_data.get("port_groups")
        or candidate_data.get("interfaces")
    )
    # An unsupported/failed poll is not a valid empty snapshot. Preserve the
    # last good payload and expose the collection state separately.
    preserve_data = not candidate_supported and bool(existing.get("data"))
    detail[domain] = {
        **existing,
        **collector,
        "data": existing.get("data") if preserve_data else candidate_data,
        "collection_status": "SUCCESS" if candidate_supported and (candidate_has_rows or not existing.get("data")) else "FAILED",
        "last_good_timestamp": existing.get("timestamp") if preserve_data else collector.get("timestamp"),
    }
    cap.capability_detail = detail
    attr = f"cap_{domain}"
    if hasattr(cap, attr):
        setattr(cap, attr, collector.get("supported", False))
    cap.updated_at = datetime.utcnow()
    db.flush()


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
    system_data = (result.get("collectors") or {}).get("system", {}).get("data") or {}
    system_mac = system_data.get("mac_address")
    if system_mac:
        macs.append(str(system_mac))
        if not device.mac_address:
            device.mac_address = str(system_mac)
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
    # Persist values from the full collector on the primary device row so the
    # inventory and detail endpoints can render them immediately.
    system_data = (result.get("collectors", {}).get("system", {}).get("data") or {})
    uptime = system_data.get("uptime") or {}
    uptime_seconds = result.get("uptime_seconds")
    if isinstance(uptime, dict):
        uptime_seconds = uptime.get("seconds", uptime_seconds)
    if uptime_seconds is not None:
        device.uptime_seconds = int(float(uptime_seconds))
    interface_data = (result.get("collectors", {}).get("interfaces", {}).get("data") or {})
    interface_rows = interface_data.get("interfaces") if isinstance(interface_data, dict) else []
    if not device.mac_address and result.get("mac_address"):
        device.mac_address = str(result["mac_address"])[:32]
    if not device.mac_address and isinstance(interface_rows, list):
        first_mac = next(
            (row.get("mac") for row in interface_rows if isinstance(row, dict) and row.get("mac")),
            None,
        )
        if first_mac:
            device.mac_address = str(first_mac)[:32]
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
    module: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Trigger a full poll, or one requested module, and return the result."""
    from backend.services.snmp_poll_guard import poll_guard

    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    guard = poll_guard(device_id, module or "__full__", blocking=False)
    acquired = guard.__enter__()
    if not acquired:
        guard.__exit__(None, None, None)
        raise HTTPException(status_code=409, detail="Poll already in progress for this device and module")
    try:
        result = _live_collect(device, cred, domain=module or None, acquire_guard=False)
        _persist_collect_result(device_id, result, db)
        return result
    finally:
        guard.__exit__(None, None, None)


@router.get("/snmp/devices/{device_id}/overview")
def get_snmp_overview(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Device overview: identity + health + capabilities + last-poll summary."""
    from backend.cache.redis_cache import get_json, set_json
    from backend.models.identity import DeviceIdentity, DeviceCapabilities  # noqa
    from backend.models.snmp import PollingHistory  # noqa
    cache_key = f"nms:snmp:device:{device_id}:overview:v1"
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached
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

    payload = {
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
    set_json(cache_key, payload)
    return payload


@router.get("/snmp/devices/{device_id}/system")
def get_snmp_system(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    cred   = _get_credentials(device_id, db)
    result = _live_collect(device, cred, domain="system")
    system = _collector_data(result, "system")
    system_data = dict(system.get("data") or {})
    mac_address = _known_device_mac(device, db)
    # MAC is learned from interface/identity data, not the system OID set.
    # Always expose the field so an empty database is distinguishable from a
    # response-mapping bug, while keeping the system collector unchanged.
    system_data["mac_address"] = mac_address or system_data.get("mac_address")
    system = {**system, "data": system_data}
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
        **system,
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

    result   = _live_collect(device, cred, domain="cpu")
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
        "collection_status": col.get("collection_status", "NOT_COLLECTED"),
        "last_good_timestamp": col.get("last_good_timestamp"),
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="memory")
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
        "collection_status": col.get("collection_status", "NOT_COLLECTED"),
        "last_good_timestamp": col.get("last_good_timestamp"),
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="storage")
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
def get_snmp_interfaces(device_id: int, limit: int = Query(default=MAX_SNMP_TABLE_ROWS, ge=1, le=MAX_SNMP_TABLE_ROWS), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    credential = _get_credentials(device_id, db)
    # Interface detail is also used by topology rendering. A device without
    # configured SNMP credentials must not turn an optional interface read
    # into a 422; return the last persisted interface snapshot (or empty data)
    # using the same response contract.
    if credential is None:
        capability = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
        stored = ((capability.capability_detail or {}).get("interfaces") or {}) if capability else {}
        stored_data = stored.get("data") or {}
        return {
            "api_version": "2.0", "ip": device.ip_address, "reachable": False,
            "snmp_version": None, "vendor": device.vendor.vendor_name if device.vendor else None,
            "device_type": device.device_type.name if device.device_type else None,
            "hostname": device.hostname, "collection_ms": 0, "device_id": device_id,
            "collector": "interfaces", "supported": bool(stored_data.get("interfaces")),
            "interfaces": (stored_data.get("interfaces") or [])[:limit],
            "data": {"interfaces": (stored_data.get("interfaces") or [])[:limit]},
            "warnings": ["No SNMP credentials configured; returned persisted interfaces."],
        }
    result = _live_collect(device, credential, domain="interfaces")
    col      = _collector_data(result, "interfaces")
    col_data = col.get("data") or {}
    live_interfaces = col_data.get("interfaces", [])
    previous_by_index = {
        row.if_index: row
        for row in db.query(LatestInterface).options(load_only(
            LatestInterface.interface_id,
            LatestInterface.if_index,
            LatestInterface.speed_bps,
            LatestInterface.rx_octets,
            LatestInterface.tx_octets,
            LatestInterface.rx_packets,
            LatestInterface.tx_packets,
            LatestInterface.utilization_percent,
            LatestInterface.errors,
            LatestInterface.discards,
            LatestInterface.polled_at,
        )).filter(LatestInterface.device_id == device_id).all()
        if row.if_index is not None
    }
    now = utc_now()
    enriched_interfaces = []
    for iface in live_interfaces[:limit]:
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
                elapsed = max((_interface_api_elapsed(now, latest.polled_at)), 0)
                if elapsed > 0:
                    from backend.snmp.statistics_engine import interface_rate_mbps
                    rx_mbps = interface_rate_mbps(float(in_octets), float(latest.rx_octets), elapsed, iface.get("speed_bps") or latest.speed_bps)
            if latest.polled_at and out_octets is not None and latest.tx_octets is not None:
                elapsed = max((_interface_api_elapsed(now, latest.polled_at)), 0)
                if elapsed > 0:
                    from backend.snmp.statistics_engine import interface_rate_mbps
                    tx_mbps = interface_rate_mbps(float(out_octets), float(latest.tx_octets), elapsed, iface.get("speed_bps") or latest.speed_bps)

            speed_bps = iface.get("speed_bps") or latest.speed_bps
            utilization = latest.utilization_percent
            if speed_bps and rx_mbps is not None and tx_mbps is not None:
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="environment")
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
def get_snmp_lldp(device_id: int, limit: int = Query(default=MAX_SNMP_TABLE_ROWS, ge=1, le=MAX_SNMP_TABLE_ROWS), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db), domain="lldp")
    col      = _collector_data(result, "lldp")
    col_data = col.get("data") or {}
    neighbors = _enrich_lldp_neighbors(db, device, (col_data.get("neighbors") or [])[:limit])
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
            "neighbor_count": len(neighbors),
            "neighbors":      neighbors,
            "local_ports":    dict(list((col_data.get("local_ports") or {}).items())[:limit]),
        },
    }


@router.get("/snmp/devices/{device_id}/routing")
def get_snmp_routing(device_id: int, limit: int = Query(default=MAX_SNMP_TABLE_ROWS, ge=1, le=MAX_SNMP_TABLE_ROWS), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db), domain="routing")
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
            "routes":            (col_data.get("routes") or [])[:limit],
        },
    }


@router.get("/snmp/devices/{device_id}/vlans")
def get_snmp_vlans(device_id: int, limit: int = Query(default=MAX_SNMP_TABLE_ROWS, ge=1, le=MAX_SNMP_TABLE_ROWS), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db), domain="vlan")
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
            "vlans":      (col_data.get("vlans") or [])[:limit],
        },
    }


@router.get("/snmp/devices/{device_id}/cdp")
def get_snmp_cdp(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db), domain="cdp")
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
def get_snmp_arp(device_id: int, limit: int = Query(default=MAX_SNMP_TABLE_ROWS, ge=1, le=MAX_SNMP_TABLE_ROWS), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    # This endpoint serves the stored snapshot and only needs the version for
    # metadata. Do not decrypt passwords on every read; that also avoids the
    # noisy cryptography deprecation warning from pysnmpcrypto.
    cred = db.query(DeviceCredential).options(
        load_only(DeviceCredential.snmp_version),
    ).filter(DeviceCredential.device_id == device_id).first()
    stored_cap = db.query(DeviceCapabilities).options(load_only(
        DeviceCapabilities.capability_detail,
    )).filter(DeviceCapabilities.device_id == device_id).first()
    stored_arp = ((stored_cap.capability_detail or {}).get("arp") or {}) if stored_cap else {}
    stored_data = stored_arp.get("data") or {}
    entries = stored_data.get("entries") or []
    # ARP snapshots usually contain the bridge interface, while VLAN IDs are
    # learned by the MAC-table collector. Join both snapshots by MAC + port
    # so the ARP table can show the real VLAN for entries such as interface 4.
    mac_snapshot = ((stored_cap.capability_detail or {}).get("mac_table") or {}) if stored_cap else {}
    mac_entries = ((mac_snapshot.get("data") or {}).get("entries") or [])
    vlan_by_mac_port: dict[tuple[str, str], list[int]] = {}
    vlan_by_port: dict[str, list[int]] = {}
    for group in ((mac_snapshot.get("data") or {}).get("port_groups") or []):
        port = str(group.get("interface") or group.get("port") or group.get("if_index") or group.get("port_id") or "")
        if port:
            vlan_by_port[port] = sorted({int(v) for v in (group.get("vlans") or []) if str(v).isdigit()})
    # ARP interface indexes can be bridge ports that have no MAC-table group.
    # Use the authoritative VLAN collector's tagged/untagged/egress port lists.
    vlan_snapshot = ((stored_cap.capability_detail or {}).get("vlan") or {}) if stored_cap else {}
    for vlan in ((vlan_snapshot.get("data") or {}).get("vlans") or []):
        vlan_id = vlan.get("vlan_id")
        if vlan_id is None:
            continue
        for port in set((vlan.get("egress_ports") or []) + (vlan.get("untagged_ports") or []) + (vlan.get("tagged_ports") or [])):
            vlan_by_port.setdefault(str(port), []).append(int(vlan_id))
    for port in list(vlan_by_port):
        vlan_by_port[port] = sorted(set(vlan_by_port[port]))
    for mac_entry in mac_entries:
        mac = _normalize_mac(mac_entry.get("mac") or mac_entry.get("mac_address"))
        port = str(mac_entry.get("interface") or mac_entry.get("port") or mac_entry.get("if_index") or "")
        vlan = mac_entry.get("vlan_id")
        if mac and port and vlan is not None:
            vlan_by_mac_port.setdefault((mac, port), []).append(int(vlan))
    enriched_entries = []
    for entry in entries:
        row = dict(entry)
        mac = _normalize_mac(row.get("mac") or row.get("mac_address"))
        port = str(row.get("interface") or row.get("if_index") or row.get("port") or "")
        vlans = vlan_by_mac_port.get((mac, port), []) or vlan_by_port.get(port, [])
        if vlans and row.get("vlan_id") is None:
            row["vlan_id"] = sorted(set(vlans))[0]
        enriched_entries.append(row)
    returned_entries = enriched_entries[:limit]
    return {
        "api_version":   "2.0",
        "ip":            device.ip_address,
        "reachable":     None,
        "snmp_version":  cred.snmp_version if cred else None,
        "vendor":        device.vendor.vendor_name if device.vendor else None,
        "device_type":   device.device_type.name if device.device_type else None,
        "hostname":      device.hostname,
        "collection_ms": None,
        "device_id":     device_id,
        "collector":     "arp",
        "supported":     stored_arp.get("supported", False),
        "timestamp":     stored_arp.get("timestamp"),
        "missing":       stored_arp.get("missing", []),
        "warnings":      stored_arp.get("warnings", []),
        "reason":        stored_arp.get("reason"),
        "data": {
            "entry_count": len(returned_entries),
            "entries":     returned_entries,
            "port_groups": (stored_data.get("port_groups") or [])[:limit],
        },
    }


@router.get("/snmp/devices/{device_id}/mac-table")
def get_snmp_mac_table(device_id: int, limit: int = Query(default=MAX_SNMP_TABLE_ROWS, ge=1, le=MAX_SNMP_TABLE_ROWS), db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    # The MAC table is DB-backed here; credential secrets are not required to
    # render it. Avoid decrypting them for every page refresh.
    cred = db.query(DeviceCredential).options(
        load_only(DeviceCredential.snmp_version),
    ).filter(DeviceCredential.device_id == device_id).first()
    stored_cap = db.query(DeviceCapabilities).options(load_only(
        DeviceCapabilities.capability_detail,
    )).filter(DeviceCapabilities.device_id == device_id).first()
    stored_mac = ((stored_cap.capability_detail or {}).get("mac_table") or {}) if stored_cap else {}
    stored_arp_snapshot = ((stored_cap.capability_detail or {}).get("arp") or {}) if stored_cap else {}
    stored_arp = stored_arp_snapshot.get("data") or {}
    col = stored_mac or {
        "collector": "mac_table",
        "supported": False,
        "reason": "MAC table has not been collected by the background monitor yet.",
        "missing": [],
    }
    col_data = col.get("data") or {}
    # The scheduler persists both domains. Never start a blocking SNMP poll in
    # a read request; this keeps page loads fast and avoids duplicate polls.
    arp_entries = stored_arp.get("entries") or []
    mac_updated_at = col.get("last_good_timestamp") or col.get("timestamp")
    arp_updated_at = stored_arp_snapshot.get("last_good_timestamp") or stored_arp_snapshot.get("timestamp")
    data_quality = "complete"
    if col.get("collection_status") not in (None, "SUCCESS"):
        data_quality = "stale"
    elif not arp_entries or stored_arp_snapshot.get("collection_status") not in (None, "SUCCESS"):
        data_quality = "partial"
    else:
        try:
            mac_time = datetime.fromisoformat(str(mac_updated_at).replace("Z", "+00:00"))
            arp_time = datetime.fromisoformat(str(arp_updated_at).replace("Z", "+00:00"))
            if mac_time.tzinfo is None:
                mac_time = mac_time.replace(tzinfo=timezone.utc)
            if arp_time.tzinfo is None:
                arp_time = arp_time.replace(tzinfo=timezone.utc)
            if abs((mac_time - arp_time).total_seconds()) > 120:
                data_quality = "stale"
        except (TypeError, ValueError):
            data_quality = "partial"
    arp_by_mac: dict[str, list[str]] = {}
    for arp_entry in arp_entries:
        mac = _normalize_mac(arp_entry.get("mac"))
        ip = arp_entry.get("ip_address") or arp_entry.get("ip")
        if mac and ip:
            arp_by_mac.setdefault(mac, []).append(str(ip))

    port_groups = []
    for group in (col_data.get("port_groups") or [])[:limit]:
        enriched = dict(group)
        canonical_macs = sorted({mac for mac in (_normalize_mac(value) for value in group.get("macs", [])) if mac})
        enriched["macs"] = [_display_mac(mac) for mac in canonical_macs]
        enriched["mac_count"] = len(canonical_macs)
        ips = list(group.get("ip_addresses") or group.get("ips") or [])
        for mac_value in canonical_macs:
            ips.extend(arp_by_mac.get(_normalize_mac(mac_value), []))
        enriched["ip_addresses"] = sorted(set(ips), key=_ip_sort_key)
        enriched["data_quality"] = data_quality if ips else "partial"
        enriched["mac_updated_at"] = mac_updated_at
        enriched["arp_updated_at"] = arp_updated_at
        port_groups.append(enriched)
    enriched_entries = []
    for entry in (col_data.get("entries") or [])[:limit]:
        enriched_entry = dict(entry)
        mac_key = _normalize_mac(entry.get("mac"))
        mapped_ips = arp_by_mac.get(mac_key, [])
        if mapped_ips:
            enriched_entry["ip_address"] = mapped_ips[0]
            enriched_entry["ip_addresses"] = mapped_ips
        enriched_entries.append(enriched_entry)
    has_last_good_data = bool(col_data.get("entries") or col_data.get("port_groups"))
    return {
        "api_version":   "2.0",
        "ip":            device.ip_address,
        "reachable":     None,
        "snmp_version":  cred.snmp_version if cred else None,
        "vendor":        device.vendor.vendor_name if device.vendor else None,
        "device_type":   device.device_type.name if device.device_type else None,
        "hostname":      device.hostname,
        "collection_ms": None,
        "device_id":     device_id,
        "collector":     "mac_table",
        # A failed refresh can retain the last good snapshot. Keep that data
        # renderable and expose the failure through collection_status/data_quality.
        "supported":     bool(col.get("supported", False) or has_last_good_data),
        "timestamp":     col.get("timestamp"),
        "collection_status": col.get("collection_status", "NOT_COLLECTED"),
        "last_good_timestamp": col.get("last_good_timestamp"),
        "missing":       col.get("missing", []),
        "warnings":      col.get("warnings", []),
        "reason":        col.get("reason"),
        "data": {
            "entry_count": col_data.get("entry_count", 0),
            "vlan_aware":  col_data.get("vlan_aware", False),
            "data_quality": data_quality,
            "mac_updated_at": mac_updated_at,
            "arp_updated_at": arp_updated_at,
            "entries":     enriched_entries,
            "port_groups": port_groups,
        },
    }


@router.get("/snmp/devices/{device_id}/inventory")
def get_snmp_inventory(device_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    device = _get_device_or_404(device_id, db)
    result = _live_collect(device, _get_credentials(device_id, db), domain="inventory")
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="health")
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="firewall")
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="wireless")
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
    result = _live_collect(device, _get_credentials(device_id, db), domain="topology")
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
            "verification_mismatches": col_data.get("verification_mismatches", []),
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
def get_snmp_topology(device_id: int | None = Query(default=None), refresh: bool = Query(default=False), db: Session = Depends(get_db), current_user: Any = Depends(require_permission("devices:read"))) -> dict[str, Any]:
    topology_observations = 0
    topology_candidates = 0
    topology_duplicates = 0
    devices_q = (
        db.query(Device)
        .options(
            load_only(
                Device.id,
                Device.hostname,
                Device.ip_address,
                Device.mac_address,
                Device.model,
                Device.status,
                Device.deleted_at,
                Device.device_type_id,
                Device.vendor_id,
            ),
            joinedload(Device.vendor).load_only(Vendor.id, Vendor.vendor_name),
            joinedload(Device.device_type).load_only(DeviceType.id, DeviceType.name),
        )
        .filter(Device.deleted_at.is_(None))
    )
    if device_id:
        devices_q = devices_q.filter(Device.id == device_id)
    accessible_site_ids = get_accessible_site_ids(current_user)
    if accessible_site_ids is not None:
        devices_q = devices_q.filter(Device.site_id.in_(accessible_site_ids) if accessible_site_ids else False)
    all_devices = devices_q.limit(200).all()
    all_device_ids = [device.id for device in all_devices]
    capability_map = {
        row.device_id: row
        for row in db.query(DeviceCapabilities)
        .filter(DeviceCapabilities.device_id.in_(all_device_ids))
        .all()
    } if all_device_ids else {}

    # A forced refresh is a rebuild, not a merge. Remove only the persisted
    # topology snapshot so stale MAC/ARP/LLDP nodes cannot survive a fresh
    # collection. Device identity, credentials, and other SNMP modules remain
    # untouched.
    if refresh:
        for capability in capability_map.values():
            detail = dict(capability.capability_detail or {})
            if "topology" in detail:
                detail.pop("topology", None)
                capability.capability_detail = detail
            capability.cap_topology = False
        db.flush()
        logger.info(
            "[TOPOLOGY-BE] cleared persisted topology snapshots before rebuild devices=%s",
            len(capability_map),
        )
    credentials_map = _get_credentials_map(all_device_ids, db)
    # Root from the default gateway first when one is known, otherwise fall
    # back to core/network infrastructure devices.
    identity_maps = _load_device_identity_maps(db, all_devices)
    gateway_devices = [
        d for d in all_devices
        if any(token in " ".join([
            d.hostname or "",
            d.model or "",
            d.vendor.vendor_name if d.vendor else "",
        ]).lower() for token in ("gateway", "gw", "default gateway", "router"))
    ]
    core_devices = [d for d in all_devices if any(token in (d.hostname or '').lower() for token in ('core', 'switch', 'sw-'))]
    exact_gateway = next((d for d in all_devices if d.ip_address in ("192.168.1.0", "192.168.100.1")), None)
    d_list = [exact_gateway] if exact_gateway else gateway_devices[:1] or core_devices[:1] or all_devices[:1]
    # An explicit refresh is a physical-topology rebuild, not a single-root
    # view. Poll every managed device so partial LLDP/CDP/FDB evidence from
    # distribution/access switches and endpoints can be assembled together.
    # Keep the normal request rooted/cached for latency and backward behavior.
    if refresh:
        d_list = all_devices
    if not refresh and d_list:
        # A live refresh may be rooted at the core switch while the normal
        # collector root is the gateway. Always return the newest persisted
        # snapshot instead of assuming d_list[0] owns the latest graph.
        cached_topology = _latest_cached_topology(capability_map) or {}
        cached_data = cached_topology.get("data") or {}
        selected_capability = next(
            (cap for cap in capability_map.values()
             if (cap.capability_detail or {}).get("topology") is cached_topology),
            None,
        )
        logger.info(
            "[TOPOLOGY-BE] GET cached selected_capability_id=%s selected_device_id=%s "
            "timestamp=%s nodes=%s links=%s",
            selected_capability.id if selected_capability else None,
            selected_capability.device_id if selected_capability else None,
            cached_topology.get("timestamp") or cached_topology.get("collected_at"),
            len(cached_data.get("nodes") or []),
            len(cached_data.get("links") or []),
        )
        if cached_data.get("nodes") or cached_data.get("links"):
            return {
                "devices": cached_data.get("nodes", []),
                "links": cached_data.get("links", []),
                "verified_only": True,
                "cached": True,
                "timestamp": cached_topology.get("timestamp"),
            }
        # A normal page load must never fall through to a live SNMP walk.
        # Return the DB inventory immediately while the explicit refresh action
        # is allowed to collect and update topology data from the device.
        inventory_nodes = []
        for device in all_devices:
            enriched = _enrich_topology_node(
                {"id": str(device.id), "hostname": device.hostname, "ip_address": device.ip_address, "status": device.status},
                device,
                identity_maps,
            )
            inventory_nodes.append({
                "id": str(device.id),
                "hostname": enriched.get("hostname"),
                "ip_address": enriched.get("ip_address"),
                "status": device.status,
                "type": enriched.get("device_type"),
                "vendor": enriched.get("vendor"),
                "model": enriched.get("model"),
                "sys_name": enriched.get("sys_name"),
                "sys_descr": enriched.get("sys_descr"),
                "mac_address": enriched.get("mac_address"),
                "display_name": enriched.get("display_name"),
            })
        logger.info(
            "[TOPOLOGY-BE] GET inventory fallback selected_capability_id=None "
            "selected_device_id=None timestamp=None nodes=%s links=0",
            len(inventory_nodes),
        )
        return {
            "devices": inventory_nodes,
            "links": [],
            "verified_only": True,
            "cached": True,
            "timestamp": None,
        }
    nodes: dict[str, dict[str, Any]] = {}
    for d in d_list:
        enriched = _enrich_topology_node(
            {"id": str(d.id), "hostname": d.hostname, "ip_address": d.ip_address, "status": d.status},
            d,
            identity_maps,
        )
        nodes[str(d.id)] = {
            "id": str(d.id),
            "hostname": enriched.get("hostname"),
            "ip_address": enriched.get("ip_address"),
            "status": d.status,
            "type": enriched.get("device_type"),
            "vendor": enriched.get("vendor"),
            "model": enriched.get("model"),
            "sys_name": enriched.get("sys_name"),
            "sys_descr": enriched.get("sys_descr"),
            "mac_address": enriched.get("mac_address"),
            "display_name": enriched.get("display_name"),
        }
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    # Topology used to poll every device serially. A slow/unreachable device
    # therefore blocked the whole page behind SNMP timeout + retries. Fetch
    # credentials before starting workers and collect devices concurrently.
    poll_targets = [(d, credentials_map.get(d.id)) for d in d_list]
    def collect_topology(target: tuple[Device, DeviceCredential | None]) -> tuple[Device, dict[str, Any]]:
        device, credential = target
        return device, _live_collect(device, credential, domain="topology")

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(poll_targets)))) as executor:
        future_targets = {executor.submit(collect_topology, target): target for target in poll_targets}
        for future in as_completed(future_targets):
          target_device = future_targets[future][0]
          try:
            d, result = future.result()
            topology = (result.get("collectors") or {}).get("topology") or {}
            data = topology.get("data") or {}
            # Persist only a successful topology result. An empty/failing
            # poll must not erase the last known graph.
            if topology.get("supported") and (data.get("nodes") or data.get("links")):
                cap = capability_map.get(d.id)
                if cap is None:
                    cap = DeviceCapabilities(device_id=d.id, capability_detail={})
                    db.add(cap)
                    capability_map[d.id] = cap
                _persist_topology_snapshot(
                    db,
                    d.id,
                    data.get("nodes") or [],
                    data.get("links") or [],
                    topology.get("timestamp") or datetime.utcnow().isoformat(),
                    source="collector",
                )
            else:
                cached = capability_map.get(d.id)
                data = ((cached.capability_detail or {}).get("topology") or {}).get("data") or {} if cached else {}
            topology_nodes = data.get("nodes", [])
            node_alias: dict[str, str] = {}
            local_topology_id = str(topology_nodes[0].get("id")) if topology_nodes else None
            if local_topology_id:
                node_alias[local_topology_id] = str(d.id)
            for node in topology_nodes:
                node_id = str(node.get("id") or "")
                if node_id and node_id not in nodes:
                    node_ip = node.get("ip_address") or node.get("ip")
                    node_mac = node.get("mac_address") or node.get("mac")
                    normalized_node_mac = str(node_mac or '').replace(':', '').replace('-', '').replace('.', '').lower()
                    matching_device = next((known for known in all_devices if
                        (node_ip and known.ip_address == node_ip) or
                        (normalized_node_mac and str(getattr(known, "mac_address", "") or '').replace(':', '').replace('-', '').replace('.', '').lower() == normalized_node_mac)), None)
                    if node_id == local_topology_id:
                        matching_device = d
                    if matching_device is None and normalized_node_mac:
                        interface_identity = identity_maps["by_mac"].get(_normalize_mac(node_mac))
                        if interface_identity:
                            matching_device = interface_identity.get("device")
                    canonical_id = str(matching_device.id) if matching_device else node_id
                    node_alias[node_id] = canonical_id
                    enriched = _enrich_topology_node(node, matching_device, identity_maps)
                    nodes[canonical_id] = {
                        "id": canonical_id,
                        "hostname": enriched.get("hostname"),
                        "ip_address": enriched.get("ip_address"),
                        "status": "online",
                        "type": enriched.get("device_type"),
                        "vendor": enriched.get("vendor"),
                        "model": enriched.get("model"),
                        "sys_name": enriched.get("sys_name"),
                        "sys_descr": enriched.get("sys_descr"),
                        "mac_address": enriched.get("mac_address"),
                        "display_name": enriched.get("display_name"),
                    }
            for link in data.get("links", []):
                topology_observations += 1
                topology_candidates += 1
                link = {**link,
                        "source_node": node_alias.get(str(link.get("source_node")), str(link.get("source_node"))),
                        "target_node": node_alias.get(str(link.get("target_node")), str(link.get("target_node")))}
                key = (str(link.get("source_node")), str(link.get("target_node")),
                       str(link.get("source_port")), str(link.get("target_port")))
                if (link.get("verified") or link.get("confidence") == "INFERRED") and key not in seen:
                    seen.add(key)
                    links.append({**link, "verified": True})
                elif link.get("verified") or link.get("confidence") == "INFERRED":
                    topology_duplicates += 1
          except Exception:
            cached = capability_map.get(target_device.id)
            data = ((cached.capability_detail or {}).get("topology") or {}).get("data") or {} if cached else {}
            for node in data.get("nodes", []):
                node_id = str(node.get("id") or "")
                if node_id and node_id not in nodes:
                    enriched = _enrich_topology_node(node, None, identity_maps)
                    nodes[node_id] = {
                        "id": node_id,
                        "hostname": enriched.get("hostname"),
                        "ip_address": enriched.get("ip_address"),
                        "status": "online",
                        "type": enriched.get("device_type"),
                        "vendor": enriched.get("vendor"),
                        "model": enriched.get("model"),
                        "sys_name": enriched.get("sys_name"),
                        "sys_descr": enriched.get("sys_descr"),
                        "mac_address": enriched.get("mac_address"),
                        "display_name": enriched.get("display_name"),
                    }
            for link in data.get("links", []):
                if link.get("verified"):
                    links.append({**link, "verified": True})
            continue
    db.commit()
    logger.info(
        "[TOPOLOGY-BE] GET live/assembled selected_device_ids=%s timestamp=%s nodes=%s links=%s",
        [device.id for device in d_list],
        None,
        len(nodes),
        len(links),
    )
    logger.info(
        "PHYSICAL_TOPOLOGY_BUILD devices=%s interfaces=%s lldpObservations=%s "
        "cdpObservations=%s fdbEntries=%s arpEntries=%s candidates=%s confirmed=%s "
        "inferred=%s ambiguous=%s unmanaged=%s discarded=%s duplicates=%s",
        len(nodes), 0, topology_observations, 0, 0, 0, topology_candidates,
        len(links), 0, 0, 0, 0, topology_duplicates,
    )
    return {"devices": list(nodes.values()), "links": links, "verified_only": True, "timestamp": datetime.utcnow().isoformat()}


@router.get("/snmp/topology/stream")
async def stream_snmp_topology_updates(
    request: Request,
    _: Any = Depends(require_permission("devices:read")),
) -> StreamingResponse:
    """Notify every client when shared topology or inventory state changes."""
    async def events():
        previous_revision = ""
        while not await request.is_disconnected():
            with SessionLocal() as stream_db:
                state = _topology_revision(stream_db)
            if state["revision"] != previous_revision:
                previous_revision = state["revision"]
                state["updated_at"] = state["updated_at"] or datetime.now(timezone.utc).isoformat()
                yield f"event: topology\ndata: {json.dumps(state)}\n\n"
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/snmp/topology/snapshot")
def persist_snmp_topology_snapshot(
    payload: TopologySnapshotPayload,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Persist a successfully assembled live topology for future GETs."""
    _get_device_or_404(payload.device_id, db)
    persisted = _persist_topology_snapshot(
        db,
        payload.device_id,
        payload.devices,
        payload.links,
        payload.collected_at,
        source=payload.source,
    )
    db.commit()
    return {"persisted": persisted, "collected_at": payload.collected_at}


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
async def get_device_monitoring_configs(
    device_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> list[dict[str, Any]]:
    """Get all monitoring configurations for a device."""
    from backend.services.snmp_polling import get_polling_scheduler
    scheduler = await get_polling_scheduler()
    return await scheduler.get_device_jobs(device_id)


def _notify_monitoring_started(device_id: int, module: str, interval_seconds: int) -> None:
    from backend.database.session import SessionLocal
    from backend.services.alerting import create_operational_alert
    with SessionLocal() as db:
        create_operational_alert(
            db, title=f"Monitoring Started: {module}",
            description=f"SNMP {module} monitoring started for device {device_id} at {interval_seconds}s interval.",
            device_id=device_id,
        )
        db.commit()


@router.post("/snmp/devices/{device_id}/monitoring/{module}/start")
async def start_module_monitoring(
    device_id: int,
    module: str,
    payload: MonitoringConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Start monitoring a specific module on a device."""
    from backend.services.snmp_polling import get_polling_scheduler, ALLOWED_INTERVALS
    from backend.services.snmp_poll_guard import poll_guard
    if payload.interval_seconds not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Allowed: {ALLOWED_INTERVALS}")

    # Validate module is supported
    from backend.models.identity import DeviceCapabilities
    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == device_id).first()
    if cap:
        cap_map = cap.to_map()
        if not cap_map.get(module, False):
            raise HTTPException(status_code=400, detail=f"Module {module} not supported by this device")

    guard = poll_guard(device_id, module, blocking=False)
    acquired = guard.__enter__()
    if not acquired:
        guard.__exit__(None, None, None)
        raise HTTPException(status_code=409, detail="Poll or monitoring start already in progress for this device and module")
    try:
        scheduler = await get_polling_scheduler()
        config = await scheduler.add_job(device_id, module, payload.interval_seconds)
    finally:
        guard.__exit__(None, None, None)
    background_tasks.add_task(_notify_monitoring_started, device_id, module, payload.interval_seconds)
    return {
        "device_id": config.device_id,
        "module_name": config.module_name,
        "enabled": config.enabled,
        "interval_seconds": config.interval_seconds,
        "status": config.status,
        "message": f"Monitoring started for {module}",
    }


@router.post("/snmp/devices/{device_id}/monitoring/{module}/stop")
async def stop_module_monitoring(
    device_id: int,
    module: str,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Stop monitoring a specific module on a device."""
    from backend.services.snmp_polling import get_polling_scheduler
    scheduler = await get_polling_scheduler()
    stopped = await scheduler.stop_job(device_id, module)
    return {
        "device_id": device_id,
        "module_name": module,
        "stopped": stopped,
        "message": f"Monitoring stopped for {module}" if stopped else f"No monitoring job found for {module}",
    }


@router.put("/snmp/devices/{device_id}/monitoring/{module}")
async def update_module_monitoring(
    device_id: int,
    module: str,
    payload: MonitoringConfigUpdateRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:update")),
) -> dict[str, Any]:
    """Update monitoring configuration (interval, enabled) for a module."""
    from backend.services.snmp_polling import get_polling_scheduler, ALLOWED_INTERVALS
    if payload.interval_seconds is not None and payload.interval_seconds not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Allowed: {ALLOWED_INTERVALS}")

    scheduler = await get_polling_scheduler()

    if payload.interval_seconds is not None:
        updated = await scheduler.update_job_interval(device_id, module, payload.interval_seconds)
        if not updated:
            raise HTTPException(status_code=404, detail="Monitoring config not found")

    status = await scheduler.get_job_status(device_id, module)
    if not status:
        raise HTTPException(status_code=404, detail="Monitoring config not found")

    # Handle enable/disable
    if payload.enabled is not None:
        if payload.enabled:
            # Start if not running
            if status["status"] != "running":
                await scheduler.add_job(device_id, module, status["interval_seconds"])
        else:
            # Stop if running
            if status["status"] == "running":
                await scheduler.stop_job(device_id, module)
        status = await scheduler.get_job_status(device_id, module)

    return status


@router.get("/snmp/devices/{device_id}/monitoring/{module}/status")
async def get_module_monitoring_status(
    device_id: int,
    module: str,
    db: Session = Depends(get_db),
    _: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Get monitoring status for a specific module."""
    from backend.services.snmp_polling import get_polling_scheduler
    scheduler = await get_polling_scheduler()
    status = await scheduler.get_job_status(device_id, module)
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
    from backend.cache.redis_cache import get_json, set_json
    cache_key = f"nms:snmp:device:{device_id}:metrics-latest:v1"
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached
    # These tables intentionally remain separate, but one read-only statement
    # avoids five independent round trips for the same device.
    metrics = db.execute(text("""
        SELECT
            (
                SELECT row_to_json(cpu_row)
                FROM (
                    SELECT utilization_percent, per_core, load_avg, polled_at
                    FROM latest_cpu
                    WHERE device_id = :device_id
                    LIMIT 1
                ) AS cpu_row
            ) AS cpu,
            (
                SELECT row_to_json(memory_row)
                FROM (
                    SELECT total_bytes, used_bytes, free_bytes, cached_bytes,
                           buffer_bytes, swap_total, swap_free,
                           utilization_percent, polled_at
                    FROM latest_memory
                    WHERE device_id = :device_id
                    LIMIT 1
                ) AS memory_row
            ) AS memory,
            COALESCE(
                (
                    SELECT json_agg(row_to_json(storage_row))
                    FROM (
                        SELECT volume_id, mount_name, total_bytes, used_bytes,
                               free_bytes, utilization_percent, type_label, polled_at
                        FROM latest_storage
                        WHERE device_id = :device_id
                    ) AS storage_row
                ),
                '[]'::json
            ) AS storage,
            COALESCE(
                (
                    SELECT json_agg(row_to_json(interface_row))
                    FROM (
                        SELECT interface_id, if_index, name, oper_status,
                               admin_status, speed_bps, rx_mbps, tx_mbps,
                               rx_octets, tx_octets, rx_packets, tx_packets,
                               errors, discards, utilization_percent, polled_at
                        FROM latest_interface
                        WHERE device_id = :device_id
                    ) AS interface_row
                ),
                '[]'::json
            ) AS interfaces,
            COALESCE(
                (
                    SELECT json_agg(row_to_json(environment_row))
                    FROM (
                        SELECT sensor_id, sensor_name, sensor_type, value,
                               unit, status, polled_at
                        FROM latest_environment
                        WHERE device_id = :device_id
                    ) AS environment_row
                ),
                '[]'::json
            ) AS environment
    """), {"device_id": device_id}).mappings().one()
    cpu = metrics["cpu"]
    mem = metrics["memory"]
    storage = metrics["storage"] or []
    interfaces = metrics["interfaces"] or []
    env = metrics["environment"] or []

    def _iso(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else value

    payload = {
        "device_id": device_id,
        "cpu": {
            "utilization_percent": cpu.get("utilization_percent"),
            "per_core": cpu.get("per_core"),
            "load_avg": cpu.get("load_avg"),
            "polled_at": _iso(cpu.get("polled_at")),
        } if cpu else None,
        "memory": {
            "total_bytes": mem.get("total_bytes"),
            "used_bytes": mem.get("used_bytes"),
            "free_bytes": mem.get("free_bytes"),
            "cached_bytes": mem.get("cached_bytes"),
            "buffer_bytes": mem.get("buffer_bytes"),
            "swap_total": mem.get("swap_total"),
            "swap_free": mem.get("swap_free"),
            "utilization_percent": mem.get("utilization_percent"),
            "polled_at": _iso(mem.get("polled_at")),
        } if mem else None,
        "storage": [
            {
                "volume_id": s["volume_id"],
                "mount_name": s["mount_name"],
                "total_bytes": s["total_bytes"],
                "used_bytes": s["used_bytes"],
                "free_bytes": s["free_bytes"],
                "utilization_percent": s["utilization_percent"],
                "type_label": s["type_label"],
                "polled_at": _iso(s["polled_at"]),
            }
            for s in storage
        ],
        "interfaces": [
            {
                "interface_id": i["interface_id"],
                "if_index": i["if_index"],
                "name": i["name"],
                "oper_status": i["oper_status"],
                "admin_status": i["admin_status"],
                "speed_bps": i["speed_bps"],
                "rx_mbps": i["rx_mbps"],
                "tx_mbps": i["tx_mbps"],
                "rx_octets": i["rx_octets"],
                "tx_octets": i["tx_octets"],
                "rx_packets": i["rx_packets"],
                "tx_packets": i["tx_packets"],
                "errors": i["errors"],
                "discards": i["discards"],
                "utilization_percent": i["utilization_percent"],
                "polled_at": _iso(i["polled_at"]),
            }
            for i in interfaces
        ],
        "environment": [
            {
                "sensor_id": e["sensor_id"],
                "sensor_name": e["sensor_name"],
                "sensor_type": e["sensor_type"],
                "value": e["value"],
                "unit": e["unit"],
                "status": e["status"],
                "polled_at": _iso(e["polled_at"]),
            }
            for e in env
        ],
    }
    set_json(cache_key, payload)
    return payload


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
    interfaces = db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()
    known_indexes = {item.if_index for item in interfaces}
    identity_interfaces = (
        db.query(DeviceInterface)
        .filter(
            DeviceInterface.device_id == device_id,
            ~DeviceInterface.if_index.in_(known_indexes),
        )
        .order_by(DeviceInterface.if_index.asc())
        .all()
        if known_indexes
        else db.query(DeviceInterface)
        .filter(DeviceInterface.device_id == device_id)
        .order_by(DeviceInterface.if_index.asc())
        .all()
    )
    latest_rows = [
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
    latest_rows.extend(
        {
            "interface_id": i.if_index,
            "if_index": i.if_index,
            "name": i.name,
            "oper_status": i.status,
            "admin_status": "UNKNOWN",
            "speed_bps": i.speed_bps,
            "rx_mbps": None,
            "tx_mbps": None,
            "rx_octets": None,
            "tx_octets": None,
            "rx_packets": None,
            "tx_packets": None,
            "errors": None,
            "discards": None,
            "utilization_percent": None,
            "last_poll": None,
        }
        for i in identity_interfaces
    )
    return latest_rows


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

def _load_device_list_metadata(
    db: Session,
    device_ids: list[int],
    DeviceIdentity: Any,
    MonitoringConfig: Any,
) -> tuple[dict[int, DeviceCredential], dict[int, Any], dict[int, list[Any]]]:
    """Load page metadata in one batched read instead of three N+1-style reads."""
    if not device_ids:
        return {}, {}, {}

    rows = db.query(DeviceCredential, DeviceIdentity, MonitoringConfig).select_from(Device).outerjoin(
        DeviceCredential, DeviceCredential.device_id == Device.id,
    ).outerjoin(
        DeviceIdentity, DeviceIdentity.device_id == Device.id,
    ).outerjoin(
        MonitoringConfig, MonitoringConfig.device_id == Device.id,
    ).filter(Device.id.in_(device_ids)).order_by(DeviceCredential.id.asc()).all()

    credentials_by_device: dict[int, DeviceCredential] = {}
    identities: dict[int, Any] = {}
    configs_by_device: dict[int, list[Any]] = {}
    config_ids_by_device: dict[int, set[int]] = {}
    for credential, identity, config in rows:
        if credential is not None:
            credentials_by_device.setdefault(credential.device_id, credential)
        if identity is not None:
            identities[identity.device_id] = identity
        if config is not None:
            seen = config_ids_by_device.setdefault(config.device_id, set())
            if config.id not in seen:
                seen.add(config.id)
                configs_by_device.setdefault(config.device_id, []).append(config)
    return credentials_by_device, identities, configs_by_device

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
    current_user: Any = Depends(require_permission("devices:read")),
) -> dict[str, Any]:
    """Optimized paginated device list with all info needed for the device list page."""
    from backend.models.identity import DeviceIdentity
    from backend.models.snmp import MonitoringConfig
    from sqlalchemy import or_

    query = (
        db.query(Device)
        .options(
            load_only(
                Device.id,
                Device.hostname,
                Device.ip_address,
                Device.model,
                Device.serial_number,
                Device.firmware_version,
                Device.mac_address,
                Device.status,
                Device.last_seen,
                Device.deleted_at,
                Device.device_type_id,
                Device.vendor_id,
            ),
            joinedload(Device.vendor).load_only(Vendor.id, Vendor.vendor_name),
            joinedload(Device.device_type).load_only(DeviceType.id, DeviceType.name),
        )
        .filter(Device.deleted_at.is_(None))
    )
    accessible_site_ids = get_accessible_site_ids(current_user)
    if accessible_site_ids is not None:
        query = query.filter(Device.site_id.in_(accessible_site_ids) if accessible_site_ids else False)

    # Show every active device. Some discovery/import flows create the device
    # row before credentials are attached; those devices must remain visible.

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
            # Match the status exposed in the response below. A device may
            # have been created by monitoring/import and verified later, so
            # discovery_source alone must not hide a valid SNMP identity.
            query = query.filter(
                (DeviceIdentity.vendor.isnot(None))
                | (DeviceIdentity.sys_name.isnot(None))
                | (DeviceIdentity.sys_object_id.isnot(None))
            )
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
    device_ids = [device.id for device in devices]
    credentials_by_device, identities, configs_by_device = _load_device_list_metadata(
        db, device_ids, DeviceIdentity, MonitoringConfig,
    )

    # Build response with all needed data
    items = []
    for d in devices:
        di = identities.get(d.id)
        configs = configs_by_device.get(d.id, [])
        modules_monitored = sum(1 for c in configs if c.enabled and c.status == "running")

        vendor_name = d.vendor.vendor_name if d.vendor else (di.vendor if di else None)
        snmp_status_val = (
            "verified"
            if di and (di.vendor or di.sys_name or di.sys_object_id)
            else "unknown"
        )
        primary_credential = credentials_by_device.get(d.id)
        identity_hostname = (
            di.hostname
            if di and di.hostname and di.hostname.strip().lower() not in {"unknown", "unknown device"}
            else None
        )
        resolved_hostname = _first_non_empty(
            d.hostname,
            identity_hostname,
            di.sys_name if di else None,
            d.ip_address,
        )
        identity_macs = di.mac_addresses if di and isinstance(di.mac_addresses, list) else []
        resolved_mac = _first_non_empty(
            d.mac_address,
            next((str(mac) for mac in identity_macs if mac), None),
        )

        items.append({
            "id": d.id,
            "name": resolved_hostname,
            "ip_address": d.ip_address,
            "hostname": resolved_hostname,
            "device_type": d.device_type.name if d.device_type else None,
            "model": d.model,
            "serial_number": d.serial_number,
            "firmware": d.firmware_version,
            "firmware_version": d.firmware_version,
            "mac_address": resolved_mac,
            "topology_metadata": d.topology_metadata or {},
            "status": d.status,
            "snmp_version": primary_credential.snmp_version if primary_credential else None,
            "snmp_status": snmp_status_val,
            **derive_monitoring_state(d, configs),
            "monitoring_status": d.monitoring_status,
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
    from backend.models.snmp import MonitoringConfig, LatestCPU, LatestMemory, LatestStorage, LatestInterface, LatestEnvironment, PollingHistory
    from backend.models import Interface, Vendor, DeviceType

    device = (
        db.query(Device)
        .options(
            load_only(
                Device.id,
                Device.hostname,
                Device.ip_address,
                Device.model,
                Device.serial_number,
                Device.firmware_version,
                Device.mac_address,
                Device.status,
                Device.monitoring_status,
                Device.last_seen,
                Device.created_at,
                Device.uptime_seconds,
                Device.deleted_at,
                Device.vendor_id,
                Device.device_type_id,
            ),
            joinedload(Device.vendor).load_only(Vendor.id, Vendor.vendor_name),
            joinedload(Device.device_type).load_only(DeviceType.id, DeviceType.name),
        )
        .filter(Device.id == device_id, Device.deleted_at.is_(None))
        .first()
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    di = (
        db.query(DeviceIdentity)
        .filter(DeviceIdentity.device_id == device_id)
        .first()
    )
    dc = (
        db.query(DeviceCapabilities)
        .filter(DeviceCapabilities.device_id == device_id)
        .first()
    )
    configs = (
        db.query(MonitoringConfig)
        .options(load_only(
            MonitoringConfig.module_name,
            MonitoringConfig.enabled,
            MonitoringConfig.interval_seconds,
            MonitoringConfig.status,
            MonitoringConfig.last_started_at,
            MonitoringConfig.last_stopped_at,
            MonitoringConfig.last_poll_at,
            MonitoringConfig.next_poll_at,
            MonitoringConfig.error_message,
            MonitoringConfig.device_id,
        ))
        .filter(MonitoringConfig.device_id == device_id)
        .all()
    )
    cred = (
        db.query(DeviceCredential)
        .options(load_only(DeviceCredential.device_id, DeviceCredential.snmp_version))
        .filter(DeviceCredential.device_id == device_id)
        .first()
    )

    # Latest metrics
    cpu = db.query(LatestCPU).filter(LatestCPU.device_id == device_id).first()
    mem = db.query(LatestMemory).filter(LatestMemory.device_id == device_id).first()
    storage = db.query(LatestStorage).filter(LatestStorage.device_id == device_id).all()
    interfaces = db.query(LatestInterface).filter(LatestInterface.device_id == device_id).all()
    env = db.query(LatestEnvironment).filter(LatestEnvironment.device_id == device_id).all()
    capabilities = dict(dc.to_map() if dc else {})
    # Persisted latest data is authoritative for modules already collected.
    # Keep capability metadata as-is, but do not hide available stored data
    # when a previous live probe marked a module as unsupported.
    if cpu:
        capabilities["cpu"] = True
    if mem:
        capabilities["memory"] = True
    if storage:
        capabilities["storage"] = True
    if interfaces:
        capabilities["interfaces"] = True
    if env:
        capabilities["environment"] = True

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
            "mac_address": _known_device_mac(device, db),
            "topology_metadata": device.topology_metadata or {},
            "status": device.status,
            "monitoring_status": device.monitoring_status,
            **derive_monitoring_state(device, configs),
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "uptime_seconds": device.uptime_seconds,
        },
        "snmp": {
            "version": cred.snmp_version if cred else None,
            "port": 161,
            "status": (
                "verified"
                if di and (di.vendor or di.sys_name or di.sys_object_id)
                else "unknown"
            ),
            "last_test_at": None,
        },
        "capabilities": capabilities,
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
