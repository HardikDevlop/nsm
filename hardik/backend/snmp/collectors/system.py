"""
System Collector — device identity, inventory scalars, uptime.

Standard OIDs used
------------------
  sysDescr    1.3.6.1.2.1.1.1.0
  sysObjectID 1.3.6.1.2.1.1.2.0
  sysUpTime   1.3.6.1.2.1.1.3.0
  sysContact  1.3.6.1.2.1.1.4.0
  sysName     1.3.6.1.2.1.1.5.0
  sysLocation 1.3.6.1.2.1.1.6.0

Vendor extensions used for model / serial / firmware / os_version
are resolved through the OIDRegistry — the collector never sees raw OIDs.
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice, uptime as _uptime


class SystemCollector(BaseCollector):
    """
    Returns full device identity:
      hostname, description, vendor, model, serial_number, firmware,
      os_version, uptime, contact, location, device_type, sys_object_id
    """

    name = "system"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        missing: list[str] = []
        warnings: list[str] = []

        # ---------------------------------------------------------------
        # All scalar fields come from the RawDevice produced by the
        # normalizer, not directly from OIDs.
        # ---------------------------------------------------------------

        # Support both new (RawDevice) and legacy (flat dict) raw inputs.
        if isinstance(raw, RawDevice):
            device = raw
        else:
            # Legacy path: build a minimal RawDevice from the flat dict.
            from ..normalizer import NormalizationLayer  # noqa: PLC0415
            device = NormalizationLayer().normalize(raw)

        # --- Required fields ---
        hostname = device.hostname
        sys_descr = device.sys_descr

        if not hostname:
            missing.append("sysName")
        if not sys_descr:
            missing.append("sysDescr")

        # --- Uptime ---
        ut = _uptime(device.uptime_ticks)

        # --- Vendor-extension scalars (model, serial, firmware, os) ---
        model        = self._resolve_vendor_scalar(device, oid_registry, "system", "model")
        serial       = self._resolve_vendor_scalar(device, oid_registry, "system", "serial")
        firmware     = self._resolve_vendor_scalar(device, oid_registry, "system", "firmware")
        os_version   = self._resolve_vendor_scalar(device, oid_registry, "system", "os_version")

        # Some vendors expose ios_version instead of os_version
        if not os_version:
            os_version = self._resolve_vendor_scalar(device, oid_registry, "system", "ios_version")

        # --- Hardware revision from ENTITY-MIB (chassis entity index = 1) ---
        hw_rev = None
        hw_prefix = "1.3.6.1.2.1.47.1.1.1.1.8."   # entPhysicalHardwareRev
        fw_prefix  = "1.3.6.1.2.1.47.1.1.1.1.9."   # entPhysicalFirmwareRev
        sw_prefix  = "1.3.6.1.2.1.47.1.1.1.1.10."  # entPhysicalSoftwareRev
        sn_prefix  = "1.3.6.1.2.1.47.1.1.1.1.11."  # entPhysicalSerialNum
        mn_prefix  = "1.3.6.1.2.1.47.1.1.1.1.13."  # entPhysicalModelName

        if isinstance(raw, dict):
            raw_flat = raw
        else:
            raw_flat = device.raw

        if not firmware:
            firmware = self.text(raw_flat.get(fw_prefix + "1"))
        if not os_version:
            os_version = self.text(raw_flat.get(sw_prefix + "1"))
        if not serial:
            serial = self.text(raw_flat.get(sn_prefix + "1"))
        if not model:
            model = self.text(raw_flat.get(mn_prefix + "1"))
        hw_rev = self.text(raw_flat.get(hw_prefix + "1"))

        # --- Track missing optional fields as warnings ---
        for label, val in [("model", model), ("serial_number", serial),
                            ("firmware", firmware), ("os_version", os_version)]:
            if not val:
                self.warn(warnings, f"{label} not available for vendor={device.vendor!r}")

        data: dict[str, Any] = {
            "hostname":      hostname,
            "description":   sys_descr,
            "vendor":        device.vendor,
            "device_type":   device.device_type,
            "model":         model,
            "serial_number": serial,
            "firmware":      firmware,
            "os_version":    os_version,
            "hardware_rev":  hw_rev,
            "uptime": {
                "ticks":   device.uptime_ticks,
                "seconds": ut["seconds"],
                "display": ut["display"],
            },
            "contact":       device.contact,
            "location":      device.location,
            "sys_object_id": device.sys_object_id,
        }

        supported = bool(hostname or sys_descr)
        if not supported:
            return CollectorResponse.unsupported(
                self.name,
                reason="sysName and sysDescr both absent — device unreachable or SNMP not enabled",
                missing=missing,
            )

        return CollectorResponse.ok(self.name, data, missing, warnings)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_vendor_scalar(
        device: RawDevice,
        oid_registry: Any,
        domain: str,
        metric: str,
    ) -> str | None:
        """Look up a vendor scalar via oid_registry then raw vendor_scalars."""
        key = f"{domain}.{metric}"
        val = device.vendor_scalars.get(key)
        if val is not None:
            s = str(val).strip()
            return s if s else None
        # Try a direct OID lookup
        if oid_registry:
            oid = oid_registry.resolve(domain, metric)
            if oid:
                val = device.raw.get(oid) or device.raw.get(oid + ".0")
                if val is not None:
                    s = str(val).strip()
                    return s if s else None
        return None
