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
import time
from typing import Any

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
        timeout: float = 2.0,
        retries: int = 1,
    ) -> None:
        self.client      = SNMPClient(credentials, timeout, retries)
        self.credentials = credentials
        self._normalizer = NormalizationLayer()
        self._detector   = VendorDetector()

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
        for name, root in walks.items():
            try:
                raw.update(self.client.walk(host, root))
            except Exception as exc:
                logger.debug("Walk %s %s failed: %s", name, root, exc)

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

        for collector in _COLLECTORS:
            try:
                resp = collector.collect(device, registry, registry.profile)
                collectors_out[collector.name] = resp.to_dict()
                if not resp.supported:
                    unsupported.append(collector.name)
            except Exception as exc:
                logger.error("Collector %s error on %s: %s",
                             collector.name, host, exc, exc_info=True)
                collectors_out[collector.name] = {
                    "collector": collector.name,
                    "supported": False,
                    "reason":    f"Internal error: {exc}",
                    "missing":   [],
                }
                unsupported.append(collector.name)

        elapsed = round((time.perf_counter() - t0) * 1000, 1)

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

        for name, root in (_DOMAIN_WALKS.get(domain) or {}).items():
            try:
                raw.update(self.client.walk(host, root))
            except Exception:
                pass

        device   = self._normalizer.normalize(raw, vendor=vendor, device_type=device_type)
        registry = build_registry(vendor=vendor, walk=raw)
        try:
            return collector.collect(device, registry, registry.profile).to_dict()
        except Exception as exc:
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
    "mac_table":  {"mac":        "1.3.6.1.2.1.17.4.3.1"},
    "inventory":  {"entity":     "1.3.6.1.2.1.47.1.1.1.1"},
    "topology":   {"lldp":       "1.0.8802.1.1.2.1.4",
                   "arp":        "1.3.6.1.2.1.4.22.1"},
}


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------

class SNMPDiscovery(SNMPService):
    """Legacy constructor — keeps discovery_routes.py working."""
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


SNMPCollector = SNMPService
