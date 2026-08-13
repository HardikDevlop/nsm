"""
Agnigate NMS — Normalization Layer
====================================
Converts a raw OID→value walk dict into a typed RawDevice.

Key behaviours
--------------
- No file I/O of any kind.
- Vendor detection runs from the walk itself.
- CPU / memory scalars populated by probing the walk for every
  known OID (standard + vendor) and taking the first hit.
- Table sections are sliced from the walk by OID prefix.
- All values are None when absent — never strings like "Not Supported".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .oid_catalog import STANDARD_OIDS, VENDOR_OID_CATALOG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------

def number(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    try:
        f = float(str(value).replace(",", "").strip())
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def uptime(ticks: Any) -> dict[str, Any]:
    s = number(ticks)
    if s is None:
        return {"seconds": None, "display": None}
    s = round(float(s) / 100, 2)
    d, r  = divmod(int(s), 86400)
    h, r  = divmod(r, 3600)
    m, sc = divmod(r, 60)
    return {"seconds": s, "display": f"{d}d {h:02d}h {m:02d}m {sc:02d}s"}


def mac(value: Any) -> str | None:
    raw = str(value or "").replace("0x","").replace(":","").replace("-","").strip()
    if len(raw) == 12 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return ":".join(raw[i:i+2] for i in range(0, 12, 2)).upper()
    return None


def _clean(value: Any) -> str | None:
    s = str(value).strip() if value is not None else ""
    bad = {"", "N/A", "None", "noSuchObject", "noSuchInstance",
           "No Such Object", "No Such Instance", "endOfMibView"}
    return s if s not in bad else None


# ---------------------------------------------------------------------------
# RawDevice dataclass
# ---------------------------------------------------------------------------

@dataclass
class RawDevice:
    """
    Collector-ready device snapshot.
    All fields are None or empty collection when the device didn't answer.
    No "Not Supported" strings anywhere.
    """
    # Identity
    hostname:        str | None = None
    sys_descr:       str | None = None
    sys_object_id:   str | None = None
    contact:         str | None = None
    location:        str | None = None
    uptime_ticks:    int | None = None
    uptime_seconds:  float | None = None
    uptime_display:  str | None = None

    # Detected at runtime
    vendor:          str | None = None
    device_type:     str | None = None

    # Scalar CPU (whichever source won)
    cpu_overall:     float | None = None
    cpu_user:        float | None = None
    cpu_system:      float | None = None
    cpu_idle:        float | None = None
    cpu_cores:       dict[str, float] = field(default_factory=dict)

    # Scalar memory (bytes)
    mem_total:       int | None = None
    mem_used:        int | None = None
    mem_free:        int | None = None
    mem_cached:      int | None = None
    mem_buffers:     int | None = None
    mem_swap_total:  int | None = None
    mem_swap_free:   int | None = None

    # Table slices (prefix-filtered sub-dicts of the original walk)
    raw_interfaces:  dict[str, Any] = field(default_factory=dict)
    raw_if_ext:      dict[str, Any] = field(default_factory=dict)
    raw_storage:     dict[str, Any] = field(default_factory=dict)
    raw_lldp:        dict[str, Any] = field(default_factory=dict)
    raw_vlans:       dict[str, Any] = field(default_factory=dict)
    raw_routing:     dict[str, Any] = field(default_factory=dict)
    raw_arp:         dict[str, Any] = field(default_factory=dict)
    raw_mac_table:   dict[str, Any] = field(default_factory=dict)
    raw_entity:      dict[str, Any] = field(default_factory=dict)
    raw_entity_sensor: dict[str, Any] = field(default_factory=dict)
    raw_cdp:         dict[str, Any] = field(default_factory=dict)

    # Original walk (kept for collectors that need direct OID access)
    raw: dict[str, Any] = field(default_factory=dict)

    # Vendor scalars derived from the walk (populated by normalizer)
    vendor_scalars: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OID prefix → RawDevice attribute  (for table slicing)
# ---------------------------------------------------------------------------

_TABLE_PREFIXES: dict[str, str] = {
    "1.3.6.1.2.1.2.2.1":        "raw_interfaces",
    "1.3.6.1.2.1.31.1.1.1":     "raw_if_ext",
    "1.3.6.1.2.1.25.2.3.1":     "raw_storage",
    "1.0.8802.1.1.2.1.4":       "raw_lldp",
    "1.3.6.1.2.1.17.7.1.4":     "raw_vlans",
    "1.3.6.1.2.1.4.21.1":       "raw_routing",
    "1.3.6.1.2.1.4.22.1":       "raw_arp",
    "1.3.6.1.2.1.17.4.3.1":     "raw_mac_table",
    "1.3.6.1.2.1.47.1.1.1.1":   "raw_entity",
    "1.3.6.1.2.1.99.1.1.1":     "raw_entity_sensor",
    "1.3.6.1.4.1.9.9.23.1.2":   "raw_cdp",
}


# ---------------------------------------------------------------------------
# NormalizationLayer
# ---------------------------------------------------------------------------

class NormalizationLayer:
    """
    Single-call normalizer: walk dict → RawDevice.

    Usage
    -----
        device = NormalizationLayer().normalize(walk_dict)
    """

    def normalize(
        self,
        raw: dict[str, Any],
        vendor: str | None = None,
        device_type: str | None = None,
    ) -> RawDevice:
        from .vendor_detector import VendorDetector  # local import avoids circularity
        device = RawDevice(raw=raw)

        # -- 1. System scalars --
        device.sys_descr   = _clean(self._g(raw, STANDARD_OIDS["system.description"]))
        device.sys_object_id = _clean(self._g(raw, STANDARD_OIDS["system.object_id"]))
        device.hostname    = _clean(self._g(raw, STANDARD_OIDS["system.name"]))
        device.contact     = _clean(self._g(raw, STANDARD_OIDS["system.contact"]))
        device.location    = _clean(self._g(raw, STANDARD_OIDS["system.location"]))
        ticks = number(self._g(raw, STANDARD_OIDS["system.uptime"]))
        device.uptime_ticks   = int(ticks) if ticks is not None else None
        ut = uptime(ticks)
        device.uptime_seconds = ut["seconds"]
        device.uptime_display = ut["display"]

        # -- 2. Vendor detection (from walk, not from files) --
        if vendor:
            device.vendor = vendor.lower()
        else:
            result = VendorDetector().detect_from_walk(raw)
            device.vendor = result["vendor"]

        device.device_type = device_type or VendorDetector().detect_device_type(
            sys_descr=device.sys_descr
        )

        # -- 3. CPU scalars --
        self._populate_cpu(device, raw)

        # -- 4. Memory scalars --
        self._populate_memory(device, raw)

        # -- 5. Table slices --
        for prefix, attr in _TABLE_PREFIXES.items():
            prefix_dot = prefix + "."
            setattr(device, attr, {
                k: v for k, v in raw.items() if k.startswith(prefix_dot)
            })

        # -- 6. Vendor scalars (all vendor OIDs that responded in the walk) --
        vendor = device.vendor or "generic"
        vendor_scalars: dict[str, Any] = {}
        for domain, metrics in VENDOR_OID_CATALOG.get(vendor, {}).items():
            for metric, oid in metrics.items():
                v = raw.get(oid) or raw.get(oid + ".0") or raw.get(oid.rstrip(".0"))
                if v is not None:
                    s = str(v).strip()
                    if s and s not in ("", "noSuchObject", "noSuchInstance",
                                       "No Such Object", "No Such Instance", "endOfMibView"):
                        vendor_scalars[f"{domain}.{metric}"] = v
        device.vendor_scalars = vendor_scalars

        return device

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    def _populate_cpu(self, device: RawDevice, raw: dict[str, Any]) -> None:
        vendor = device.vendor or "generic"

        # Try vendor-specific scalar OIDs first
        vendor_cpu = VENDOR_OID_CATALOG.get(vendor, {}).get("cpu", {})
        for metric, oid in vendor_cpu.items():
            # Skip table OIDs (they don't end with .0 and have walk rows)
            if "table" in metric:
                continue
            val = number(self._g(raw, oid))
            if val is not None and 0 <= float(val) <= 100:
                device.cpu_overall = float(val)
                return

        # UCD-SNMP idle-based
        idle = number(self._g(raw, STANDARD_OIDS["ucdCpuIdle"]))
        if idle is not None:
            device.cpu_idle   = float(idle)
            user   = number(self._g(raw, STANDARD_OIDS["ucdCpuUser"]))
            system = number(self._g(raw, STANDARD_OIDS["ucdCpuSystem"]))
            device.cpu_user   = float(user)   if user   is not None else None
            device.cpu_system = float(system) if system is not None else None
            device.cpu_overall = round(100.0 - float(idle), 2)
            return

        # hrProcessorLoad table → average
        prefix = STANDARD_OIDS["hrProcessorLoad"] + "."
        cores: dict[str, float] = {}
        for k, v in raw.items():
            if k.startswith(prefix):
                val = number(v)
                if val is not None and 0 <= float(val) <= 100:
                    cores[k[len(prefix):]] = float(val)
        if cores:
            device.cpu_cores   = cores
            device.cpu_overall = round(sum(cores.values()) / len(cores), 2)

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def _populate_memory(self, device: RawDevice, raw: dict[str, Any]) -> None:
        vendor = device.vendor or "generic"

        # UCD-SNMP (Linux / net-snmp) — values in KB
        total_kb = number(self._g(raw, STANDARD_OIDS["ucdMemTotalReal"]))
        if total_kb:
            avail_kb  = number(self._g(raw, STANDARD_OIDS["ucdMemAvailReal"]))
            cached_kb = number(self._g(raw, STANDARD_OIDS["ucdMemCached"]))
            buffer_kb = number(self._g(raw, STANDARD_OIDS["ucdMemBuffer"]))
            swap_t_kb = number(self._g(raw, STANDARD_OIDS["ucdMemTotalSwap"]))
            swap_f_kb = number(self._g(raw, STANDARD_OIDS["ucdMemAvailSwap"]))
            device.mem_total    = int(total_kb)  * 1024
            device.mem_cached   = int(cached_kb) * 1024 if cached_kb else None
            device.mem_buffers  = int(buffer_kb) * 1024 if buffer_kb else None
            device.mem_swap_total = int(swap_t_kb) * 1024 if swap_t_kb else None
            device.mem_swap_free  = int(swap_f_kb) * 1024 if swap_f_kb else None
            if avail_kb:
                device.mem_free = int(avail_kb) * 1024
                device.mem_used = device.mem_total - device.mem_free
            return

        # hrStorageTable — find RAM row (type = 1.3.6.1.2.1.25.2.1.2)
        type_prefix  = STANDARD_OIDS["hrStorageType"]  + "."
        size_prefix  = STANDARD_OIDS["hrStorageSize"]  + "."
        used_prefix  = STANDARD_OIDS["hrStorageUsed"]  + "."
        units_prefix = STANDARD_OIDS["hrStorageAllocationUnits"] + "."
        for k, v in raw.items():
            if not k.startswith(type_prefix):
                continue
            if STANDARD_OIDS["hrStorageRam"] not in str(v):
                continue
            idx  = k[len(type_prefix):]
            unit = number(raw.get(units_prefix + idx)) or 1
            size = number(raw.get(size_prefix  + idx))
            used = number(raw.get(used_prefix  + idx))
            if size:
                device.mem_total = int(size) * int(unit)
                if used is not None:
                    device.mem_used = int(used) * int(unit)
                    device.mem_free = device.mem_total - device.mem_used
            return

        # Vendor-specific memory OIDs
        vendor_mem = VENDOR_OID_CATALOG.get(vendor, {}).get("memory", {})
        for suffix, mult in (("_kb", 1024), ("_bytes", 1), ("_mb", 1024*1024)):
            t_oid = vendor_mem.get(f"total{suffix}")
            if not t_oid:
                continue
            total_raw = number(self._g(raw, t_oid))
            if total_raw is None:
                continue
            device.mem_total = int(total_raw) * mult
            u_oid = vendor_mem.get(f"used{suffix}")
            f_oid = vendor_mem.get(f"free{suffix}")
            if u_oid:
                u = number(self._g(raw, u_oid))
                if u is not None:
                    device.mem_used = int(u) * mult
            if f_oid:
                f = number(self._g(raw, f_oid))
                if f is not None:
                    device.mem_free = int(f) * mult
            if device.mem_used is None and device.mem_free is not None:
                device.mem_used = device.mem_total - device.mem_free
            elif device.mem_free is None and device.mem_used is not None:
                device.mem_free = device.mem_total - device.mem_used
            return

    @staticmethod
    def _g(raw: dict[str, Any], oid: str) -> Any:
        v = raw.get(oid)
        if v is None and oid.endswith(".0"):
            v = raw.get(oid[:-2])
        return v
