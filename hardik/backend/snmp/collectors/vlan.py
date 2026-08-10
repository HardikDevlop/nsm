"""
VLAN Collector — Q-BRIDGE-MIB (RFC 4363).

OID roots used
--------------
  dot1qVlanStaticName          1.3.6.1.2.1.17.7.1.4.3.1.1.<vlan_id>
  dot1qVlanStaticEgressPorts   1.3.6.1.2.1.17.7.1.4.3.1.2.<vlan_id>
  dot1qVlanStaticUntaggedPorts 1.3.6.1.2.1.17.7.1.4.3.1.4.<vlan_id>
  dot1qVlanStaticRowStatus     1.3.6.1.2.1.17.7.1.4.3.1.5.<vlan_id>
  dot1qCurrentEgressPorts      1.3.6.1.2.1.17.7.1.4.2.1.4.<fdb>.<vlan_id>
  dot1qCurrentUntaggedPorts    1.3.6.1.2.1.17.7.1.4.2.1.5.<fdb>.<vlan_id>
  dot1qVlanFdbId               1.3.6.1.2.1.17.7.1.4.2.1.3

Returned fields per VLAN
------------------------
  vlan_id        int
  name           str | None
  status         str       — "active" | "notInService" | "notReady" | "unknown"
  egress_ports   list[int] — port indexes (decoded from port-bitmap)
  untagged_ports list[int]
  tagged_ports   list[int] — egress minus untagged
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# Q-BRIDGE-MIB column prefixes
_STATIC_NAME    = "1.3.6.1.2.1.17.7.1.4.3.1.1."
_STATIC_EGRESS  = "1.3.6.1.2.1.17.7.1.4.3.1.2."
_STATIC_UNTAG   = "1.3.6.1.2.1.17.7.1.4.3.1.4."
_STATIC_STATUS  = "1.3.6.1.2.1.17.7.1.4.3.1.5."
_CURRENT_EGRESS = "1.3.6.1.2.1.17.7.1.4.2.1.4."
_CURRENT_UNTAG  = "1.3.6.1.2.1.17.7.1.4.2.1.5."
_CURRENT_STATUS = "1.3.6.1.2.1.17.7.1.4.2.1.6."

_ROW_STATUS: dict[str, str] = {
    "1": "active", "2": "notInService", "3": "notReady",
    "4": "createAndGo", "5": "createAndWait", "6": "destroy",
}


def _decode_port_bitmap(bitmap_str: str) -> list[int]:
    """
    Decode a hexadecimal port bitmap (OCTET STRING) into a list of port indexes.
    Port 1 is the MSB of byte 0.
    """
    ports: list[int] = []
    raw = str(bitmap_str or "").replace(" ", "").replace("0x", "").replace(":", "")
    if not raw:
        return ports
    try:
        for byte_idx, byte_hex in enumerate(
            [raw[i:i+2] for i in range(0, len(raw), 2)]
        ):
            byte_val = int(byte_hex, 16)
            for bit in range(8):
                if byte_val & (0x80 >> bit):
                    ports.append(byte_idx * 8 + bit + 1)
    except (ValueError, IndexError):
        pass
    return ports


class VLANCollector(BaseCollector):
    """
    Parses Q-BRIDGE-MIB static and current VLAN tables.
    Returns a list of VLAN records with port membership bitmaps decoded.
    """

    name = "vlan"

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

        vlans: dict[int, dict[str, Any]] = {}

        # ---------------------------------------------------------------
        # dot1qVlanStaticTable (authoritative source for names / status)
        # ---------------------------------------------------------------
        for k, v in raw_flat.items():
            sk = str(k)
            for prefix, col in (
                (_STATIC_NAME,   "name"),
                (_STATIC_EGRESS, "egress_raw"),
                (_STATIC_UNTAG,  "untag_raw"),
                (_STATIC_STATUS, "status_code"),
            ):
                if sk.startswith(prefix):
                    vid = sk[len(prefix):]
                    try:
                        vlan_id = int(vid)
                    except ValueError:
                        continue
                    vlans.setdefault(vlan_id, {"vlan_id": vlan_id})
                    vlans[vlan_id][col] = v

        # ---------------------------------------------------------------
        # dot1qVlanCurrentTable (has port membership even when static is absent)
        # Current table key is: <fdb_id>.<vlan_id>
        # ---------------------------------------------------------------
        for k, v in raw_flat.items():
            sk = str(k)
            for prefix, col in (
                (_CURRENT_EGRESS, "egress_raw"),
                (_CURRENT_UNTAG,  "untag_raw"),
                (_CURRENT_STATUS, "current_status_code"),
            ):
                if sk.startswith(prefix):
                    suffix = sk[len(prefix):]
                    parts = suffix.split(".")
                    if len(parts) == 2:
                        try:
                            vlan_id = int(parts[1])
                        except ValueError:
                            continue
                        vlans.setdefault(vlan_id, {"vlan_id": vlan_id})
                        if col not in vlans[vlan_id]:   # Static takes precedence
                            vlans[vlan_id][col] = v

        if not vlans:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "Q-BRIDGE-MIB (1.3.6.1.2.1.17.7.1.4) returned no VLAN data — "
                    "device may not support VLANs or 802.1Q"
                ),
                missing=["dot1qVlanStaticName", "dot1qVlanStaticRowStatus"],
            )

        # ---------------------------------------------------------------
        # Build output records
        # ---------------------------------------------------------------
        result: list[dict[str, Any]] = []
        for vlan_id in sorted(vlans.keys()):
            row = vlans[vlan_id]
            name        = self.text(row.get("name")) or f"VLAN{vlan_id}"
            status_code = str(row.get("status_code") or row.get("current_status_code") or "1")
            status      = _ROW_STATUS.get(status_code, "unknown")

            egress  = _decode_port_bitmap(str(row.get("egress_raw", "")))
            untagged = _decode_port_bitmap(str(row.get("untag_raw", "")))
            tagged  = [p for p in egress if p not in untagged]

            result.append({
                "vlan_id":       vlan_id,
                "name":          name,
                "status":        status,
                "egress_ports":  egress,
                "untagged_ports": untagged,
                "tagged_ports":  tagged,
                "port_count":    len(egress),
            })

        # Skip management VLAN 1 warning
        if not any(v["vlan_id"] == 1 for v in result):
            self.warn(warnings, "VLAN 1 not found in Q-BRIDGE table")

        return CollectorResponse.ok(
            self.name,
            {"vlans": result, "vlan_count": len(result)},
            missing,
            warnings,
        )
