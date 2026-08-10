"""Chunked network discovery with live progress tracking.

Splits a CIDR range into chunks of 25 IPs, scans each chunk sequentially,
and stores progress/results for SSE streaming to the frontend.

Pipeline per chunk:
  1. ICMP ping to find alive hosts (always on)
  2. Run selected enrichment modules on alive hosts
  3. Profile each device (vendor / OS / category)
  4. Only reachable devices are included in results
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from backend.services.discovery import _ping, _lookup_mac


# ---------------------------------------------------------------------------
# In-memory job store (keyed by job_id)
# ---------------------------------------------------------------------------

@dataclass
class ScanJob:
    """Tracks state for a single chunked scan job."""

    job_id: str
    network_range: str
    site_id: int | None
    total_ips: int = 0
    chunk_size: int = 25
    chunks_total: int = 0
    chunks_completed: int = 0
    ips_scanned: int = 0
    discovered: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending | running | completed | failed
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    # Threading event for cross-thread signaling (scan thread -> SSE async gen)
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def signal_update(self) -> None:
        """Wake up any SSE coroutines waiting for progress."""
        self._event.set()

    def progress_pct(self) -> int:
        if self.chunks_total == 0:
            return 0
        return int((self.chunks_completed / self.chunks_total) * 100)

    def to_progress_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "network_range": self.network_range,
            "total_ips": self.total_ips,
            "chunk_size": self.chunk_size,
            "chunks_total": self.chunks_total,
            "chunks_completed": self.chunks_completed,
            "ips_scanned": self.ips_scanned,
            "discovered_count": len(self.discovered),
            "progress_pct": self.progress_pct(),
            "elapsed_seconds": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "error": self.error,
        }


# Global job store — keyed by job_id
_jobs: dict[str, ScanJob] = {}


def get_job(job_id: str) -> ScanJob | None:
    return _jobs.get(job_id)


def list_jobs() -> list[str]:
    return list(_jobs.keys())


# ---------------------------------------------------------------------------
# Module registry — maps module names to their enrichment functions
# ---------------------------------------------------------------------------

def _run_tcp(ip: str, ports: list[int], timeout_s: float) -> dict[str, str]:
    from discovery_modules.tcp_discovery import TCPDiscovery  # type: ignore
    return TCPDiscovery(ports=ports or None, timeout_seconds=timeout_s).scan_host(ip)


def _run_arp(ip: str) -> dict[str, Any]:
    from discovery_modules.arp_discovery import ARPDiscovery  # type: ignore
    return ARPDiscovery().collect(ip)


def _run_dns(ip: str) -> dict[str, Any]:
    from discovery_modules.dns_discovery import DNSDiscovery  # type: ignore
    return DNSDiscovery().resolve(ip)


def _run_http(ip: str, open_ports: dict) -> dict[str, Any]:
    from discovery_modules.http_discovery import HTTPDiscovery  # type: ignore
    return HTTPDiscovery().discover(ip, open_ports)


def _run_snmp(ip: str, timeout_s: float) -> dict[str, Any]:
    from backend.snmp.collector import SNMPDiscovery
    return SNMPDiscovery(timeout_seconds=timeout_s).collect(ip)


def _run_ssh(ip: str, open_ports: dict, timeout_s: float) -> dict[str, Any]:
    from discovery_modules.ssh_discovery import SSHDiscovery  # type: ignore
    return SSHDiscovery(timeout_seconds=timeout_s).collect(ip, open_ports)


def _run_wmi(ip: str, open_ports: dict, timeout_s: int) -> dict[str, Any]:
    from discovery_modules.wmi_discovery import WMIDiscovery  # type: ignore
    return WMIDiscovery(timeout_seconds=timeout_s).collect(ip, open_ports)


def _profile_device(signals: dict[str, Any]) -> dict[str, Any]:
    from discovery_modules.device_profiler import DeviceProfiler  # type: ignore
    return DeviceProfiler().profile(signals)


# ---------------------------------------------------------------------------
# Chunked scan executor (runs in a background thread)
# ---------------------------------------------------------------------------

def _enrich_host(
    ip: str,
    modules: list[str],
    ports: list[int],
    timeout_ms: int,
) -> dict[str, Any]:
    """Run selected enrichment modules on a single alive host."""
    timeout_s = timeout_ms / 1000.0
    record: dict[str, Any] = {"ip": ip}

    # TCP port scan
    open_ports: dict[str, str] = {}
    if "tcp_discovery" in modules:
        open_ports = _run_tcp(ip, ports, timeout_s)
        record["open_ports"] = open_ports

    # ARP (MAC lookup)
    if "arp_discovery" in modules:
        record["arp"] = _run_arp(ip)

    # DNS
    if "dns_discovery" in modules:
        record["dns"] = _run_dns(ip)

    # HTTP banner
    if "http_discovery" in modules:
        record["http"] = _run_http(ip, open_ports)

    # SNMP
    if "snmp_discovery" in modules:
        record["snmp"] = _run_snmp(ip, timeout_s)

    # SSH
    if "ssh_discovery" in modules:
        record["ssh"] = _run_ssh(ip, open_ports, timeout_s)

    # WMI
    if "wmi_discovery" in modules:
        record["wmi"] = _run_wmi(ip, open_ports, int(timeout_s * 4))

    # Device profiler (always runs if any enrichment module is active)
    if len(modules) > 1:  # more than just ip_discovery
        record["device_profile"] = _profile_device(record)

    return record


def _execute_chunked_scan(
    job: ScanJob,
    all_ips: list[str],
    ports: list[int],
    timeout_ms: int,
    snmp_community: str,
    scan_icmp: bool,
    scan_tcp_ports: bool,
    scan_snmp: bool,
    modules: list[str] | None,
) -> None:
    """Scan IPs in chunks of 25, updating job state after each chunk.

    Pipeline per chunk:
      1. ICMP ping to find alive hosts
      2. Enrich alive hosts with selected modules (TCP, ARP, DNS, HTTP, SNMP, SSH, WMI)
      3. Profile each device
      4. Only reachable devices are added to results
    """
    from vendor_map import lookup_vendor  # type: ignore

    # Active enrichment modules (always include ip_discovery + icmp_discovery as core)
    active_modules = modules or ["ip_discovery", "icmp_discovery"]
    if "ip_discovery" not in active_modules:
        active_modules.insert(0, "ip_discovery")
    if "icmp_discovery" not in active_modules:
        active_modules.insert(1 if "ip_discovery" in active_modules else 0, "icmp_discovery")

    job.status = "running"
    job.started_at = time.time()
    job.signal_update()

    # Split into chunks of 25
    chunks = [all_ips[i:i + job.chunk_size] for i in range(0, len(all_ips), job.chunk_size)]
    job.chunks_total = len(chunks)
    job.total_ips = len(all_ips)
    job.signal_update()

    try:
        for chunk_idx, chunk in enumerate(chunks):
            # --- Phase 1: ICMP ping to find alive hosts (parallel) ---
            alive_ips: list[str] = []
            with ThreadPoolExecutor(max_workers=min(len(chunk), 20), thread_name_prefix="chunk-ping") as pool:
                futures = {pool.submit(_ping, ip, timeout_ms): ip for ip in chunk}
                for future in as_completed(futures):
                    try:
                        if future.result():
                            alive_ips.append(futures[future])
                    except Exception:
                        pass

            # --- Phase 2: Enrich alive hosts ---
            for ip in alive_ips:
                record = _enrich_host(ip, active_modules, ports, timeout_ms)

                # Resolve vendor from MAC
                mac = None
                arp_data = record.get("arp") or {}
                if arp_data.get("mac"):
                    mac = arp_data["mac"]
                else:
                    mac = _lookup_mac(ip)
                    record["mac"] = mac

                try:
                    vendor = lookup_vendor(mac) if mac else "Unknown"
                except Exception:
                    vendor = "Unknown"

                # Smart hostname resolution
                profile = record.get("device_profile") or {}
                snmp_data = record.get("snmp") or {}
                dns_data = record.get("dns") or {}

                if snmp_data.get("hostname"):
                    hostname = snmp_data["hostname"]
                elif dns_data.get("hostname"):
                    hostname = dns_data["hostname"]
                elif profile.get("vendor") and profile["vendor"] != "Unknown":
                    hostname = profile["vendor"]
                elif vendor != "Unknown":
                    hostname = vendor
                else:
                    hostname = f"device-{ip.replace('.', '-')}"

                device: dict[str, Any] = {
                    "ip_address": ip,
                    "mac_address": mac,
                    "hostname": hostname,
                    "vendor": vendor if vendor != "Unknown" else (profile.get("vendor") or "Unknown"),
                    "status": "online",
                    "reachable": True,
                    "chunk": chunk_idx + 1,
                    "modules_run": active_modules,
                }

                # Include enrichment data
                if record.get("open_ports"):
                    device["open_ports"] = record["open_ports"]
                if record.get("snmp"):
                    snmp = record["snmp"]
                    if snmp.get("reachable"):
                        device["snmp_name"] = snmp.get("hostname")
                        device["snmp_description"] = snmp.get("sysDescr")
                        device["snmp_vendor"] = snmp.get("vendor")
                        device["snmp_model"] = snmp.get("model")
                if record.get("dns") and record["dns"].get("resolved"):
                    device["dns_hostname"] = record["dns"]["hostname"]
                if record.get("ssh") and record["ssh"].get("reachable"):
                    device["ssh_banner"] = record["ssh"].get("banner")
                    device["ssh_platform"] = record["ssh"].get("platform_hint")
                if profile:
                    device["category"] = profile.get("category", "Unknown")
                    device["os"] = profile.get("os", "Unknown")
                    device["model"] = profile.get("model", "Unknown")
                    device["confidence"] = profile.get("confidence", 0)

                job.discovered.append(device)
                # Signal SSE immediately per device for faster frontend updates
                job.signal_update()

            # Update chunk-level progress
            job.chunks_completed = chunk_idx + 1
            job.ips_scanned += len(chunk)
            job.signal_update()

        job.status = "completed"
        job.finished_at = time.time()
        job.signal_update()

    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = time.time()
        job.signal_update()


# ---------------------------------------------------------------------------
# Public API: start a chunked scan job
# ---------------------------------------------------------------------------

def start_chunked_scan(
    network_range: str,
    all_ips: list[str],
    site_id: int | None = None,
    ports: list[int] | None = None,
    timeout_ms: int = 700,
    snmp_community: str = "public",
    scan_icmp: bool = True,
    scan_tcp_ports: bool = True,
    scan_snmp: bool = False,
    chunk_size: int = 25,
    modules: list[str] | None = None,
) -> ScanJob:
    """Create a new scan job and start it in a background thread.

    Returns the ScanJob immediately; progress is tracked via job.to_progress_dict().
    """
    job_id = str(uuid.uuid4())[:8]
    job = ScanJob(
        job_id=job_id,
        network_range=network_range,
        site_id=site_id,
        chunk_size=chunk_size,
    )
    _jobs[job_id] = job

    # Launch background thread for scanning
    thread = threading.Thread(
        target=_execute_chunked_scan,
        args=(job, all_ips, ports or [], timeout_ms, snmp_community, scan_icmp, scan_tcp_ports, scan_snmp, modules),
        daemon=True,
    )
    thread.start()

    return job
