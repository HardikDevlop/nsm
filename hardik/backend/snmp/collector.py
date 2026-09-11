"""
Agnigate NMS — SNMPService
===========================
Orchestrates the complete collection pipeline for one device.

Pipeline (no files touched at any stage)
-----------------------------------------
1.  GET identity scalars  (sysDescr, sysObjectID, sysName, …)
2.  Detect vendor + device_type from walk  → VendorDetector
3.  Build OIDRegistry from walk + vendor   → build_registry()
4.  Fetch UCD-SNMP + vendor scalar OIDs   (one GET batch)
5.  Walk all standard + vendor table roots
6.  Run NormalizationLayer  → RawDevice
7.  Run all collectors     → list[CollectorResponse]
8.  Return stable API document

Every step is pure Python — no JSON files, no database, no static configs.
"""

from __future__ import annotations

import logging
import inspect
import time
import concurrent.futures
from typing import Any

from backend.config.settings import get_settings
from .client import SNMPClient
from .credentials import SNMPCredentials
from .normalizer import NormalizationLayer
from .oid_catalog import STANDARD_OIDS, VENDOR_OID_CATALOG
from .oid_mapper import build_registry
from .vendor_detector import VendorDetector
from .collectors import (
    ARPCollector, CDPCollector, CPUCollector, EnvironmentCollector,
    FirewallCollector, HealthCollector, InterfaceCollector, InventoryCollector,
    LLDPCollector, MACTableCollector, MemoryCollector, RoutingCollector,
    StorageCollector, SystemCollector, TopologyCollector, VLANCollector,
    WirelessCollector,
)

logger = logging.getLogger(__name__)

# Root tasks are lightweight synchronous wrappers around SNMPClient.walk().
# Physical network work remains capped by client.py's shared 8-thread executor.
_root_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="snmp-root",
)

API_VERSION = "2.0"

# ---------------------------------------------------------------------------
# Standard table OID roots — walked for every device
# ---------------------------------------------------------------------------
_STANDARD_TABLE_WALKS: dict[str, str] = {
    "if_table":       "1.3.6.1.2.1.2.2.1",
    "if_ext":         "1.3.6.1.2.1.31.1.1.1",
    "hr_processor":   "1.3.6.1.2.1.25.3.3.1",
    "hr_storage":     "1.3.6.1.2.1.25.2.3.1",
    "entity":         "1.3.6.1.2.1.47.1.1.1.1",
    "entity_sensor":  "1.3.6.1.2.1.99.1.1.1",
    "lldp_rem":       "1.0.8802.1.1.2.1.4",
    "lldp_loc":       "1.0.8802.1.1.2.1.3.7.1",
    "vlans_static":   "1.3.6.1.2.1.17.7.1.4.3.1",
    "vlans_current":  "1.3.6.1.2.1.17.7.1.4.2.1",
    "mac_fdb":        "1.3.6.1.2.1.17.4.3.1",
    "bridge_ports":   "1.3.6.1.2.1.17.1.4.1",
    "vlan_fdb_q":     "1.3.6.1.2.1.17.7.1.2.2.1",
    "routing":        "1.3.6.1.2.1.4.21.1",
    "arp":            "1.3.6.1.2.1.4.22.1",
    # Modern IP-MIB replacement for ipNetToMediaTable (common on Linux/NVRs).
    "arp_physical":   "1.3.6.1.2.1.4.35.1",
}

# Vendor-specific table roots (derived dynamically from oid_catalog)
def _vendor_table_roots(vendor: str) -> dict[str, str]:
    roots: dict[str, str] = {}
    for domain, metrics in VENDOR_OID_CATALOG.get(vendor, {}).items():
        for metric, oid in metrics.items():
            if "table" in metric or "cdp" in domain:
                roots[f"{vendor}_{domain}_{metric}"] = oid
    return roots

