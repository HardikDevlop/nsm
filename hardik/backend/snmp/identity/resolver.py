"""
DeviceIdentityResolver — evidence-based multi-signal device identification.

No if/elif vendor chains. Evidence is collected from all available
sources and the highest-confidence signal wins per field.

Evidence priority for vendor
-----------------------------
1. sysObjectID prefix match          confidence = 0.98
2. ENTITY-MIB entPhysicalMfgName     confidence = 0.90
3. sysDescr keyword match            confidence = 0.80
4. MAC/OUI database match            confidence = 0.70
5. User override                     confidence = 1.0  (always wins)
6. Unknown                           confidence = 0.0

Evidence priority for device_type
-----------------------------------
1. device_products catalog match     confidence = 0.95
2. sysDescr pattern                  confidence = 0.80
3. vendor profile device_type_hints  confidence = 0.75
4. Unknown                           confidence = 0.0

The resolver returns an IdentityResult which is then persisted to
device_identity and used to populate the device record.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

from ..vendor_detector import VendorDetector
from .oui import MacOuiResolver, normalize_mac

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IdentityResult:
    """
    The fully-resolved identity for one device.

    Sources
    -------
    Each field has a companion `_source` string indicating which evidence
    provided the value.  Possible sources:
      snmp_sysoid | snmp_descr | entity_mib | mac_oui |
      product_catalog | hostname | user_override | unknown
    """
    vendor:                 str | None = None
    vendor_source:          str = "unknown"
    vendor_confidence:      float = 0.0

    hostname:               str | None = None
    hostname_source:        str = "unknown"

    model:                  str | None = None
    model_source:           str = "unknown"
    model_confidence:       float = 0.0

    serial_number:          str | None = None
    serial_source:          str = "unknown"

    firmware_version:       str | None = None
    os_version:             str | None = None

    device_type:            str | None = None
    device_type_source:     str = "unknown"
    device_type_confidence: float = 0.0

    product_family:         str | None = None
    roles:                  list[str] = field(default_factory=list)

    # SNMP identity OIDs
    sys_object_id:          str | None = None
    sys_descr:              str | None = None
    sys_name:               str | None = None
    sys_contact:            str | None = None
    sys_location:           str | None = None

    # MAC addresses observed
    mac_addresses:          list[str] = field(default_factory=list)

    # Linked product catalog ID (if matched)
    product_id:             int | None = None

    # Overall confidence score (mean of contributing signals)
    identity_confidence:    float = 0.0
    identity_sources:       list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API-friendly dict."""
        return {
            "vendor": self.vendor or "unknown",
            "vendor_source": self.vendor_source,
            "vendor_confidence": self.vendor_confidence,
            "hostname": self.hostname or "Unknown Device",
            "hostname_source": self.hostname_source,
            "model": self.model,
            "model_source": self.model_source,
            "model_confidence": self.model_confidence,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "os_version": self.os_version,
            "device_type": self.device_type or "unknown",
            "device_type_source": self.device_type_source,
            "device_type_confidence": self.device_type_confidence,
            "product_family": self.product_family,
            "roles": self.roles,
            "sys_object_id": self.sys_object_id,
            "sys_descr": self.sys_descr,
            "sys_name": self.sys_name,
            "sys_contact": self.sys_contact,
            "sys_location": self.sys_location,
            "mac_addresses": self.mac_addresses,
            "identity_confidence": self.identity_confidence,
            "identity_sources": self.identity_sources,
            "product_id": self.product_id,
        }


# ---------------------------------------------------------------------------
# DeviceIdentityResolver
# ---------------------------------------------------------------------------

