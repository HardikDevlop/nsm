"""
Agnigate NMS — OID Mapper
==========================
DynamicVendorProfile is built at runtime from the live SNMP walk result.
There are no JSON files, no filesystem reads, no static vendor configs.

How it works
------------
1. SNMPService walks the device and collects a flat OID→value dict.
2. VendorDetector identifies the vendor from sysObjectID / sysDescr.
3. OIDRegistry wraps the raw walk + vendor key.
4. Every collector calls OIDRegistry.resolve(domain, metric) which:
     a. Probes the walk dict for the vendor OID (from oid_catalog.py)
     b. Falls back to standard MIB OIDs
     c. Returns the OID string if the walk contained a value for it,
        OR returns the OID string unconditionally so the collector can
        attempt a GET if the walk was incomplete.
5. OIDRegistry.value(domain, metric) → actual value from the walk.

This means the system auto-discovers what each device supports by
checking what OIDs actually responded — no assumptions, no guesses.
"""

from __future__ import annotations

import logging
from typing import Any

from .oid_catalog import (
    STANDARD_OIDS,
    VENDOR_OID_CATALOG,
    get_vendor_oid,
    get_standard_oid,
    get_all_vendor_oids_for_domain,
    decode_vendor_status,
    VENDOR_SYSOID_PREFIXES,
    VENDOR_DESCR_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Re-export for backward compat
VENDOR_OIDS = VENDOR_OID_CATALOG


# ---------------------------------------------------------------------------
# DynamicVendorProfile
# ---------------------------------------------------------------------------

class DynamicVendorProfile:
    """
    Represents everything the system knows about the target device.

    Built entirely from runtime data:
      - vendor_key : detected vendor string (e.g. "cisco")
      - walk       : the raw OID→value dict from the SNMP walk
      - sys_descr  : sysDescr string (for device type inference)

    No files are read. No static data beyond oid_catalog.py is used.
    """

    __slots__ = ("vendor", "walk", "sys_descr", "device_type",
                 "_supported_cache")

    def __init__(
        self,
        vendor: str,
        walk: dict[str, Any],
        sys_descr: str | None = None,
        device_type: str | None = None,
    ) -> None:
        self.vendor      = vendor
        self.walk        = walk
        self.sys_descr   = sys_descr or ""
        self.device_type = device_type or "unknown"
        # Cache of OIDs that the walk confirmed as present
        self._supported_cache: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # OID resolution
    # ------------------------------------------------------------------

    def get_oid(self, domain: str, metric: str) -> str | None:
        """
        Return the best OID for domain.metric.
        Priority: vendor catalog OID → standard MIB OID.
        Returns the OID string regardless of whether the walk saw it
        (the collector will decide what to do with an absent OID).
        """
        oid = get_vendor_oid(self.vendor, domain, metric)
        if oid:
            return oid
        # Try standard MIB key as "domain.metric" then bare "metric"
        return STANDARD_OIDS.get(f"{domain}.{metric}") or STANDARD_OIDS.get(metric)

    def walk_value(self, domain: str, metric: str) -> Any:
        """Return the value from the walk for domain.metric, or None."""
        oid = self.get_oid(domain, metric)
        if not oid:
            return None
        return self._get_walk(oid)

    def has_oid(self, domain: str, metric: str) -> bool:
        """Return True if the walk contained a non-empty value for this OID."""
        oid = self.get_oid(domain, metric)
        if not oid:
            return False
        cache_key = oid
        if cache_key not in self._supported_cache:
            v = self._get_walk(oid)
            self._supported_cache[cache_key] = v is not None
        return self._supported_cache[cache_key]

    def probe_domain(self, domain: str) -> dict[str, Any]:
        """
        Return all metric→value pairs for a domain that the walk supports.
        Only includes metrics where the walk contained a non-None value.
        """
        vendor_metrics = get_all_vendor_oids_for_domain(self.vendor, domain)
        result: dict[str, Any] = {}
        for metric, oid in vendor_metrics.items():
            v = self._get_walk(oid)
            if v is not None:
                result[metric] = v
        return result

    def map_status(self, field: str, code: Any) -> str:
        """Translate a vendor status code to a human label."""
        return decode_vendor_status(self.vendor, field, code)

    # ------------------------------------------------------------------
    # Walk scanning helpers
    # ------------------------------------------------------------------

    def scan_prefix(self, oid_prefix: str) -> dict[str, Any]:
        """
        Return all walk entries whose OID starts with oid_prefix.
        Returns {suffix: value} where suffix is the part after the prefix.
        """
        prefix_dot = oid_prefix.rstrip(".") + "."
        return {
            k[len(prefix_dot):]: v
            for k, v in self.walk.items()
            if k.startswith(prefix_dot)
        }

    def scan_table(self, domain: str, table_metric: str) -> dict[str, Any]:
        """Convenience: scan_prefix using a catalogued table OID."""
        oid = self.get_oid(domain, table_metric)
        if not oid:
            return {}
        return self.scan_prefix(oid)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_walk(self, oid: str) -> Any:
        v = self.walk.get(oid)
        if v is None and not oid.endswith(".0"):
            v = self.walk.get(oid + ".0")
        if v is None:
            return None
        s = str(v).strip()
        if s in ("", "N/A", "None", "noSuchObject", "noSuchInstance",
                 "No Such Object", "No Such Instance", "endOfMibView"):
            return None
        return v

    def __repr__(self) -> str:
        return (f"DynamicVendorProfile(vendor={self.vendor!r}, "
                f"device_type={self.device_type!r}, "
                f"walk_oids={len(self.walk)})")


# ---------------------------------------------------------------------------
# OIDRegistry  — what collectors actually use
# ---------------------------------------------------------------------------

class OIDRegistry:
    """
    Thin wrapper that gives collectors a clean interface to OID resolution.

    Collectors call:
        oid  = registry.resolve(domain, metric)
        val  = registry.value(domain, metric)
        rows = registry.walk_table(domain, table_metric)
        ok   = registry.supported(domain, metric)
    """

    def __init__(self, profile: DynamicVendorProfile) -> None:
        self._p = profile

    # -- Resolution --

    def resolve(self, domain: str, metric: str) -> str | None:
        """Return the OID string for domain.metric (vendor first, standard fallback)."""
        return self._p.get_oid(domain, metric)

    def resolve_standard(self, key: str) -> str | None:
        """Return a standard MIB OID by mnemonic key."""
        return STANDARD_OIDS.get(key)

    # -- Value retrieval from the walk --

    def value(self, domain: str, metric: str) -> Any:
        """Return the walk value for domain.metric, or None."""
        return self._p.walk_value(domain, metric)

    def raw_value(self, oid: str) -> Any:
        """Exact OID lookup in the walk (with .0 fallback)."""
        return self._p._get_walk(oid)

    # -- Table scanning --

    def walk_table(self, domain: str, table_metric: str) -> dict[str, Any]:
        """Return {suffix: value} for all walk entries under table OID."""
        return self._p.scan_table(domain, table_metric)

    def walk_prefix(self, oid_prefix: str) -> dict[str, Any]:
        """Return {suffix: value} for all walk entries under raw OID prefix."""
        return self._p.scan_prefix(oid_prefix)

    # -- Support probing --

    def supported(self, domain: str, metric: str) -> bool:
        """Return True if the walk contained a value for this OID."""
        return self._p.has_oid(domain, metric)

    def probe_domain(self, domain: str) -> dict[str, Any]:
        """Return all metric→value pairs the device supports for a domain."""
        return self._p.probe_domain(domain)

    # -- Status decoding --

    def map_status(self, field: str, code: Any) -> str:
        return self._p.map_status(field, code)

    @property
    def vendor(self) -> str:
        return self._p.vendor

    @property
    def device_type(self) -> str:
        return self._p.device_type

    @property
    def profile(self) -> DynamicVendorProfile:
        return self._p


# ---------------------------------------------------------------------------
# Factory — single entry point used by SNMPService
# ---------------------------------------------------------------------------

def build_registry(
    vendor: str,
    walk: dict[str, Any],
    sys_descr: str | None = None,
    device_type: str | None = None,
) -> OIDRegistry:
    """
    Build an OIDRegistry from a completed SNMP walk.
    This is the ONLY function SNMPService should call.
    No files are touched.
    """
    profile = DynamicVendorProfile(
        vendor=vendor,
        walk=walk,
        sys_descr=sys_descr,
        device_type=device_type,
    )
    return OIDRegistry(profile)


# ---------------------------------------------------------------------------
# Legacy shims — keeps existing routes/tests from breaking
# ---------------------------------------------------------------------------

def load_vendor_profile(vendor: str | None) -> DynamicVendorProfile:
    """
    Legacy shim: returns a DynamicVendorProfile with an empty walk.
    Use build_registry() for the real pipeline.
    """
    return DynamicVendorProfile(vendor=vendor or "generic", walk={})


def list_available_vendors() -> list[str]:
    """Return all vendor keys that have catalog entries."""
    return list(VENDOR_OID_CATALOG.keys())


# Keep old import paths working
VendorProfile = DynamicVendorProfile


def detect_vendor(description: str | None) -> str | None:
    """Legacy shim — use VendorDetector.detect() instead."""
    from .vendor_detector import VendorDetector  # noqa: PLC0415
    return VendorDetector().detect(sys_descr=description)


def resolve(metric: str, vendor: str | None = None) -> str | None:
    """Legacy shim — resolves a single metric to OID."""
    if vendor:
        oid = get_vendor_oid(vendor, *metric.split(".", 1)) if "." in metric else None
        if oid:
            return oid
    return STANDARD_OIDS.get(metric)
