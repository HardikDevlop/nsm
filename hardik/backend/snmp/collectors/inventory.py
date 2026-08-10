"""
Inventory Collector — ENTITY-MIB (RFC 4133) entPhysicalTable.

OID roots used
--------------
  entPhysicalTable  1.3.6.1.2.1.47.1.1.1.1
    .2   entPhysicalDescr
    .3   entPhysicalVendorType
    .4   entPhysicalContainedIn
    .5   entPhysicalClass         (3=chassis, 6=PSU, 7=fan, 8=sensor, 9=module, 10=port, 12=cpu)
    .6   entPhysicalParentRelPos
    .7   entPhysicalName
    .8   entPhysicalHardwareRev
    .9   entPhysicalFirmwareRev
    .10  entPhysicalSoftwareRev
    .11  entPhysicalSerialNum
    .12  entPhysicalMfgName
    .13  entPhysicalModelName
    .16  entPhysicalIsFRU         (1=true, 2=false)

Returned fields
---------------
  chassis       InventoryItem   (physical class = 3)
  modules       list[InventoryItem]  (class = 9)
  cards         list[InventoryItem]  (class = 9, contained in chassis)
  power_supplies list[InventoryItem] (class = 6)
  fans          list[InventoryItem]  (class = 7)
  sensors       list[InventoryItem]  (class = 8)
  ports         list[InventoryItem]  (class = 10)
  other         list[InventoryItem]
  total_count   int

InventoryItem shape
-------------------
  {
    "index":        int,
    "name":         str | None,
    "description":  str | None,
    "class":        str,         # "chassis" | "module" | "fan" | etc.
    "model":        str | None,
    "serial":       str | None,
    "hardware_rev": str | None,
    "firmware_rev": str | None,
    "software_rev": str | None,
    "manufacturer": str | None,
    "is_fru":       bool,
    "parent_index": int | None,
    "parent_rel_pos": int | None,
  }
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# entPhysicalTable column prefixes
_COL_DESCR      = "1.3.6.1.2.1.47.1.1.1.1.2."
_COL_VENDOR_TYPE = "1.3.6.1.2.1.47.1.1.1.1.3."
_COL_CONTAINER  = "1.3.6.1.2.1.47.1.1.1.1.4."
_COL_CLASS      = "1.3.6.1.2.1.47.1.1.1.1.5."
_COL_REL_POS    = "1.3.6.1.2.1.47.1.1.1.1.6."
_COL_NAME       = "1.3.6.1.2.1.47.1.1.1.1.7."
_COL_HW_REV     = "1.3.6.1.2.1.47.1.1.1.1.8."
_COL_FW_REV     = "1.3.6.1.2.1.47.1.1.1.1.9."
_COL_SW_REV     = "1.3.6.1.2.1.47.1.1.1.1.10."
_COL_SERIAL     = "1.3.6.1.2.1.47.1.1.1.1.11."
_COL_MFG        = "1.3.6.1.2.1.47.1.1.1.1.12."
_COL_MODEL      = "1.3.6.1.2.1.47.1.1.1.1.13."
_COL_IS_FRU     = "1.3.6.1.2.1.47.1.1.1.1.16."

# entPhysicalClass integer → label
_PHYS_CLASS: dict[str, str] = {
    "1": "other",     "2": "unknown",   "3": "chassis",
    "4": "backplane", "5": "container", "6": "powerSupply",
    "7": "fan",       "8": "sensor",    "9": "module",
    "10": "port",     "11": "stack",    "12": "cpu",
}


class InventoryCollector(BaseCollector):
    """
    Collects full hardware inventory from ENTITY-MIB entPhysicalTable.
    """

    name = "inventory"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        missing:  list[str] = []
        warnings: list[str] = []

        if isinstance(raw, RawDevice):
            raw_flat = raw.raw
        else:
            raw_flat = raw

        # ---------------------------------------------------------------
        # Gather all entity indexes from entPhysicalClass
        # ---------------------------------------------------------------
        indexes: set[str] = set()
        for k in raw_flat:
            if str(k).startswith(_COL_CLASS):
                indexes.add(str(k)[len(_COL_CLASS):])

        if not indexes:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "ENTITY-MIB (1.3.6.1.2.1.47.1.1.1.1) returned no data — "
                    "device may not support entPhysicalTable"
                ),
                missing=["entPhysicalClass", "entPhysicalDescr"],
            )

        # ---------------------------------------------------------------
        # Build per-index inventory items
        # ---------------------------------------------------------------
        items: list[dict[str, Any]] = []

        for idx in sorted(indexes, key=lambda x: int(x) if x.isdigit() else 0):
            class_code  = str(raw_flat.get(_COL_CLASS + idx, "2")).strip()
            class_label = _PHYS_CLASS.get(class_code, "unknown")

            name     = self.text(raw_flat.get(_COL_NAME    + idx))
            descr    = self.text(raw_flat.get(_COL_DESCR   + idx))
            model    = self.text(raw_flat.get(_COL_MODEL   + idx))
            serial   = self.text(raw_flat.get(_COL_SERIAL  + idx))
            hw_rev   = self.text(raw_flat.get(_COL_HW_REV  + idx))
            fw_rev   = self.text(raw_flat.get(_COL_FW_REV  + idx))
            sw_rev   = self.text(raw_flat.get(_COL_SW_REV  + idx))
            mfg      = self.text(raw_flat.get(_COL_MFG     + idx))
            parent   = self.num(raw_flat.get(_COL_CONTAINER + idx))
            rel_pos  = self.num(raw_flat.get(_COL_REL_POS  + idx))
            is_fru_raw = str(raw_flat.get(_COL_IS_FRU + idx, "2")).strip()
            is_fru   = is_fru_raw == "1"

            items.append({
                "index":         int(idx) if idx.isdigit() else idx,
                "name":          name or descr or f"Entity-{idx}",
                "description":   descr,
                "class":         class_label,
                "model":         model,
                "serial":        serial,
                "hardware_rev":  hw_rev,
                "firmware_rev":  fw_rev,
                "software_rev":  sw_rev,
                "manufacturer":  mfg,
                "is_fru":        is_fru,
                "parent_index":  int(parent) if parent is not None else None,
                "parent_rel_pos": int(rel_pos) if rel_pos is not None else None,
            })

        # ---------------------------------------------------------------
        # Categorise by physical class
        # ---------------------------------------------------------------
        chassis_items = [i for i in items if i["class"] == "chassis"]
        modules       = [i for i in items if i["class"] == "module"]
        psus          = [i for i in items if i["class"] == "powerSupply"]
        fans          = [i for i in items if i["class"] == "fan"]
        sensors       = [i for i in items if i["class"] == "sensor"]
        ports         = [i for i in items if i["class"] == "port"]
        cpus          = [i for i in items if i["class"] == "cpu"]
        other         = [i for i in items if i["class"] not in
                         ("chassis", "module", "powerSupply", "fan",
                          "sensor", "port", "cpu")]

        # Chassis is index 1 by convention
        chassis = chassis_items[0] if chassis_items else None

        if not chassis:
            self.warn(warnings, "entPhysicalTable present but no chassis entry (class=3) found")

        return CollectorResponse.ok(
            self.name,
            {
                "chassis":         chassis,
                "modules":         modules,
                "power_supplies":  psus,
                "fans":            fans,
                "sensors":         sensors,
                "ports":           ports,
                "cpus":            cpus,
                "other":           other,
                "total_count":     len(items),
                "fru_count":       sum(1 for i in items if i["is_fru"]),
            },
            missing,
            warnings,
        )
