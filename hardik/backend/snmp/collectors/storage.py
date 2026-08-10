"""
Storage Collector — HOST-RESOURCES-MIB hrStorageTable.

OID roots
---------
  hrStorageTable           1.3.6.1.2.1.25.2.3.1
    .1  hrStorageIndex
    .2  hrStorageType       (OID: hrStorageFixedDisk = 1.3.6.1.2.1.25.2.1.4)
    .3  hrStorageDescr      (description / mount point)
    .4  hrStorageAllocationUnits  (bytes per unit)
    .5  hrStorageSize       (total units)
    .6  hrStorageUsed       (used units)

Returned fields per volume
--------------------------
    index           int
    filesystem      str     (hrStorageDescr)
    mount_point     str     (extracted from filesystem string)
    type_oid        str     (raw hrStorageType OID suffix)
    type_label      str     (FixedDisk / RAM / VirtualMemory / Other)
    total_bytes     int
    used_bytes      int
    free_bytes      int
    utilization_percent  float
    display         str     "used / total (X%)"
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice


# hrStorageTable column prefixes
_HR_IDX   = "1.3.6.1.2.1.25.2.3.1.1."
_HR_TYPE  = "1.3.6.1.2.1.25.2.3.1.2."
_HR_DESCR = "1.3.6.1.2.1.25.2.3.1.3."
_HR_UNITS = "1.3.6.1.2.1.25.2.3.1.4."
_HR_SIZE  = "1.3.6.1.2.1.25.2.3.1.5."
_HR_USED  = "1.3.6.1.2.1.25.2.3.1.6."

# hrStorageType OID suffixes → human label
_TYPE_MAP: dict[str, str] = {
    "1.3.6.1.2.1.25.2.1.1": "other",
    "1.3.6.1.2.1.25.2.1.2": "ram",
    "1.3.6.1.2.1.25.2.1.3": "virtualMemory",
    "1.3.6.1.2.1.25.2.1.4": "fixedDisk",
    "1.3.6.1.2.1.25.2.1.5": "removableDisk",
    "1.3.6.1.2.1.25.2.1.6": "floppyDisk",
    "1.3.6.1.2.1.25.2.1.7": "compactDisk",
    "1.3.6.1.2.1.25.2.1.8": "ramDisk",
    "1.3.6.1.2.1.25.2.1.9": "flashMemory",
    "1.3.6.1.2.1.25.2.1.10": "networkDisk",
}

# Types to INCLUDE in storage output (skip pure RAM rows)
_STORAGE_TYPES = {
    "1.3.6.1.2.1.25.2.1.4",   # fixedDisk
    "1.3.6.1.2.1.25.2.1.5",   # removableDisk
    "1.3.6.1.2.1.25.2.1.8",   # ramDisk
    "1.3.6.1.2.1.25.2.1.9",   # flashMemory
    "1.3.6.1.2.1.25.2.1.10",  # networkDisk
}


def _fmt(value: int | None) -> str:
    if value is None:
        return "N/A"
    for unit, div in (("TiB", 1 << 40), ("GiB", 1 << 30), ("MiB", 1 << 20)):
        if value >= div:
            return f"{value / div:.1f} {unit}"
    return f"{value} B"


def _mount_from_descr(descr: str) -> str:
    """
    Try to extract a clean mount point from hrStorageDescr.
    Windows drives look like "C:\\ Label:  Serial Number ...".
    Linux entries look like "/", "/home", "/dev/sda1".
    """
    if not descr:
        return ""
    # Windows: take everything up to the first space
    if "\\" in descr:
        return descr.split()[0].rstrip("\\") or descr
    # Linux: the whole string is usually the mount point
    return descr.split()[0]


class StorageCollector(BaseCollector):
    """
    Parses hrStorageTable and returns one entry per physical/network disk.
    RAM and virtual memory rows are excluded from the storage list
    (they are reported by MemoryCollector instead).
    """

    name = "storage"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        missing:  list[str] = []
        warnings: list[str] = []

        # Get flat raw dict
        if isinstance(raw, RawDevice):
            raw_flat = raw.raw
        else:
            raw_flat = raw

        # ---------------------------------------------------------------
        # Build index → row map from hrStorageType OIDs
        # (type column is the most reliable anchor)
        # ---------------------------------------------------------------
        rows: dict[str, dict[str, Any]] = {}
        for k, v in raw_flat.items():
            if k.startswith(_HR_TYPE):
                idx = k[len(_HR_TYPE):]
                rows.setdefault(idx, {})["type_oid"] = str(v).strip()

        if not rows:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "hrStorageTable (1.3.6.1.2.1.25.2.3.1) returned no data — "
                    "HOST-RESOURCES-MIB may not be supported on this device"
                ),
                missing=["hrStorageType", "hrStorageSize"],
            )

        # Populate remaining columns
        for k, v in raw_flat.items():
            for prefix, col in (
                (_HR_DESCR, "descr"),
                (_HR_UNITS, "alloc_units"),
                (_HR_SIZE,  "size"),
                (_HR_USED,  "used"),
            ):
                if k.startswith(prefix):
                    idx = k[len(prefix):]
                    if idx in rows:
                        rows[idx][col] = v

        # ---------------------------------------------------------------
        # Parse each row
        # ---------------------------------------------------------------
        volumes: list[dict[str, Any]] = []
        for idx in sorted(rows.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            row      = rows[idx]
            type_oid = row.get("type_oid", "")
            descr    = str(row.get("descr", "")).strip()
            unit     = self.num(row.get("alloc_units")) or 1
            size     = self.num(row.get("size"))
            used     = self.num(row.get("used"))

            # Skip non-disk entries (RAM / virtual memory)
            if type_oid and type_oid not in _STORAGE_TYPES:
                # But include "other" types that have a filesystem description
                if type_oid not in ("1.3.6.1.2.1.25.2.1.1",) or not descr:
                    continue

            if size is None or int(size) == 0:
                continue   # Skip empty / unmounted entries

            total_bytes = int(size) * int(unit)
            used_bytes  = int(used) * int(unit) if used is not None else None
            free_bytes  = (total_bytes - used_bytes) if used_bytes is not None else None
            utilization = self.percent(used_bytes, total_bytes)
            type_label  = _TYPE_MAP.get(type_oid, "unknown")

            if utilization is not None and utilization > 90:
                self.warn(
                    warnings,
                    f"Volume {descr!r} is {utilization:.1f}% full",
                )

            display = (
                f"{_fmt(used_bytes)} / {_fmt(total_bytes)}"
                + (f" ({utilization:.1f}%)" if utilization is not None else "")
            )

            volumes.append({
                "index":               int(idx) if idx.isdigit() else idx,
                "filesystem":         descr,
                "mount_point":        _mount_from_descr(descr),
                "type":               type_label,
                "type_oid":           type_oid,
                "total_bytes":        total_bytes,
                "used_bytes":         used_bytes,
                "free_bytes":         free_bytes,
                "utilization_percent": utilization,
                "display":            display,
            })

        if not volumes:
            # Table existed but contained only RAM/virtual rows
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "hrStorageTable present but contains no disk volumes "
                    "(only RAM / virtual-memory rows found)"
                ),
                missing=["hrStorageFixedDisk"],
            )

        return CollectorResponse.ok(
            self.name,
            {"volumes": volumes, "volume_count": len(volumes)},
            missing,
            warnings,
        )