# Identity OIDs — single GET before the walk
_IDENTITY_OIDS: tuple[str, ...] = (
    STANDARD_OIDS["system.description"],
    STANDARD_OIDS["system.object_id"],
    STANDARD_OIDS["system.uptime"],
    STANDARD_OIDS["system.contact"],
    STANDARD_OIDS["system.name"],
    STANDARD_OIDS["system.location"],
)

# UCD-SNMP CPU/memory scalars (Linux / net-snmp)
_UCD_OIDS: tuple[str, ...] = (
    STANDARD_OIDS["ucdCpuUser"],
    STANDARD_OIDS["ucdCpuSystem"],
    STANDARD_OIDS["ucdCpuIdle"],
    STANDARD_OIDS["ucdLoadAvg1"],
    STANDARD_OIDS["ucdLoadAvg5"],
    STANDARD_OIDS["ucdLoadAvg15"],
    STANDARD_OIDS["ucdMemTotalReal"],
    STANDARD_OIDS["ucdMemAvailReal"],
    STANDARD_OIDS["ucdMemBuffer"],
    STANDARD_OIDS["ucdMemCached"],
    STANDARD_OIDS["ucdMemTotalSwap"],
    STANDARD_OIDS["ucdMemAvailSwap"],
)

# Ordered collector list — every device runs all of these
_COLLECTORS = [
    SystemCollector(),
    CPUCollector(),
    MemoryCollector(),
    StorageCollector(),
    InterfaceCollector(),
    EnvironmentCollector(),
    VLANCollector(),
    LLDPCollector(),
    CDPCollector(),
    RoutingCollector(),
    ARPCollector(),
    MACTableCollector(),
    FirewallCollector(),
    WirelessCollector(),
    InventoryCollector(),
    TopologyCollector(),
    HealthCollector(),
]


# ---------------------------------------------------------------------------
# SNMPService
# ---------------------------------------------------------------------------