class DeviceIdentityResolver:
    """
    Resolves device identity from all available evidence.

    No vendor-specific logic lives here.
    All product knowledge comes from the device_products database table.
    MAC→vendor knowledge comes from vendor_ouis database table.
    SNMP fingerprints come from oid_catalog.py.

    Usage
    -----
        resolver = DeviceIdentityResolver(db=db_session)
        result = resolver.resolve(
            walk=raw_snmp_dict,
            mac_addresses=["AA:BB:CC:DD:EE:FF"],
            user_overrides={"vendor": "agnigate"},
        )
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._detector = VendorDetector()
        self._oui = MacOuiResolver(db=db)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def resolve(
        self,
        walk: dict[str, Any] | None = None,
        mac_addresses: list[str] | None = None,
        user_overrides: dict[str, Any] | None = None,
        hostname_hint: str | None = None,
    ) -> IdentityResult:
        """
        Build an IdentityResult from all available evidence.

        Parameters
        ----------
        walk            : Raw SNMP OID→value dict from SNMPService.collect()
        mac_addresses   : MAC addresses observed on the device (from walk or ARP)
        user_overrides  : Fields the user has explicitly set (always win)
        hostname_hint   : IP or DNS name to use if SNMP hostname unavailable
        """
        walk = walk or {}
        mac_addresses = mac_addresses or []
        user_overrides = user_overrides or {}
        result = IdentityResult()

        # Normalize MACs
        norm_macs = [m for m in (normalize_mac(m) for m in mac_addresses) if m]
        result.mac_addresses = norm_macs

        # --- 1. Extract SNMP identity scalars ---
        result.sys_object_id = self._str(walk.get("1.3.6.1.2.1.1.2.0"))
        result.sys_descr     = self._str(walk.get("1.3.6.1.2.1.1.1.0"))
        result.sys_name      = self._str(walk.get("1.3.6.1.2.1.1.5.0"))
        result.sys_contact   = self._str(walk.get("1.3.6.1.2.1.1.4.0"))
        result.sys_location  = self._str(walk.get("1.3.6.1.2.1.1.6.0"))

        # --- 2. Hostname ---
        self._resolve_hostname(result, hostname_hint)

        # --- 3. Vendor ---
        self._resolve_vendor(result, walk, norm_macs)

        # --- 4. Device type ---
        self._resolve_device_type(result, walk)

        # --- 5. Hardware identity from ENTITY-MIB ---
        self._resolve_hardware(result, walk)

        # --- 6. Product catalog match ---
        self._resolve_product(result)

        # --- 7. Apply user overrides last (always win) ---
        self._apply_overrides(result, user_overrides)

        # --- 8. Compute overall confidence ---
        scores = [
            c for c in (
                result.vendor_confidence,
                result.model_confidence,
                result.device_type_confidence,
            ) if c > 0
        ]
        result.identity_confidence = round(sum(scores) / len(scores), 3) if scores else 0.0
        result.identity_sources = list({
            result.vendor_source,
            result.hostname_source,
            result.device_type_source,
        } - {"unknown"})

        return result

    # ------------------------------------------------------------------
    # Private resolution steps
    # ------------------------------------------------------------------

    def _resolve_hostname(self, result: IdentityResult, hint: str | None) -> None:
        if result.sys_name and result.sys_name.lower() not in ("(none)", "none"):
            result.hostname = result.sys_name
            result.hostname_source = "snmp_sysname"
        elif hint:
            result.hostname = hint
            result.hostname_source = "ip_hint"
        else:
            result.hostname = "Unknown Device"
            result.hostname_source = "unknown"

    def _resolve_vendor(
        self,
        result: IdentityResult,
        walk: dict[str, Any],
        macs: list[str],
    ) -> None:
        candidates: list[tuple[float, str, str]] = []  # (confidence, vendor, source)

        # a) sysObjectID (highest confidence)
        if result.sys_object_id:
            vendor = self._detector.detect(sys_object_id=result.sys_object_id)
            if vendor != "generic":
                candidates.append((0.98, vendor, "snmp_sysoid"))

        # b) ENTITY-MIB manufacturer (physical entity 1)
        ent_mfg = self._str(walk.get("1.3.6.1.2.1.47.1.1.1.1.12.1"))
        if ent_mfg:
            v_from_mfg = self._vendor_key_from_name(ent_mfg)
            candidates.append((0.90, v_from_mfg or ent_mfg.lower()[:40], "entity_mib"))

        # c) sysDescr keyword match
        if result.sys_descr:
            vendor = self._detector.detect(sys_descr=result.sys_descr)
            if vendor != "generic":
                candidates.append((0.80, vendor, "snmp_descr"))

        # d) MAC/OUI lookup
        for mac in macs[:3]:  # check first 3 MACs
            oui_result = self._oui.resolve(mac)
            if oui_result.get("vendor_key"):
                candidates.append((
                    oui_result.get("confidence", 0.70),
                    oui_result["vendor_key"],
                    "mac_oui",
                ))

        if candidates:
            best = max(candidates, key=lambda x: x[0])
            result.vendor            = best[1]
            result.vendor_confidence = best[0]
            result.vendor_source     = best[2]
        else:
            result.vendor            = "unknown"
            result.vendor_confidence = 0.0
            result.vendor_source     = "unknown"

    def _resolve_device_type(
        self,
        result: IdentityResult,
        walk: dict[str, Any],
    ) -> None:
        # Use VendorDetector sysDescr patterns
        if result.sys_descr:
            dtype = self._detector.detect_device_type(sys_descr=result.sys_descr)
            if dtype != "unknown":
                result.device_type            = dtype
                result.device_type_source     = "snmp_descr"
                result.device_type_confidence = 0.80
                return

        result.device_type            = "unknown"
        result.device_type_source     = "unknown"
        result.device_type_confidence = 0.0

    def _resolve_hardware(self, result: IdentityResult, walk: dict[str, Any]) -> None:
        """Extract model, serial, firmware from ENTITY-MIB (index 1 = chassis)."""
        # entPhysicalModelName
        model = self._str(walk.get("1.3.6.1.2.1.47.1.1.1.1.13.1"))
        if model:
            result.model        = model
            result.model_source = "entity_mib"
            result.model_confidence = 0.90

        # entPhysicalSerialNum
        serial = self._str(walk.get("1.3.6.1.2.1.47.1.1.1.1.11.1"))
        if serial:
            result.serial_number = serial
            result.serial_source = "entity_mib"

        # entPhysicalFirmwareRev
        fw = self._str(walk.get("1.3.6.1.2.1.47.1.1.1.1.9.1"))
        if fw:
            result.firmware_version = fw

        # entPhysicalSoftwareRev
        sw = self._str(walk.get("1.3.6.1.2.1.47.1.1.1.1.10.1"))
        if sw:
            result.os_version = sw

        # If model not found from ENTITY-MIB, try vendor-specific from walk
        if not result.model and result.vendor:
            from backend.snmp.oid_catalog import VENDOR_OID_CATALOG  # noqa: PLC0415
            model_oid = VENDOR_OID_CATALOG.get(result.vendor, {}).get("system", {}).get("model")
            if model_oid:
                v = self._str(walk.get(model_oid) or walk.get(model_oid + ".0"))
                if v:
                    result.model        = v
                    result.model_source = f"vendor:{result.vendor}"
                    result.model_confidence = 0.80

    def _resolve_product(self, result: IdentityResult) -> None:
        """Try to match against the device_products catalog."""
        if not self._db:
            return
        try:
            from backend.models.identity import DeviceProduct  # noqa: PLC0415

            query = self._db.query(DeviceProduct).filter(
                DeviceProduct.is_active.is_(True)
            )

            if result.vendor and result.vendor != "unknown":
                query = query.filter(DeviceProduct.vendor_key == result.vendor)

            products = query.all()

            for prod in products:
                # sysObjectID prefix match
                if prod.sys_object_id_prefix and result.sys_object_id:
                    if result.sys_object_id.startswith(prod.sys_object_id_prefix):
                        self._apply_product(result, prod, 0.95)
                        return

                # model pattern match
                if prod.model_pattern and (result.model or result.sys_descr):
                    text = result.model or result.sys_descr or ""
                    if re.search(prod.model_pattern, text, re.I):
                        self._apply_product(result, prod, 0.88)
                        return

                # descr keyword match
                if prod.descr_keywords and result.sys_descr:
                    descr_lower = result.sys_descr.lower()
                    if all(kw.lower() in descr_lower for kw in prod.descr_keywords):
                        self._apply_product(result, prod, 0.82)
                        return

        except Exception as exc:
            logger.debug("Product catalog match failed: %s", exc)

    @staticmethod
    def _apply_product(
        result: IdentityResult,
        prod: Any,
        confidence: float,
    ) -> None:
        """Apply a product catalog match to the result."""
        result.product_id = prod.id
        if not result.model:
            result.model            = prod.product_name
            result.model_source     = "product_catalog"
            result.model_confidence = confidence
        result.product_family = prod.product_family
        if prod.roles:
            result.roles = list(prod.roles)
        if prod.device_type and result.device_type_confidence < confidence:
            result.device_type            = prod.device_type
            result.device_type_source     = "product_catalog"
            result.device_type_confidence = confidence

    @staticmethod
    def _apply_overrides(
        result: IdentityResult,
        overrides: dict[str, Any],
    ) -> None:
        """User overrides always win."""
        if not overrides:
            return
        if v := overrides.get("vendor"):
            result.vendor            = str(v)
            result.vendor_source     = "user_override"
            result.vendor_confidence = 1.0
        if m := overrides.get("model"):
            result.model            = str(m)
            result.model_source     = "user_override"
            result.model_confidence = 1.0
        if d := overrides.get("device_type"):
            result.device_type            = str(d)
            result.device_type_source     = "user_override"
            result.device_type_confidence = 1.0
        if h := overrides.get("hostname"):
            result.hostname        = str(h)
            result.hostname_source = "user_override"

    @staticmethod
    def _str(value: Any) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        bad = {"", "N/A", "None", "noSuchObject", "noSuchInstance",
               "No Such Object", "No Such Instance", "endOfMibView", "(none)"}
        return s if s not in bad else None

    @staticmethod
    def _vendor_key_from_name(name: str) -> str | None:
        """Try to extract a normalized vendor key from a manufacturer name string."""
        known = {
            "agnigate": "agnigate",
            "cisco": "cisco", "cisco systems": "cisco",
            "fortinet": "fortinet",
            "huawei": "huawei",
            "juniper": "juniper", "juniper networks": "juniper",
            "palo alto": "paloalto", "pan": "paloalto",
            "mikrotik": "mikrotik",
            "sophos": "sophos",
            "linux": "linux",
            "microsoft": "windows",
            "vmware": "vmware",
            "arista": "arista",
            "hewlett": "hp", "hpe": "hp",
            "aruba": "aruba",
            "ubiquiti": "ubiquiti",
            "f5": "f5",
            "check point": "checkpoint",
        }
        lower = name.lower()
        for keyword, key in known.items():
            if keyword in lower:
                return key
        return None
