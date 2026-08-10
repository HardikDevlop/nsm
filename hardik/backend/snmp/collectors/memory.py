"""
Memory Collector — multi-vendor RAM utilization.

Resolution order
----------------
1. UCD-SNMP-MIB   (Linux net-snmp: memTotalReal, memAvailReal, cached, buffers)
2. HOST-RESOURCES-MIB hrStorageTable (type = hrStorageRam)
3. Vendor-specific OIDs via OIDRegistry

Returned fields (all sizes in bytes)
--------------------------------------
    total_bytes        int | None
    used_bytes         int | None
    free_bytes         int | None
    cached_bytes       int | None
    buffer_bytes       int | None
    swap_total_bytes   int | None
    swap_free_bytes    int | None
    utilization_percent float | None   0–100
    display            str             "used / total  (X%)"
    source             str             which MIB / vendor provided the data
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice


# hrStorageType OID for physical RAM
_HR_STORAGE_RAM = "1.3.6.1.2.1.25.2.1.2"

# hrStorageTable column prefixes
_HR_TYPE  = "1.3.6.1.2.1.25.2.3.1.2."
_HR_UNITS = "1.3.6.1.2.1.25.2.3.1.4."
_HR_SIZE  = "1.3.6.1.2.1.25.2.3.1.5."
_HR_USED  = "1.3.6.1.2.1.25.2.3.1.6."

# UCD-SNMP OIDs
_UCD_TOTAL  = "1.3.6.1.4.1.2021.4.5.0"
_UCD_AVAIL  = "1.3.6.1.4.1.2021.4.6.0"
_UCD_FREE   = "1.3.6.1.4.1.2021.4.11.0"
_UCD_CACHED = "1.3.6.1.4.1.2021.4.15.0"
_UCD_BUFFER = "1.3.6.1.4.1.2021.4.14.0"
_UCD_SHARED = "1.3.6.1.4.1.2021.4.13.0"
_UCD_SWAP_T = "1.3.6.1.4.1.2021.4.3.0"
_UCD_SWAP_F = "1.3.6.1.4.1.2021.4.4.0"


def _fmt(value: int | None) -> str:
    """Human-readable bytes → GiB / MiB / KiB / B."""
    if value is None:
        return "N/A"
    for unit, div in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if value >= div:
            return f"{value / div:.1f} {unit}"
    return f"{value} B"


class MemoryCollector(BaseCollector):
    """
    Enterprise memory collector.
    Supports: HOST-RESOURCES-MIB, UCD-SNMP, Cisco, Fortinet,
              Huawei, Juniper, Palo Alto, MikroTik, Linux, Windows.
    """

    name = "memory"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        missing:  list[str] = []
        warnings: list[str] = []

        # Normalizer path
        if isinstance(raw, RawDevice):
            device = raw
            raw_flat = device.raw
        else:
            from ..normalizer import NormalizationLayer  # noqa: PLC0415
            device = NormalizationLayer().normalize(raw)
            raw_flat = raw

        total: int | None  = None
        used:  int | None  = None
        free:  int | None  = None
        cached:  int | None = None
        buffers: int | None = None
        swap_total: int | None = None
        swap_free:  int | None = None
        source = "none"

        # ---------------------------------------------------------------
        # 1. Normalizer already computed memory scalars
        # ---------------------------------------------------------------
        if device.mem_total:
            total   = device.mem_total
            used    = device.mem_used
            free    = device.mem_free
            cached  = device.mem_cached
            buffers = device.mem_buffers
            swap_total = device.mem_swap_total
            swap_free  = device.mem_swap_free
            source  = "normalizer"

        # ---------------------------------------------------------------
        # 2. UCD-SNMP direct (Linux / BSD)
        # ---------------------------------------------------------------
        if total is None:
            total_kb = self.num(raw_flat.get(_UCD_TOTAL))
            if total_kb:
                avail_kb  = self.num(raw_flat.get(_UCD_AVAIL))
                free_kb   = self.num(raw_flat.get(_UCD_FREE))
                cached_kb = self.num(raw_flat.get(_UCD_CACHED))
                buffer_kb = self.num(raw_flat.get(_UCD_BUFFER))
                swap_t_kb = self.num(raw_flat.get(_UCD_SWAP_T))
                swap_f_kb = self.num(raw_flat.get(_UCD_SWAP_F))
                total   = int(total_kb) * 1024
                cached  = int(cached_kb) * 1024 if cached_kb else None
                buffers = int(buffer_kb) * 1024 if buffer_kb else None
                swap_total = int(swap_t_kb) * 1024 if swap_t_kb else None
                swap_free  = int(swap_f_kb) * 1024 if swap_f_kb else None
                if avail_kb:
                    free = int(avail_kb) * 1024
                    used = total - free
                source = "ucd-snmp"

        # ---------------------------------------------------------------
        # 3. HOST-RESOURCES-MIB hrStorageTable (RAM row)
        # ---------------------------------------------------------------
        if total is None:
            total, used, free = self._try_hr_storage(raw_flat, warnings)
            if total is not None:
                source = "hr-storage"

        # ---------------------------------------------------------------
        # 4. Vendor-specific OIDs via OIDRegistry
        # ---------------------------------------------------------------
        if total is None and oid_registry:
            total, used, free = self._try_vendor(raw_flat, oid_registry, warnings)
            if total is not None:
                source = f"vendor:{getattr(vendor_profile, 'vendor', 'unknown')}"

        # ---------------------------------------------------------------
        # Nothing found
        # ---------------------------------------------------------------
        if total is None:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "No memory OID responded: tried UCD-SNMP (1.3.6.1.4.1.2021.4.x), "
                    "hrStorageTable (1.3.6.1.2.1.25.2.3.1), and vendor profile OIDs"
                ),
                missing=["memTotalReal", "hrStorageSize", "vendor.memory"],
            )

        # ---------------------------------------------------------------
        # Derive free / used if only one is present
        # ---------------------------------------------------------------
        if free is None and used is not None:
            free = total - used
        if used is None and free is not None:
            used = total - free

        utilization = self.percent(used, total)

        # Display string
        display = (
            f"{_fmt(used)} / {_fmt(total)}"
            + (f" ({utilization:.1f}%)" if utilization is not None else "")
        )

        data: dict[str, Any] = {
            "total_bytes":        total,
            "used_bytes":         used,
            "free_bytes":         free,
            "cached_bytes":       cached,
            "buffer_bytes":       buffers,
            "swap_total_bytes":   swap_total,
            "swap_free_bytes":    swap_free,
            "utilization_percent": utilization,
            "display":            display,
            "source":             source,
        }

        return CollectorResponse.ok(self.name, data, missing, warnings)

    # ------------------------------------------------------------------
    # HR-MIB hrStorageTable
    # ------------------------------------------------------------------

    def _try_hr_storage(
        self,
        raw: dict[str, Any],
        warnings: list[str],
    ) -> tuple[int | None, int | None, int | None]:
        """
        Scan hrStorageTable for the RAM row (type == hrStorageRam).
        Returns (total_bytes, used_bytes, free_bytes).
        """
        # Collect all indexes from hrStorageType
        for k, v in raw.items():
            if not k.startswith(_HR_TYPE):
                continue
            if _HR_STORAGE_RAM not in str(v):
                continue
            idx = k[len(_HR_TYPE):]
            unit = self.num(raw.get(_HR_UNITS + idx)) or 1
            size = self.num(raw.get(_HR_SIZE + idx))
            used = self.num(raw.get(_HR_USED + idx))
            if size is not None:
                total_b = int(size) * int(unit)
                used_b  = int(used) * int(unit) if used is not None else None
                free_b  = (total_b - used_b) if used_b is not None else None
                return total_b, used_b, free_b
        return None, None, None

    # ------------------------------------------------------------------
    # Vendor OID strategy
    # ------------------------------------------------------------------

    def _try_vendor(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        warnings: list[str],
    ) -> tuple[int | None, int | None, int | None]:
        """
        Try vendor profile OIDs total_kb / used_kb / free_kb (and _bytes variants).
        Returns (total_bytes, used_bytes, free_bytes).
        """
        def _get(metric: str) -> int | None:
            oid = oid_registry.resolve("memory", metric)
            if not oid:
                return None
            v = self.num(raw.get(oid) or raw.get(oid + ".0"))
            return int(v) if v is not None else None

        # Try KB first
        t_kb = _get("total_kb")
        if t_kb is not None:
            u_kb = _get("used_kb")
            f_kb = _get("free_kb")
            mult = 1024
            return (
                t_kb * mult,
                u_kb * mult if u_kb is not None else None,
                f_kb * mult if f_kb is not None else None,
            )

        # Try bytes
        t_b = _get("total_bytes")
        if t_b is not None:
            u_b = _get("used_bytes")
            f_b = _get("free_bytes")
            return t_b, u_b, f_b

        # Try MB
        t_mb = _get("total_mb")
        if t_mb is not None:
            mult = 1024 * 1024
            u_mb = _get("used_mb")
            f_mb = _get("free_mb")
            return (
                t_mb * mult,
                u_mb * mult if u_mb is not None else None,
                f_mb * mult if f_mb is not None else None,
            )

        return None, None, None
