"""
ARP Collector — IP-MIB ipNetToMediaTable (RFC 4293).

OID roots used
--------------
  ipNetToMediaTable        1.3.6.1.2.1.4.22.1
    .1  ipNetToMediaIfIndex   (output ifIndex)
    .2  ipNetToMediaPhysAddress (MAC address)
    .3  ipNetToMediaNetAddress  (IP address)
    .4  ipNetToMediaType        (1=other, 2=invalid, 3=dynamic, 4=static)

Row index: <if_index>.<ip_address>

Returned fields per ARP entry
------------------------------
  ip_address   str
  mac          str | None   (XX:XX:XX:XX:XX:XX)
  interface    int | None   (ifIndex)
  entry_type   str          — "dynamic" | "static" | "other" | "invalid"
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

_ARP_IF    = "1.3.6.1.2.1.4.22.1.1."
_ARP_MAC   = "1.3.6.1.2.1.4.22.1.2."
_ARP_IP    = "1.3.6.1.2.1.4.22.1.3."
_ARP_TYPE  = "1.3.6.1.2.1.4.22.1.4."

# ipNetToPhysicalTable (RFC 4293), used by newer Linux-based devices.
_PHYS_MAC  = "1.3.6.1.2.1.4.35.1.4."
_PHYS_TYPE = "1.3.6.1.2.1.4.35.1.6."

_ARP_TYPE_MAP: dict[str, str] = {
    "1": "other", "2": "invalid", "3": "dynamic", "4": "static",
}


class ARPCollector(BaseCollector):
    """
    Parses ipNetToMediaTable to expose the ARP cache.
    """

    name = "arp"

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
        # Row index: <if_index>.<ip_address>
        # Anchor on ipNetToMediaPhysAddress (column .2) since MAC is the
        # most useful field and always present in valid entries.
        # ---------------------------------------------------------------
        entries: list[dict[str, Any]] = []
        seen_ips: set[str] = set()

        for k, v in raw_flat.items():
            sk = str(k)
            if not sk.startswith(_ARP_MAC):
                continue
            # suffix: <if_index>.<a>.<b>.<c>.<d>
            suffix = sk[len(_ARP_MAC):]
            parts  = suffix.split(".", 1)
            if len(parts) < 2:
                continue
            if_index_str = parts[0]
            ip_suffix    = parts[1]

            # Validate IP suffix
            ip_parts = ip_suffix.split(".")
            if len(ip_parts) != 4:
                continue
            try:
                ip_addr = ".".join(str(int(p)) for p in ip_parts)
            except ValueError:
                continue

            if ip_addr in seen_ips:
                continue
            seen_ips.add(ip_addr)

            mac_val    = self.mac(v)
            if_index   = self.num(raw_flat.get(_ARP_IF  + suffix))
            type_code  = str(raw_flat.get(_ARP_TYPE + suffix, "3")).strip()
            entry_type = _ARP_TYPE_MAP.get(type_code, "unknown")

            # Skip invalid/placeholder entries
            if entry_type == "invalid":
                continue
            if mac_val in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
                continue

            entries.append({
                "ip_address":   ip_addr,
                "mac":          mac_val,
                "interface":    int(if_index) if if_index is not None else (
                                int(if_index_str) if if_index_str.isdigit() else None),
                "entry_type":   entry_type,
            })

        # Fallback for agents that no longer expose ipNetToMediaTable.
        # IPv4 row index: ifIndex.addressType.addressLength.octets...
        if not entries:
            for k, v in raw_flat.items():
                sk = str(k)
                if not sk.startswith(_PHYS_MAC):
                    continue
                suffix = sk[len(_PHYS_MAC):]
                parts = suffix.split(".")
                if len(parts) < 7 or parts[1] != "1" or parts[2] != "4":
                    continue
                octets = parts[3:7]
                if not all(p.isdigit() and 0 <= int(p) <= 255 for p in octets):
                    continue
                ip_addr = ".".join(octets)
                mac_val = self.mac(v)
                if mac_val in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
                    continue
                type_code = str(raw_flat.get(_PHYS_TYPE + suffix, "3")).strip()
                if type_code == "2":
                    continue
                entries.append({
                    "ip_address": ip_addr,
                    "mac": mac_val,
                    "interface": int(parts[0]) if parts[0].isdigit() else None,
                    "entry_type": _ARP_TYPE_MAP.get(type_code, "unknown"),
                })

        if not entries:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "ARP table (1.3.6.1.2.1.4.22.1) returned no data — "
                    "No ARP entries found in ipNetToMediaTable or ipNetToPhysicalTable"
                ),
                missing=["ipNetToMediaPhysAddress", "ipNetToPhysicalPhysAddress"],
            )

        entries.sort(key=lambda e: tuple(int(o) for o in e["ip_address"].split(".")))

        return CollectorResponse.ok(
            self.name,
            {"entries": entries, "entry_count": len(entries)},
            missing,
            warnings,
        )
