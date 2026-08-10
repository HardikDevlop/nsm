"""
Agnigate NMS — Vendor Detector
================================
Identifies device vendor and type from SNMP identity OIDs.

All fingerprint data lives in oid_catalog.py as Python dicts.
No files, no YAML, no JSON, no database lookups.

Detection order (highest priority first)
-----------------------------------------
1. sysObjectID prefix match   (most reliable — IANA-registered)
2. sysDescr keyword match     (case-insensitive substring scan)
3. "generic" fallback

Device-type inference uses sysDescr regex patterns defined in-module.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from .oid_catalog import VENDOR_SYSOID_PREFIXES, VENDOR_DESCR_KEYWORDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device-type inference patterns (sysDescr → role)
# ---------------------------------------------------------------------------

_DEVICE_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"firewall|asa\b|ftd\b|utm\b|xg\s*\d|fortigate|pan-?os"
                r"|check.?point|bigip|sophos", re.I),             "firewall"),
    (re.compile(r"wireless.controller|wlc\b|capwap|airespace"
                r"|aruba.controller", re.I),                       "wireless_controller"),
    (re.compile(r"access.?point|ap\d{3}|aironet|unifi.ap|wap\b"
                r"|802\.11", re.I),                                "access_point"),
    (re.compile(r"router\b|routing|asr\d|isr\d|mx\d{3}|ne\d{4}"
                r"|ar\d{3}", re.I),                                "router"),
    (re.compile(r"switch|catalyst\s*\d|nexus\s*\d|s\d{4}[a-z]"
                r"|ex\d{4}|qfx|procurve|comware", re.I),          "switch"),
    (re.compile(r"esxi|vsphere|proxmox|hypervisor|xen\b|kvm\b", re.I), "hypervisor"),
    (re.compile(r"synology|qnap|freenas|truenas|diskstation|nas\b", re.I), "nas"),
    (re.compile(r"windows.server|server\s20\d{2}", re.I),         "server"),
    (re.compile(r"linux|ubuntu|debian|centos|rhel|fedora|suse"
                r"|alpine|net-snmp", re.I),                        "server"),
]

# Pre-sort sysObjectID prefixes by length descending (longest = most specific wins)
_SORTED_OID_PREFIXES: list[tuple[str, str]] = sorted(
    VENDOR_SYSOID_PREFIXES.items(), key=lambda x: -len(x[0])
)


class VendorDetector:
    """
    Stateless vendor / device-type detector.
    No constructor arguments — all data comes from oid_catalog.py.
    """

    def detect(
        self,
        sys_object_id: str | None = None,
        sys_descr: str | None = None,
    ) -> str:
        """
        Return the vendor key (e.g. "cisco") or "generic" if unknown.

        Parameters
        ----------
        sys_object_id : value of OID 1.3.6.1.2.1.1.2.0
        sys_descr     : value of OID 1.3.6.1.2.1.1.1.0
        """
        # 1. sysObjectID prefix match
        if sys_object_id:
            oid = str(sys_object_id).strip()
            for prefix, vendor in _SORTED_OID_PREFIXES:
                if oid.startswith(prefix) or oid == prefix.rstrip("."):
                    logger.debug("Vendor via sysObjectID %r → %r", prefix, vendor)
                    return vendor

        # 2. sysDescr keyword match
        if sys_descr:
            text = str(sys_descr).lower()
            for vendor, keywords in VENDOR_DESCR_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    logger.debug("Vendor via sysDescr keyword → %r", vendor)
                    return vendor

        logger.debug("Vendor unknown; using generic")
        return "generic"

    def detect_device_type(
        self,
        sys_descr: str | None = None,
    ) -> str:
        """Infer device role from sysDescr. Returns 'unknown' if unrecognised."""
        if sys_descr:
            for pattern, dtype in _DEVICE_TYPE_PATTERNS:
                if pattern.search(sys_descr):
                    return dtype
        return "unknown"

    def full_detect(
        self,
        sys_object_id: str | None = None,
        sys_descr: str | None = None,
    ) -> dict[str, str]:
        """
        Detect vendor AND device type in one call.
        Returns {"vendor": "...", "device_type": "..."}
        """
        vendor = self.detect(sys_object_id=sys_object_id, sys_descr=sys_descr)
        dtype  = self.detect_device_type(sys_descr=sys_descr)
        return {"vendor": vendor, "device_type": dtype}

    def detect_from_walk(self, walk: dict[str, Any]) -> dict[str, str]:
        """
        Detect vendor and type directly from a completed SNMP walk dict.
        Extracts sysObjectID and sysDescr from the walk automatically.
        """
        sys_oid   = walk.get("1.3.6.1.2.1.1.2.0")
        sys_descr = walk.get("1.3.6.1.2.1.1.1.0")
        return self.full_detect(
            sys_object_id=str(sys_oid)  if sys_oid   else None,
            sys_descr=    str(sys_descr) if sys_descr else None,
        )