class SNMPService:
    """
    Main collection orchestrator for Agnigate NMS.
    No static vendor files. All OID knowledge from oid_catalog.py.
    """

    def __init__(
        self,
        credentials: SNMPCredentials,
        timeout: float | None = None,
        retries: int | None = None,
        operation_timeout: float | None = None,
        device_id: int | None = None,
    ) -> None:
        client_parameters = inspect.signature(SNMPClient).parameters.values()
        supports_device_id = any(
            parameter.name == "device_id"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in client_parameters
        )
        if supports_device_id:
            self.client = SNMPClient(
                credentials, timeout, retries, operation_timeout, device_id=device_id
            )
        else:
            self.client = SNMPClient(credentials, timeout, retries, operation_timeout)
        self.credentials = credentials
        self._normalizer = NormalizationLayer()
        self._detector   = VendorDetector()

    def _walk_roots(self, host: str, roots: dict[str, str]) -> dict[str, Any]:
        """Walk independent roots concurrently and merge in declared order."""
        if not roots:
            return {}

        limit = max(1, min(get_settings().snmp_root_concurrency, len(roots)))
        ordered = list(roots.items())
        results: dict[str, dict[str, Any]] = {}
        succeeded = failed = timed_out = 0
        started = time.perf_counter()
        poll_deadline = (
            started + float(self.client.operation_timeout)
            if getattr(self.client, "operation_timeout", None) is not None
            else None
        )
        walk_parameters = inspect.signature(self.client.walk).parameters.values()
        walk_accepts_deadline = any(
            parameter.name == "operation_timeout"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in walk_parameters
        )

        def walk_one(name: str, root: str) -> tuple[str, dict[str, Any]]:
            root_started = time.perf_counter()
            status = "success"
            rows = 0
            try:
                if poll_deadline is not None and walk_accepts_deadline:
                    remaining = poll_deadline - time.perf_counter()
                    if remaining <= 0:
                        raise TimeoutError("SNMP poll deadline exhausted")
                    value = self.client.walk(host, root, operation_timeout=remaining)
                else:
                    value = self.client.walk(host, root)
                rows = len(value)
                return name, value
            except TimeoutError:
                status = "timeout"
                raise
            except Exception:
                status = "failed"
                raise
            finally:
                logger.debug(
                    "SNMP_ROOT_WALK root=%s operation=walk duration_ms=%.1f status=%s rows=%d",
                    root,
                    (time.perf_counter() - root_started) * 1000,
                    status,
                    rows,
                )

        pending_items = iter(ordered)
        active: dict[concurrent.futures.Future, tuple[str, str]] = {}
        for _ in range(limit):
            try:
                name, root = next(pending_items)
            except StopIteration:
                break
            active[_root_executor.submit(walk_one, name, root)] = (name, root)

        while active:
            done, _ = concurrent.futures.wait(
                active, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                name, root = active.pop(future)
                try:
                    result_name, value = future.result()
                    results[result_name] = value
                    succeeded += 1
                except TimeoutError:
                    timed_out += 1
                    logger.debug("Walk %s %s timed out", name, root)
                except Exception as exc:
                    failed += 1
                    logger.debug("Walk %s %s failed: %s", name, root, exc)

                try:
                    next_name, next_root = next(pending_items)
                except StopIteration:
                    continue
                active[_root_executor.submit(walk_one, next_name, next_root)] = (
                    next_name, next_root
                )

        merged: dict[str, Any] = {}
        for name, _root in ordered:
            merged.update(results.get(name, {}))
        logger.info(
            "SNMP_ROOT_SUMMARY host=%s roots=%d succeeded=%d failed=%d timed_out=%d duration_ms=%.1f",
            host,
            len(ordered),
            succeeded,
            failed,
            timed_out,
            (time.perf_counter() - started) * 1000,
        )
        return merged

    def collect(self, host: str) -> dict[str, Any]:
        """
        Full collection run for one device.
        Returns a stable API document with a 'collectors' dict.
        Unreachable devices return reachable=False immediately.
        """
        t0 = time.perf_counter()

        # -- Step 1: identity GET --
        raw: dict[str, Any] = {}
        try:
            raw.update(self.client.get(host, _IDENTITY_OIDS))
        except Exception as exc:
            logger.warning("SNMP identity GET failed for %s: %s", host, exc)
            return self._dead(host, str(exc))

        # -- Step 2: detect vendor from identity --
        detection   = self._detector.detect_from_walk(raw)
        vendor      = detection["vendor"]
        device_type = detection["device_type"]
        logger.info("%s → vendor=%s device_type=%s", host, vendor, device_type)

        # -- Step 3: vendor scalar OIDs (CPU/memory/system) --
        vendor_scalars: list[str] = []
        for domain, metrics in VENDOR_OID_CATALOG.get(vendor, {}).items():
            for metric, oid in metrics.items():
                if "table" not in metric and oid not in vendor_scalars:
                    vendor_scalars.append(oid)
        if vendor_scalars:
            try:
                raw.update(self.client.get(host, tuple(vendor_scalars[:40])))
            except Exception as exc:
                logger.debug("Vendor scalar GET partial %s: %s", host, exc)

        # UCD-SNMP scalars (Linux)
        try:
            raw.update(self.client.get(host, _UCD_OIDS))
        except Exception:
            pass

        # -- Step 4: table walks (standard + vendor) --
        walks = dict(_STANDARD_TABLE_WALKS)
        walks.update(_vendor_table_roots(vendor))
        walked = self._walk_roots(host, walks)
        walk_oid_count = len(walked)
        raw.update(walked)

        logger.info(
            "%s walk complete: %d OID roots walked, %d total OIDs in raw",
            host, len(walks), len(raw),
        )

        # -- Step 5: normalize --
        device = self._normalizer.normalize(raw, vendor=vendor, device_type=device_type)

        # -- Step 6: build registry (no files) --
        registry = build_registry(
            vendor=vendor, walk=raw,
            sys_descr=device.sys_descr,
            device_type=device_type,
        )

        # -- Step 7: run collectors --
        collectors_out: dict[str, Any] = {}
        unsupported:    list[str]      = []

        logger.info("%s running %d collectors", host, len(_COLLECTORS))

        for collector in _COLLECTORS:
            c_t0 = time.perf_counter()
            try:
                resp = collector.collect(device, registry, registry.profile)
                c_ms = round((time.perf_counter() - c_t0) * 1000, 1)
                from backend.observability import record_collector_duration  # noqa: PLC0415
                record_collector_duration(c_ms)

                collectors_out[collector.name] = resp.to_dict()

                if resp.supported:
                    # Summarise data keys so it's visible without full dump
                    data_keys = list(resp.data.keys()) if resp.data else []
                    # Count items for list-valued fields
                    counts = {
                        k: len(v) for k, v in resp.data.items()
                        if isinstance(v, list) and v
                    } if resp.data else {}
                    logger.info(
                        "  %-16s OK      ms=%-6.1f keys=%s counts=%s warn=%s",
                        collector.name, c_ms, data_keys, counts,
                        resp.warnings or "-",
                    )
                else:
                    unsupported.append(collector.name)
                    logger.info(
                        "  %-16s SKIP    ms=%-6.1f reason=%s missing=%s",
                        collector.name, c_ms,
                        (resp.reason or "")[:120],
                        resp.missing or [],
                    )

            except Exception as exc:
                c_ms = round((time.perf_counter() - c_t0) * 1000, 1)
                from backend.observability import record_collector_duration  # noqa: PLC0415
                record_collector_duration(c_ms)
                logger.error(
                    "  %-16s ERROR   ms=%-6.1f %s: %s",
                    collector.name, c_ms,
                    type(exc).__name__, exc,
                    exc_info=True,
                )
                collectors_out[collector.name] = {
                    "collector": collector.name,
                    "supported": False,
                    "reason":    f"{type(exc).__name__}: {exc}",
                    "missing":   [],
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                }
                unsupported.append(collector.name)

        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        supported_count = len(_COLLECTORS) - len(unsupported)
        logger.info(
            "%s collection done: %d/%d collectors supported, %.1f ms total",
            host, supported_count, len(_COLLECTORS), elapsed,
        )
        if unsupported:
            logger.info("  unsupported: %s", unsupported)

        system_data = (collectors_out.get("system") or {}).get("data") or {}
        interface_data = (collectors_out.get("interfaces") or {}).get("data") or {}
        interface_rows = interface_data.get("interfaces") if isinstance(interface_data, dict) else []
        discovered_mac = system_data.get("mac_address")
        if not discovered_mac and isinstance(interface_rows, list):
            discovered_mac = next(
                (row.get("mac") for row in interface_rows if isinstance(row, dict) and row.get("mac")),
                None,
            )

        return {
            "api_version":   API_VERSION,
            "ip":            host,
            "reachable":     True,
            "snmp_enabled":  True,
            "snmp_version":  self.credentials.version,
            "vendor":        vendor,
            "device_type":   device_type,
            "hostname":      device.hostname,
            "sys_object_id": device.sys_object_id,
            "uptime_seconds": device.uptime_seconds,
            "mac_address":   discovered_mac,
            "collection_ms": elapsed,
            "collectors":    collectors_out,
            "unsupported":   unsupported,
        }

    def collect_domain(self, host: str, domain: str) -> dict[str, Any]:
        """Single-domain collection for polling scheduler."""
        collector = next((c for c in _COLLECTORS if c.name == domain), None)
        if not collector:
            return {"supported": False, "reason": f"Unknown domain: {domain!r}"}

        raw: dict[str, Any] = {}
        try:
            raw.update(self.client.get(host, _IDENTITY_OIDS))
        except Exception as exc:
            return {"supported": False, "reason": str(exc)}

        detection   = self._detector.detect_from_walk(raw)
        vendor      = detection["vendor"]
        device_type = detection["device_type"]

        raw.update(self._walk_roots(host, _DOMAIN_WALKS.get(domain) or {}))

        device   = self._normalizer.normalize(raw, vendor=vendor, device_type=device_type)
        registry = build_registry(vendor=vendor, walk=raw)
        c_t0 = time.perf_counter()
        try:
            result = collector.collect(device, registry, registry.profile).to_dict()
            from backend.observability import record_collector_duration  # noqa: PLC0415
            record_collector_duration((time.perf_counter() - c_t0) * 1000)
            return result
        except Exception as exc:
            from backend.observability import record_collector_duration  # noqa: PLC0415
            record_collector_duration((time.perf_counter() - c_t0) * 1000)
            return {"supported": False, "reason": str(exc)}

    @staticmethod
    def _dead(host: str, reason: str) -> dict[str, Any]:
        return {
            "api_version":   API_VERSION,
            "ip":            host,
            "reachable":     False,
            "snmp_enabled":  False,
            "snmp_version":  None,
            "vendor":        None,
            "device_type":   None,
            "hostname":      None,
            "collection_ms": 0,
            "collectors":    {},
            "unsupported":   [],
            "error":         reason,
        }


# Per-domain minimal walks for polling
_DOMAIN_WALKS: dict[str, dict[str, str]] = {
    "system":     {},
    "cpu":        {"hr_proc":    "1.3.6.1.2.1.25.3.3.1"},
    "memory":     {"hr_storage": "1.3.6.1.2.1.25.2.3.1"},
    "storage":    {"hr_storage": "1.3.6.1.2.1.25.2.3.1"},
    "interfaces": {"if_table":   "1.3.6.1.2.1.2.2.1",
                   "if_ext":     "1.3.6.1.2.1.31.1.1.1"},
    "environment":{"entity":     "1.3.6.1.2.1.47.1.1.1.1",
                   "sensor":     "1.3.6.1.2.1.99.1.1.1"},
    "vlan":       {"vlans":      "1.3.6.1.2.1.17.7.1.4.3.1"},
    "lldp":       {"lldp":       "1.0.8802.1.1.2.1.4"},
    "cdp":        {"cdp":        "1.3.6.1.4.1.9.9.23.1.2.1.1"},
    "routing":    {"routing":    "1.3.6.1.2.1.4.21.1"},
    "arp":        {"arp":        "1.3.6.1.2.1.4.22.1"},
    # Include the Q-BRIDGE FDB as well as the legacy Bridge-MIB FDB. The
    # Q-BRIDGE row index contains <vlan_id>.<mac>, which is the only reliable
    # VLAN source for a MAC-table entry on VLAN-aware switches.
    "mac_table":  {"mac":        "1.3.6.1.2.1.17.4.3.1",
                   "mac_qbridge": "1.3.6.1.2.1.17.7.1.2.2.1",
                   "bridge_ports": "1.3.6.1.2.1.17.1.4.1"},
    "inventory":  {"entity":     "1.3.6.1.2.1.47.1.1.1.1"},
    "health":     {},
    "topology":   {"lldp":       "1.0.8802.1.1.2.1.4",
                   "arp":        "1.3.6.1.2.1.4.22.1",
                   "mac":        "1.3.6.1.2.1.17.4.3.1",
                   "interfaces": "1.3.6.1.2.1.2.2.1",
                   "if_ext":     "1.3.6.1.2.1.31.1.1.1",
                   "routing":    "1.3.6.1.2.1.4.21.1"},
}


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------

class SNMPDiscovery(SNMPService):
    """Read-only SNMP discovery adapter that returns the complete collection."""
    def __init__(self, communities=None, timeout_seconds=2.0, snmp_version="v2c",
                 username=None, auth_protocol=None, auth_password=None,
                 privacy_protocol=None, privacy_password=None, security_level=None):
        super().__init__(SNMPCredentials(
            version=snmp_version,
            community=(communities or ["public"])[0],
            username=username, auth_protocol=auth_protocol,
            auth_password=auth_password, privacy_protocol=privacy_protocol,
            privacy_password=privacy_password, security_level=security_level,
        ), timeout=timeout_seconds)

    def collect(self, host: str) -> dict[str, Any]:
        # Scanning has no persistence side effect. The caller decides whether
        # to add the returned device, while receiving the same full collector
        # document used by the per-device discovery API.
        return super().collect(host)


SNMPCollector = SNMPService
