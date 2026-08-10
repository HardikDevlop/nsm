"""FastAPI router that exposes the backend-owned discovery / monitoring / analytics modules.

The runtime logic is now bundled inside the backend workspace so the old
``icmp_discovery/`` folder is no longer required for the live API.

No RBAC on these endpoints by default: discovery probes are operational
tasks and historically the Flask service was public. If you want RBAC,
wrap individual handlers with ``Depends(require_permission("discovery:execute"))``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["Discovery / Monitoring (modules)"])
logger = logging.getLogger(__name__)


# ----------------------------- Request schemas ----------------------------- #


class IpsRequest(BaseModel):
    ips: list[str] = Field(default_factory=list)
    ip: str | None = None
    subnet: str | None = None
    max_hosts: int = Field(default=1024, ge=1, le=65536)
    timeout_ms: int = 1000
    timeout_seconds: float = 0.75
    ports: list[int] | None = None
    communities: list[str] | None = None
    snmp_version: str = "v2c"
    username: str | None = None
    auth_protocol: str | None = None
    auth_password: str | None = None
    privacy_protocol: str | None = None
    privacy_password: str | None = None
    security_level: str | None = None
    open_ports: dict[str, str] | None = None


class ProfileRequest(BaseModel):
    signals: dict[str, Any]


class SyslogRequest(BaseModel):
    message: str
    source_ip: str = "unknown"


class TrapRequest(BaseModel):
    payload: str
    source_ip: str = "unknown"


class AlertsEvaluateRequest(BaseModel):
    samples: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


class EventsFromSamplesRequest(BaseModel):
    samples: list[dict[str, Any]] = Field(default_factory=list)


class EventsNormalizeRequest(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


class TopologyRequest(BaseModel):
    devices: list[dict[str, Any]] | None = None


class TargetRequest(BaseModel):
    target: str
    limit: int | None = None


class MacLookupRequest(BaseModel):
    mac: str | None = None
    macs: list[str] | None = None


class ScanPlanRequest(BaseModel):
    network_range: str
    max_hosts: int = 1024


class ChunkedScanRequest(BaseModel):
    """Request body for starting a chunked discovery scan."""
    network_range: str
    site_id: int | None = None
    ports: list[int] = [22, 80, 443, 161, 162, 8080, 8443]
    scan_icmp: bool = True
    scan_ports: bool = True
    scan_snmp: bool = False
    snmp_community: str = "public"
    timeout_ms: int = 700
    max_hosts: int = 254
    chunk_size: int = 25
    modules: list[str] = ["ip_discovery", "icmp_discovery"]


class AddDevicesRequest(BaseModel):
    """Request body for adding discovered devices to the database."""
    devices: list[dict[str, Any]]
    site_id: int | None = None


class MonitorDeviceRequest(BaseModel):
    """Request body for starting/stopping monitoring on a device."""
    ip: str
    hostname: str | None = None
    vendor: str | None = None
    mac_address: str | None = None
    site_id: int | None = None
    device_id: int | None = None


class MonitorAllRequest(BaseModel):
    """Request body for starting/stopping monitoring on multiple devices."""
    devices: list[dict[str, Any]]


class CheckStoredRequest(BaseModel):
    """Check which IPs from a list are already stored in the database."""
    ips: list[str]


class VendorAddRequest(BaseModel):
    prefix: str
    vendor: str


# ----------------------------- Helpers ------------------------------------ #


def _ips(body: IpsRequest) -> list[str]:
    out = list(body.ips or [])
    if not out and body.ip:
        out = [body.ip]
    return [str(x) for x in out if x]


def _load_inventory() -> dict[str, Any]:
    from config import JSON_FILE  # type: ignore  (resolved from hardik root)

    path = Path(__file__).resolve().parents[2] / JSON_FILE
    if not path.exists():
        return {"devices": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ----------------------------- Meta --------------------------------------- #


@router.get("/discovery/local-subnet")
def detect_local_subnet():
    """Auto-detect the local machine's subnet (CIDR notation).

    Uses `ip route` on Linux/macOS or `ipconfig` on Windows to find the
    primary network interface's subnet. Falls back to 192.168.1.0/24.
    """
    import platform
    import re
    import ipaddress

    fallback = "192.168.1.0/24"
    try:
        if platform.system().lower() == "windows":
            import subprocess
            out = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                m = re.search(r"IPv4 Address.*:\s*(\d+\.\d+\.\d+\.\d+)", line)
                if m and not m.group(1).startswith("127."):
                    ip = m.group(1)
                    return {"subnet": f"{ip.rsplit('.', 1)[0]}.0/24", "ip": ip}
        else:
            import subprocess
            route_out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
            dev_match = re.search(r"dev\s+(\S+)", route_out)
            if dev_match:
                iface = dev_match.group(1)
                addr_out = subprocess.run(["ip", "addr", "show", iface], capture_output=True, text=True, timeout=5).stdout
                ip_match = re.search(r"inet\s+(\S+)", addr_out)
                if ip_match:
                    cidr = ip_match.group(1)
                    net = ipaddress.ip_network(cidr, strict=False)
                    local_ip = cidr.split("/")[0]
                    return {"subnet": str(net), "ip": local_ip}
    except Exception:
        pass
    return {"subnet": fallback, "ip": None}


@router.get("/discovery/modules")
def discovery_modules():
    """List all registered discovery / monitoring / analytics modules."""
    return {
        "modules": [
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
        ],
    }


# ----------------------------- IP Discovery ------------------------------- #


@router.post("/discovery/ip")
def discovery_ip(payload: TargetRequest):
    from discovery_modules.ip_discovery import IPDiscovery  # type: ignore

    try:
        result = IPDiscovery().discover(payload.target, limit=payload.limit)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {
        "target": result.target,
        "version": result.version,
        "total_hosts": result.total_hosts,
        "candidates": result.ips,
        "candidate_count": len(result.ips),
    }


# ----------------------------- ICMP --------------------------------------- #


@router.post("/discovery/icmp")
def discovery_icmp(payload: IpsRequest):
    from discovery_modules.icmp_discovery import ICMPDiscovery  # type: ignore

    ips = _ips(payload)
    if not ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ips[] is required")
    results = ICMPDiscovery(timeout_ms=payload.timeout_ms).discover(ips)
    return {"count": len(results), "results": results}


# ----------------------------- TCP ---------------------------------------- #


@router.post("/discovery/tcp")
def discovery_tcp(payload: IpsRequest):
    from discovery_modules.tcp_discovery import TCPDiscovery  # type: ignore

    ips = _ips(payload)
    if not ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ips[] is required")
    scanner = TCPDiscovery(ports=payload.ports, timeout_seconds=payload.timeout_seconds)
    results = {ip: scanner.scan_host(ip) for ip in ips}
    return {"count": len(results), "results": results}


# ----------------------------- ARP ---------------------------------------- #


@router.post("/discovery/arp")
def discovery_arp(payload: IpsRequest):
    from discovery_modules.arp_discovery import ARPDiscovery  # type: ignore

    ips = _ips(payload)
    if not ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ips[] is required")
    arp = ARPDiscovery()
    results = [arp.collect(ip) for ip in ips]
    return {"count": len(results), "results": results}


# ----------------------------- DNS ---------------------------------------- #


@router.post("/discovery/dns")
def discovery_dns(payload: IpsRequest):
    from discovery_modules.dns_discovery import DNSDiscovery  # type: ignore

    ips = _ips(payload)
    if not ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ips[] is required")
    dns = DNSDiscovery()
    results = [dns.resolve(ip) for ip in ips]
    return {"count": len(results), "results": results}


# ----------------------------- HTTP banner -------------------------------- #


@router.post("/discovery/http")
def discovery_http(payload: IpsRequest):
    from discovery_modules.http_discovery import HTTPDiscovery  # type: ignore

    if not payload.ip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ip is required")
    banners = HTTPDiscovery(timeout_seconds=payload.timeout_seconds).discover(
        payload.ip, payload.open_ports or {}
    )
    return {"ip": payload.ip, "banners": banners}


# ----------------------------- SNMP --------------------------------------- #


@router.post("/discovery/snmp")
def discovery_snmp(payload: IpsRequest):
    from backend.snmp.collector import SNMPDiscovery
    from backend.database.session import SessionLocal
    from backend.models import Device, DeviceCredential, Event, Interface
    from backend.utils.crypto import encrypt_secret
    from datetime import datetime

    ips = _ips(payload)
    if payload.subnet:
        try:
            network = ipaddress.ip_network(payload.subnet, strict=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid subnet: {exc}")
        hosts = list(network.hosts())
        if len(hosts) > payload.max_hosts:
            raise HTTPException(status_code=400, detail=f"subnet has {len(hosts)} hosts; max_hosts is {payload.max_hosts}")
        ips = [str(host) for host in hosts]
    if not ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ips[] or subnet is required")
    snmp = SNMPDiscovery(
        communities=payload.communities,
        timeout_seconds=payload.timeout_seconds,
        snmp_version=payload.snmp_version,
        username=payload.username,
        auth_protocol=payload.auth_protocol,
        auth_password=payload.auth_password,
        privacy_protocol=payload.privacy_protocol,
        privacy_password=payload.privacy_password,
        security_level=payload.security_level,
    )
    with ThreadPoolExecutor(max_workers=min(64, len(ips))) as pool:
        scanned = pool.map(snmp.collect, ips)
    results = {ip: result for ip, result in zip(ips, scanned) if result.get("snmp_enabled")}
    if not results:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No SNMP response received before timeout. Check community string, credentials, and that SNMP is enabled on target devices.",
        )

    # Persist successful discovery before returning the response.
    db = SessionLocal()
    try:
        for ip, result in results.items():
            # sysName is optional on cameras and other embedded agents;
            # devices.hostname is NOT NULL, so establish a stable fallback
            # before SQLAlchemy flushes the row.
            raw_hostname = result.get("hostname") or result.get("sysName")
            hostname = str(raw_hostname) if raw_hostname and str(raw_hostname).lower() not in {"(none)", "none", "unknown"} else f"device-{ip.replace('.', '-')}"

            # UPSERT: find existing device or create a new one.
            # Never delete ICMP-discovered or other existing devices.
            device = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.is_(None)).first()
            if device is None:
                # Check for soft-deleted device with same IP - if it exists, undelete it
                soft_deleted = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.isnot(None)).first()
                if soft_deleted:
                    # Undelete the device and update its hostname
                    device = soft_deleted
                    device.deleted_at = None
                else:
                    # Create new device
                    device = Device(ip_address=ip, hostname=hostname)
                db.add(device)
                db.flush()
            
            # Update hostname only if the new one is meaningful
            if hostname and hostname != f"device-{ip.replace('.', '-')}":
                device.hostname = hostname
            device.model = result.get("model")
            device.firmware_version = result.get("firmware")
            interface_payload = result.get("interfaces") or {}
            interface_rows = interface_payload.get("interfaces", []) if isinstance(interface_payload, dict) else interface_payload
            interface_rows = interface_rows if isinstance(interface_rows, list) else []
            # Upsert IF-MIB interface rows — match by device_id + interface_name
            for row in interface_rows:
                if not isinstance(row, dict):
                    continue
                iface_name = str(row.get("name") or f"ifIndex-{row.get('ifIndex', 'unknown')}")
                existing_iface = db.query(Interface).filter(
                    Interface.device_id == device.id,
                    Interface.interface_name == iface_name,
                ).first()
                if existing_iface:
                    existing_iface.status = str(row.get("operStatus") or "unknown").lower()
                    existing_iface.speed = str(row.get("speed") or "Not Supported")
                    existing_iface.traffic_in = float(row.get("inOctets") or 0)
                    existing_iface.traffic_out = float(row.get("outOctets") or 0)
                    existing_iface.packet_errors = int(row.get("errors") or 0)
                else:
                    db.add(Interface(
                        device_id=device.id,
                        interface_name=iface_name,
                        status=str(row.get("operStatus") or "unknown").lower(),
                        speed=str(row.get("speed") or "Not Supported"),
                        traffic_in=float(row.get("inOctets") or 0),
                        traffic_out=float(row.get("outOctets") or 0),
                        packet_errors=int(row.get("errors") or 0),
                    ))
                if not device.mac_address and row.get("mac") not in (None, "", "Not Supported"):
                    device.mac_address = str(row["mac"])
            device.uptime_seconds = int(result.get("uptime_seconds") or 0)
            device.status = "online"
            device.monitoring_status = True
            device.last_seen = datetime.utcnow()
            device.deleted_at = None

            credential = db.query(DeviceCredential).filter(DeviceCredential.device_id == device.id).first()
            if credential is None:
                credential = DeviceCredential(device_id=device.id)
                db.add(credential)
            credential.snmp_version = payload.snmp_version
            credential.username = payload.username
            credential.auth_protocol = payload.auth_protocol
            credential.auth_password = encrypt_secret(payload.auth_password) if payload.auth_password else None
            credential.privacy_protocol = payload.privacy_protocol
            credential.privacy_password = encrypt_secret(payload.privacy_password) if payload.privacy_password else None
            credential.security_level = payload.security_level
            db.add(Event(device_id=device.id, event_type="SNMP_DISCOVERY", description=f"SNMP discovery successful for {ip}"))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("SNMP inventory replacement failed")
        raise HTTPException(status_code=500, detail=f"SNMP inventory save failed: {exc}") from exc
    finally:
        db.close()
    return {
        "scanned": len(ips),
        "count": len(results),
        "results": results,
    }


# ----------------------------- SSH ---------------------------------------- #


@router.post("/discovery/ssh")
def discovery_ssh(payload: IpsRequest):
    from discovery_modules.ssh_discovery import SSHDiscovery  # type: ignore

    if not payload.ip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ip is required")
    result = SSHDiscovery(timeout_seconds=payload.timeout_seconds).collect(payload.ip, payload.open_ports)
    return {"ip": payload.ip, **result}


# ----------------------------- WMI ---------------------------------------- #


@router.post("/discovery/wmi")
def discovery_wmi(payload: IpsRequest):
    from discovery_modules.wmi_discovery import WMIDiscovery  # type: ignore

    if not payload.ip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ip is required")
    result = WMIDiscovery(timeout_seconds=int(payload.timeout_seconds)).collect(payload.ip, payload.open_ports)
    return {"ip": payload.ip, **result}


# ----------------------------- Device Profiler ---------------------------- #


@router.post("/discovery/profile")
def discovery_profile(payload: ProfileRequest):
    from discovery_modules.device_profiler import DeviceProfiler  # type: ignore

    if not payload.signals:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="signals object is required")
    return DeviceProfiler().profile(payload.signals)


# ----------------------------- Summary / Inventory ------------------------ #


@router.get("/discovery/summary")
def discovery_summary():
    from monitoring_services import MonitoringServices  # type: ignore

    payload = _load_inventory()
    devices = payload.get("devices", [])
    summary = MonitoringServices().summarize(devices)
    return {**summary, "device_count": len(devices)}


@router.get("/discovery/inventory")
def discovery_inventory():
    return _load_inventory()


# ----------------------------- Monitoring --------------------------------- #


@router.post("/monitoring/icmp")
def monitoring_icmp(payload: IpsRequest):
    from monitoring_modules.icmp_monitor import ICMPMonitor  # type: ignore

    ips = _ips(payload)
    if not ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ips[] is required")
    samples = ICMPMonitor(timeout_ms=payload.timeout_ms).check_many(ips)
    return {"count": len(samples), "samples": samples}


@router.post("/monitoring/snmp")
def monitoring_snmp(payload: IpsRequest):
    from backend.snmp.monitor import SNMPMonitor

    if not payload.ip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ip is required")
    sample = SNMPMonitor().poll(payload.ip)
    return {"ip": payload.ip, **sample}


@router.post("/monitoring/syslog/ingest")
def monitoring_syslog_ingest(payload: SyslogRequest):
    from monitoring_modules.syslog_collector import SyslogCollector  # type: ignore

    if not payload.message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message is required")
    return SyslogCollector().ingest(payload.message, payload.source_ip)


@router.post("/monitoring/syslog/parse")
def monitoring_syslog_parse(payload: SyslogRequest):
    from monitoring_modules.syslog_collector import SyslogCollector  # type: ignore

    if not payload.message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message is required")
    return SyslogCollector().parse(payload.message, payload.source_ip)


@router.post("/monitoring/trap/ingest")
def monitoring_trap_ingest(payload: TrapRequest):
    from monitoring_modules.trap_receiver import TrapReceiver  # type: ignore

    raw = payload.payload
    if raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload is required")
    try:
        raw_bytes = bytes.fromhex(raw)
    except ValueError:
        raw_bytes = raw  # treat as plain text
    return TrapReceiver().ingest(raw_bytes, payload.source_ip)


# ----------------------------- Analytics ---------------------------------- #


@router.post("/analytics/alerts/evaluate")
def analytics_alerts_evaluate(payload: AlertsEvaluateRequest):
    from analytics_modules.alert_engine import AlertEngine  # type: ignore

    engine = AlertEngine()
    alerts = engine.evaluate_samples(payload.samples)
    if payload.events:
        alerts.extend(engine.evaluate_events(payload.events))
    return {"count": len(alerts), "alerts": alerts}


@router.post("/analytics/alerts/thresholds")
def analytics_alerts_thresholds():
    from config import ALERT_THRESHOLDS  # type: ignore

    return {"thresholds": ALERT_THRESHOLDS}


@router.post("/analytics/events/from-samples")
def analytics_events_from_samples(payload: EventsFromSamplesRequest):
    from analytics_modules.event_engine import EventEngine  # type: ignore

    engine = EventEngine()
    events: list[dict[str, Any]] = []
    for sample in payload.samples:
        events.extend(engine.from_monitor_sample(sample))
    return {"count": len(events), "events": events}


@router.post("/analytics/events/normalize")
def analytics_events_normalize(payload: EventsNormalizeRequest):
    from analytics_modules.event_engine import EventEngine  # type: ignore

    events = EventEngine().normalize_external(payload.events)
    return {"count": len(events), "events": events}


@router.post("/analytics/topology")
def analytics_topology(payload: TopologyRequest):
    from analytics_modules.topology_engine import TopologyEngine  # type: ignore

    devices = payload.devices
    if devices is None:
        devices = _load_inventory().get("devices", [])
    if not isinstance(devices, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="devices[] is required")
    graph = TopologyEngine().build(devices)
    return {
        "node_count": len(graph["nodes"]),
        "link_count": len(graph["links"]),
        "subnet_count": len(graph["subnets"]),
        **graph,
    }


@router.post("/analytics/topology/db")
def analytics_topology_db():
    """Build topology from the PostgreSQL ``devices`` table (FastAPI source of truth).

    Vendor is resolved via the ``vendors`` FK if set, otherwise falls back to
    MAC-based OUI lookup from ``vendor_map``. Useful when the React dashboard
    wants to display the live NMS database view rather than the on-disk
    ``inventory.json`` file.
    """
    from vendor_map import lookup_vendor  # type: ignore
    from analytics_modules.topology_engine import TopologyEngine  # type: ignore

    # Lazy import — only works when this router is part of the FastAPI app.
    from backend.database.session import SessionLocal  # type: ignore
    from backend.models import Device, Vendor  # type: ignore

    devices: list[dict[str, Any]] = []
    with SessionLocal() as db:
        rows = db.query(Device).filter(Device.deleted_at.is_(None)).all()
        for d in rows:
            vendor_name: str | None = None
            if d.vendor_id:
                v = db.get(Vendor, d.vendor_id)
                if v is not None:
                    vendor_name = v.vendor_name
            if not vendor_name:
                resolved = lookup_vendor(d.mac_address)
                if resolved != "Unknown":
                    vendor_name = resolved
            devices.append(
                {
                    "ip": d.ip_address,
                    "ip_address": d.ip_address,
                    "mac": d.mac_address,
                    "mac_address": d.mac_address,
                    "hostname": d.hostname,
                    "vendor": vendor_name,
                    "status": d.status,
                    "model": d.model,
                    "category": d.model or "device",
                }
            )
    graph = TopologyEngine().build(devices)
    return {
        "node_count": len(graph["nodes"]),
        "link_count": len(graph["links"]),
        "subnet_count": len(graph["subnets"]),
        "source": "postgresql",
        **graph,
    }


# ----------------------------- MAC -> Vendor ------------------------------ #


@router.post("/mac-vendors/lookup")
def mac_vendors_lookup(payload: MacLookupRequest):
    """Resolve one MAC (``mac``) or a list of MACs (``macs``) to vendor names."""
    from vendor_map import lookup_vendor  # type: ignore

    if payload.macs:
        return {"results": [{"mac": m, "vendor": lookup_vendor(m)} for m in payload.macs]}
    if payload.mac:
        return {"mac": payload.mac, "vendor": lookup_vendor(payload.mac)}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mac or macs[] is required")


@router.get("/mac-vendors")
def mac_vendors_list():
    """Return the full OUI (MAC prefix -> vendor) table in use."""
    from vendor_map import list_vendors  # type: ignore

    return {"count": len(list_vendors()), "entries": list_vendors()}


@router.post("/mac-vendors", status_code=status.HTTP_201_CREATED)
def mac_vendors_add(payload: VendorAddRequest):
    """Add a new OUI entry to the in-memory table (lost on restart)."""
    from vendor_map import add_vendor  # type: ignore

    try:
        add_vendor(payload.prefix, payload.vendor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"prefix": payload.prefix, "vendor": payload.vendor}


# ----------------------------- Chunked Scan ------------------------------- #


@router.post("/discovery/chunked-scan")
def start_chunked_scan(payload: ChunkedScanRequest):
    """Start a chunked discovery scan. Returns a job_id for progress tracking.

    The backend will:
    1. Expand the CIDR range into individual IPs.
    2. Split them into chunks of 25.
    3. Scan each chunk sequentially.
    4. Stream progress via SSE at /discovery/chunked-scan/{job_id}/progress.
    """
    from network_range import NetworkRange  # type: ignore

    try:
        rng = NetworkRange(payload.network_range, max_hosts=payload.max_hosts)
        all_ips = rng.expand()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not all_ips:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No IPs in range")

    from backend.services.chunked_discovery import start_chunked_scan as _start

    job = _start(
        network_range=payload.network_range,
        all_ips=all_ips,
        site_id=payload.site_id,
        ports=payload.ports,
        timeout_ms=payload.timeout_ms,
        snmp_community=payload.snmp_community,
        scan_icmp=payload.scan_icmp,
        scan_tcp_ports=payload.scan_ports,
        scan_snmp=payload.scan_snmp,
        chunk_size=payload.chunk_size,
        modules=payload.modules,
    )
    return {
        "job_id": job.job_id,
        "total_ips": job.total_ips,
        "chunks_total": job.chunks_total,
        "chunk_size": job.chunk_size,
        "status": job.status,
    }


@router.get("/discovery/chunked-scan/{job_id}")
def get_chunked_scan_status(job_id: str):
    """Get current status and discovered results for a chunked scan job."""
    from backend.services.chunked_discovery import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return {
        "progress": job.to_progress_dict(),
        "discovered": job.discovered,
    }


@router.get("/discovery/chunked-scan/{job_id}/progress")
async def chunked_scan_progress(job_id: str):
    """SSE stream for live progress updates during a chunked scan.

    Events:
    - progress: { status, chunks_completed, chunks_total, ips_scanned, discovered_count, progress_pct, elapsed_seconds }
    - discovered: { ip_address, mac_address, hostname, vendor, status, chunk }
    - complete: { status, total_ips, discovered_count, elapsed_seconds, discovered: [...] }
    - error: { error: "message" }
    """
    from backend.services.chunked_discovery import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    async def event_stream():
        sent_discovered = 0
        while True:
            # Wait for the threading.Event to be set, or timeout after 2s
            await asyncio.get_event_loop().run_in_executor(
                None, job._event.wait, 2.0
            )
            job._event.clear()

            # Send progress update
            progress = job.to_progress_dict()
            yield f"event: progress\ndata: {json.dumps(progress)}\n\n"

            # Send newly discovered devices since last update
            new_devices = job.discovered[sent_discovered:]
            for device in new_devices:
                yield f"event: discovered\ndata: {json.dumps(device)}\n\n"
            sent_discovered = len(job.discovered)

            # Check if job is done
            if job.status in ("completed", "failed"):
                if job.status == "completed":
                    final = {
                        **progress,
                        "discovered": job.discovered,
                    }
                    yield f"event: complete\ndata: {json.dumps(final)}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'error': job.error or 'Unknown error'})}\n\n"
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ----------------------------- Add Discovered Devices ------------------- #


@router.post("/discovery/add-devices")
def add_discovered_devices(payload: AddDevicesRequest):
    """Add discovered devices to the PostgreSQL database.

    Accepts a list of device dicts (from the chunked scan results) and
    creates Device records. Skips devices whose IP already exists.
    Returns a summary of added / skipped devices.
    """
    from backend.database.session import SessionLocal
    from backend.models import Device, DeviceMetric, Interface
    from datetime import datetime

    added = []
    skipped = []

    try:
        with SessionLocal() as db:
            for dev in payload.devices:
                ip = dev.get("ip_address") or dev.get("ip")
                if not ip:
                    skipped.append({"ip": None, "reason": "no IP"})
                    continue

                # Check if device with this IP already exists (active)
                existing = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.is_(None)).first()
                if existing:
                    hostname = dev.get("hostname") or dev.get("sysName") or dev.get("sysDescr") or existing.hostname
                    if str(hostname).strip().lower() in {"(none)", "none", "null"}:
                        hostname = existing.hostname or f"device-{ip.replace('.', '-')}"
                    existing.hostname = str(hostname)[:160]
                    existing.model = str(dev.get("model") or dev.get("sysDescr") or existing.model or "")[:120] or None
                    existing.firmware_version = dev.get("firmware") or existing.firmware_version
                    existing.uptime_seconds = int(dev.get("uptime_seconds") or existing.uptime_seconds or 0)
                    existing.status = "online"
                    existing.monitoring_status = True
                    existing.last_seen = datetime.utcnow()
                    added.append({"id": existing.id, "ip": ip, "hostname": existing.hostname, "updated": True})
                    continue

                # Check if a soft-deleted device with this IP exists — undelete it
                soft_deleted = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.isnot(None)).first()
                if soft_deleted:
                    hostname = dev.get("hostname") or dev.get("dns_hostname") or soft_deleted.hostname
                    mac = dev.get("mac_address") or dev.get("mac")
                    model = dev.get("model") or dev.get("category")
                    soft_deleted.deleted_at = None
                    soft_deleted.hostname = (hostname or soft_deleted.hostname)[:160]
                    if mac:
                        soft_deleted.mac_address = mac[:32]
                    if model:
                        soft_deleted.model = model[:120]
                    soft_deleted.status = "online"
                    soft_deleted.monitoring_status = True
                    if payload.site_id is not None:
                        soft_deleted.site_id = payload.site_id
                    added.append({"id": soft_deleted.id, "ip": ip, "hostname": soft_deleted.hostname})
                    continue

                hostname = dev.get("hostname") or dev.get("dns_hostname") or f"device-{ip.replace('.', '-')}"
                if str(hostname).strip().lower() in {"(none)", "none", "null"}:
                    hostname = dev.get("sysName") or dev.get("sysDescr") or f"device-{ip.replace('.', '-')}"
                mac = dev.get("mac_address") or dev.get("mac")
                model = dev.get("model") or dev.get("sysDescr") or dev.get("category")

                device = Device(
                    site_id=payload.site_id,
                    hostname=hostname[:160],
                    ip_address=ip,
                    mac_address=mac[:32] if mac else None,
                    model=model[:120] if model else None,
                    status="online",
                    monitoring_status=True,
                )
                db.add(device)
                db.flush()
                for row in dev.get("interfaces") or []:
                    index = row.get("ifIndex")
                    if index is None:
                        continue
                    db.add(Interface(
                        device_id=device.id,
                        interface_name=str(row.get("ifName") or row.get("description") or f"if{index}")[:120],
                        status=str(row.get("operational_status") or "unknown")[:30],
                        speed=str(row.get("speed")) if row.get("speed") is not None else None,
                        traffic_in=float(row.get("ifHCInOctets") or row.get("in_octets") or 0),
                        traffic_out=float(row.get("ifHCOutOctets") or row.get("out_octets") or 0),
                        packet_errors=int(row.get("in_errors") or 0) + int(row.get("out_errors") or 0),
                    ))
                memory = dev.get("memory") or {}
                cpu = dev.get("cpu") or {}
                db.add(DeviceMetric(
                    device_id=device.id,
                    cpu_usage=float(cpu.get("average") or cpu.get("current") or 0) if cpu else None,
                    memory_usage=float(memory.get("utilization_percent") or 0) if memory else None,
                    temperature=float((dev.get("environment") or {}).get("temperature") or 0) if (dev.get("environment") or {}).get("temperature") is not None else None,
                ))
                added.append({"id": device.id, "ip": ip, "hostname": hostname})

            db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return {
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added": added,
        "skipped": skipped,
    }


# ----------------------------- Check Stored Devices ---------------------- #


@router.post("/discovery/check-stored")
def check_stored_devices(payload: CheckStoredRequest):
    """Check which IPs from a list are already stored in the database.

    Returns a set of IPs that exist in the DB so the frontend can show
    'Monitoring' buttons instead of 'Add' buttons.
    """
    from backend.database.session import SessionLocal
    from backend.models import Device

    stored_ips: set[str] = set()
    with SessionLocal() as db:
        rows = db.query(Device.ip_address).filter(
            Device.ip_address.in_(payload.ips),
            Device.deleted_at.is_(None),
        ).all()
        stored_ips = {r[0] for r in rows}

    return {"stored_ips": list(stored_ips)}


# ----------------------------- Real-time Monitoring ---------------------- #


@router.post("/discovery/monitoring/start")
def monitoring_start_device(payload: MonitorDeviceRequest):
    """Start monitoring a single device (ping every 5s)."""
    from backend.services.realtime_monitor import get_engine

    engine = get_engine()
    dev = engine.start_device(
        ip=payload.ip,
        hostname=payload.hostname or "",
        vendor=payload.vendor or "",
        mac_address=payload.mac_address,
        site_id=payload.site_id,
        device_id=payload.device_id,
    )
    return dev.to_dict()


@router.post("/discovery/monitoring/stop")
def monitoring_stop_device(payload: MonitorDeviceRequest):
    """Stop monitoring a single device."""
    from backend.services.realtime_monitor import get_engine

    engine = get_engine()
    removed = engine.stop_device(payload.ip)
    return {"ip": payload.ip, "stopped": removed}


@router.post("/discovery/monitoring/start-all")
def monitoring_start_all(payload: MonitorAllRequest):
    """Start monitoring multiple devices at once."""
    from backend.services.realtime_monitor import get_engine

    engine = get_engine()
    added = engine.start_all(payload.devices)
    return {"added": added, "total_monitored": len(engine.get_all())}


@router.post("/discovery/monitoring/stop-all")
def monitoring_stop_all():
    """Stop monitoring all devices."""
    from backend.services.realtime_monitor import get_engine

    engine = get_engine()
    count = engine.stop_all()
    return {"stopped": count}


@router.get("/discovery/monitoring/status")
def monitoring_status():
    """Get current status of all monitored devices + summary."""
    from backend.services.realtime_monitor import get_engine

    engine = get_engine()
    return {
        "summary": engine.get_summary(),
        "devices": engine.get_all(),
    }


@router.get("/discovery/monitoring/stream")
async def monitoring_sse_stream():
    """SSE stream for real-time monitoring updates.

    Events:
    - update: { summary: {...}, devices: [...] }
    """
    from backend.services.realtime_monitor import get_engine

    engine = get_engine()

    async def event_stream():
        while True:
            # Block until new data or timeout (5s)
            await asyncio.get_event_loop().run_in_executor(
                None, engine.wait_for_update, 5.0
            )
            data = {
                "summary": engine.get_summary(),
                "devices": engine.get_all(),
            }
            yield f"event: update\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------- Device Monitoring History (detail page) ------------- #


@router.get("/discovery/device-history/{ip}")
def device_monitoring_history(
    ip: str,
    hours: int = Query(default=24, ge=1, le=720, description="History window in hours (default 24h, max 30 days)"),
):
    """Return full monitoring history for a single device identified by IP.

    Response includes:
    - device: Full device record from the DB
    - status_history: List of up/down status change events
    - metrics: Time-series latency + packet-loss data for graphs
    - summary: Aggregated uptime / downtime / availability stats
    """
    from backend.database.session import SessionLocal  # type: ignore
    from backend.models import Device, DeviceMetric, DeviceStatusHistory
    from datetime import datetime, timedelta

    # ---- 1. Look up the device by IP ----
    with SessionLocal() as db:
        device = db.query(Device).filter(
            Device.ip_address == ip,
            Device.deleted_at.is_(None),
        ).first()
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {ip} not found")

        # ---- 2. Time window for history queries ----
        since = datetime.utcnow() - timedelta(hours=hours)

        # ---- 3. Status change history (up/down events) ----
        history_rows = (
            db.query(DeviceStatusHistory)
            .filter(
                DeviceStatusHistory.device_id == device.id,
                DeviceStatusHistory.timestamp >= since,
            )
            .order_by(DeviceStatusHistory.timestamp.desc())
            .all()
        )
        status_history = [
            {
                "id": h.id,
                "old_status": h.old_status,
                "new_status": h.new_status,
                "reason": h.change_reason,
                "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            }
            for h in history_rows
        ]

        # ---- 4. Metrics time-series (latency, packet loss) for graph ----
        metric_rows = (
            db.query(DeviceMetric)
            .filter(
                DeviceMetric.device_id == device.id,
                DeviceMetric.created_at >= since,
            )
            .order_by(DeviceMetric.created_at.asc())
            .all()
        )
        metrics = [
            {
                "timestamp": m.created_at.isoformat() if m.created_at else None,
                "latency_ms": m.latency,
                "packet_loss": m.packet_loss,
                "cpu_usage": m.cpu_usage,
                "memory_usage": m.memory_usage,
            }
            for m in metric_rows
        ]

        # ---- 5. Compute uptime / downtime summary ----
        uptime_secs = device.uptime_seconds or 0
        downtime_secs = device.downtime_seconds or 0
        # If device is currently online, add time since last status change
        if device.status == "online" and device.last_status_change:
            elapsed = (datetime.utcnow() - device.last_status_change).total_seconds()
            uptime_secs += int(elapsed)
        elif device.status == "offline" and device.last_status_change:
            elapsed = (datetime.utcnow() - device.last_status_change).total_seconds()
            downtime_secs += int(elapsed)
        total_recorded = uptime_secs + downtime_secs
        availability_pct = round((uptime_secs / total_recorded * 100), 2) if total_recorded > 0 else 0.0

        summary = {
            "total_hours": hours,
            "uptime_seconds": uptime_secs,
            "downtime_seconds": downtime_secs,
            "uptime_hours": round(uptime_secs / 3600, 2),
            "downtime_hours": round(downtime_secs / 3600, 2),
            "availability_pct": availability_pct,
            "total_status_changes": len(history_rows),
            "total_pings": len(metric_rows),
            "current_status": device.status,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "last_status_change": device.last_status_change.isoformat() if device.last_status_change else None,
        }

        # ---- 6. Build device detail object ----
        device_detail = {
            "id": device.id,
            "ip_address": device.ip_address,
            "hostname": device.hostname,
            "mac_address": device.mac_address,
            "status": device.status,
            "model": device.model,
            "serial_number": device.serial_number,
            "firmware_version": device.firmware_version,
            "monitoring_status": device.monitoring_status,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "site_id": device.site_id,
            "vendor": device.vendor.vendor_name if device.vendor else None,
            "device_type": device.device_type.name if device.device_type else None,
        }

        return {
            "device": device_detail,
            "status_history": status_history,
            "metrics": metrics,
            "summary": summary,
        }


# ----------------------------- Scan Plan (preview) ------------------------ #


@router.post("/discovery/plan")
def discovery_plan(payload: ScanPlanRequest):
    """Preview what a discovery run would scan — no network probes are made.

    Splits the user's ``network_range`` into:
      * ``total_ips``    — all IPs the range expands to
      * ``new_ips``      — IPs not in the current inventory file
      * ``known_ips``    — IPs already in the inventory file (will be skipped)

    Accepts CIDR ("192.168.1.0/24"), dash ranges ("192.168.1.1-50"),
    or comma-separated lists.
    """
    from network_range import NetworkRange, diff_against_known  # type: ignore

    try:
        rng = NetworkRange(payload.network_range, max_hosts=payload.max_hosts)
        all_ips = rng.expand()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    known_ips = [d.get("ip") for d in _load_inventory().get("devices", []) if d.get("ip")]
    new_ips, known_in_range = diff_against_known(all_ips, known_ips)
    return {
        "network_range": payload.network_range,
        "max_hosts": payload.max_hosts,
        "total_ips": len(all_ips),
        "new_ips": new_ips,
        "new_count": len(new_ips),
        "known_ips": known_in_range,
        "known_count": len(known_in_range),
    }
