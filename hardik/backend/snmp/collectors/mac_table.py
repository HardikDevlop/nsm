"""
MAC Address Table Collector — BRIDGE-MIB (RFC 4188).

OID roots used
--------------
  dot1dTpFdbTable          1.3.6.1.2.1.17.4.3.1
    .1  dot1dTpFdbAddress   (MAC address — encoded in OID suffix)
    .2  dot1dTpFdbPort      (bridge port number)
    .3  dot1dTpFdbStatus    (1=other, 2=invalid, 3=learned, 4=self, 5=mgmt)

  dot1dBasePortIfIndex     1.3.6.1.2.1.17.1.4.1.2.<port>
    Maps bridge port numbers to ifIndex values.

  dot1qTpFdbTable (Q-BRIDGE-MIB, VLAN-aware)
    1.3.6.1.2.1.17.7.1.2.2.1
      .2  dot1qTpFdbPort    — keyed by <vlan_id>.<mac_6_bytes>
      .3  dot1qTpFdbStatus

Row index for dot1dTpFdb: <6 MAC octets as decimal>
Row index for dot1qTpFdb: <vlan_id>.<6 MAC octets as decimal>

Returned fields per entry
--------------------------
  mac          str    (XX:XX:XX:XX:XX:XX)
  port         int | None   (bridge port number)
  if_index     int | None   (mapped via dot1dBasePortIfIndex)
  vlan_id      int | None   (from dot1qTpFdb, None for 802.1D)
  status       str   — "learned" | "self" | "mgmt" | "other"
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# BRIDGE-MIB
_FDB_PORT   = "1.3.6.1.2.1.17.4.3.1.2."   # dot1dTpFdbPort
_FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3."   # dot1dTpFdbStatus
_PORT_IFIX  = "1.3.6.1.2.1.17.1.4.1.2."   # dot1dBasePortIfIndex

# Q-BRIDGE-MIB dot1qTpFdbTable
_Q_FDB_PORT   = "1.3.6.1.2.1.17.7.1.2.2.1.2."  # dot1qTpFdbPort (vlan.mac)
_Q_FDB_STATUS = "1.3.6.1.2.1.17.7.1.2.2.1.3."  # dot1qTpFdbStatus

_FDB_STATUS_MAP: dict[str, str] = {
    "1": "other", "2": "invalid", "3": "learned", "4": "self", "5": "mgmt",
}


def _mac_from_oid_suffix(suffix: str) -> str | None:
    """
    Convert an OID MAC suffix (6 decimal octets) to XX:XX:XX:XX:XX:XX.
    e.g. "0.80.195.12.43.100" → "00:50:C3:0C:2B:64"
    """
    parts = suffix.split(".")
    if len(parts) < 6:
        return None
    try:
        octets = [int(p) for p in parts[-6:]]
        if all(0 <= o <= 255 for o in octets):
            return ":".join(f"{o:02X}" for o in octets)
    except (ValueError, TypeError):
        pass
    return None


class MACTableCollector(BaseCollector):
    """
    Collects the Layer-2 forwarding table.
    Tries Q-BRIDGE-MIB (VLAN-aware) first, falls back to BRIDGE-MIB.
    """

    name = "mac_table"

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
        # Build bridge port → ifIndex mapping
        # ---------------------------------------------------------------
        port_to_ifindex: dict[int, int] = {}
        for k, v in raw_flat.items():
            sk = str(k)
            if sk.startswith(_PORT_IFIX):
                port_str = sk[len(_PORT_IFIX):]
                try:
                    port = int(port_str)
                    if_idx = self.num(v)
                    if if_idx is not None:
                        port_to_ifindex[port] = int(if_idx)
                except (ValueError, TypeError):
                    pass

        entries: list[dict[str, Any]] = []
        seen_macs: set[str] = set()

        # ---------------------------------------------------------------
        # 1. Q-BRIDGE dot1qTpFdbTable (VLAN-aware — preferred)
        # Row index: <vlan_id>.<mac_6_octets>
        # ---------------------------------------------------------------
        q_vlan_mac: dict[str, dict[str, Any]] = {}
        for k, v in raw_flat.items():
            sk = str(k)
            if not sk.startswith(_Q_FDB_PORT):
                continue
            suffix = sk[len(_Q_FDB_PORT):]
            parts  = suffix.split(".", 1)
            if len(parts) < 2:
                continue
            try:
                vlan_id  = int(parts[0])
                mac_sfx  = parts[1]
                mac_str  = _mac_from_oid_suffix(mac_sfx)
                if not mac_str:
                    continue
                port_num = self.num(v)
                status_code = str(
                    raw_flat.get(_Q_FDB_STATUS + suffix, "3")
                ).strip()
                status = _FDB_STATUS_MAP.get(status_code, "learned")
                if status == "invalid":
                    continue

                key = f"{mac_str}:{vlan_id}"
                if key in seen_macs:
                    continue
                seen_macs.add(key)

                port_int = int(port_num) if port_num is not None else None
                entries.append({
                    "mac":      mac_str,
                    "port":     port_int,
                    "if_index": port_to_ifindex.get(port_int) if port_int else None,
                    "vlan_id":  vlan_id,
                    "status":   status,
                })
            except (ValueError, TypeError):
                continue

        # ---------------------------------------------------------------
        # 2. BRIDGE-MIB dot1dTpFdbTable (fallback, no VLAN info)
        # Row index: <mac_6_octets>
        # ---------------------------------------------------------------
        if not entries:
            for k, v in raw_flat.items():
                sk = str(k)
                if not sk.startswith(_FDB_PORT):
                    continue
                mac_sfx = sk[len(_FDB_PORT):]
                mac_str = _mac_from_oid_suffix(mac_sfx)
                if not mac_str:
                    continue
                port_num    = self.num(v)
                status_code = str(raw_flat.get(_FDB_STATUS + mac_sfx, "3")).strip()
                status = _FDB_STATUS_MAP.get(status_code, "learned")
                if status == "invalid":
                    continue
                if mac_str in seen_macs:
                    continue
                seen_macs.add(mac_str)

                port_int = int(port_num) if port_num is not None else None
                entries.append({
                    "mac":      mac_str,
                    "port":     port_int,
                    "if_index": port_to_ifindex.get(port_int) if port_int else None,
                    "vlan_id":  None,
                    "status":   status,
                })

        if not entries:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "MAC address table (1.3.6.1.2.1.17.4.3.1 / 1.3.6.1.2.1.17.7.1.2.2.1) "
                    "returned no data — device may not support BRIDGE-MIB"
                ),
                missing=["dot1dTpFdbPort", "dot1qTpFdbPort"],
            )

        # Sort by VLAN then MAC
        entries.sort(key=lambda e: (e.get("vlan_id") or 0, e["mac"]))

        # Build a port-centric view. LLDP presence is the strongest signal
        # that a port is an uplink/trunk; otherwise one learned MAC is an
        # endpoint hint and ambiguous/multi-MAC ports remain UNKNOWN.
        lldp_ports: set[str] = set()
        lldp_prefix = "1.0.8802.1.1.2.1.4.1.1."
        for oid in raw_flat:
            sk = str(oid)
            if sk.startswith(lldp_prefix):
                suffix = sk[len(lldp_prefix):].split(".")
                if len(suffix) >= 3:
                    # column.timeMark.localPort.remoteIndex
                    lldp_ports.add(suffix[2])

        groups: dict[str, dict[str, Any]] = {}
        for entry in entries:
            port_key = str(entry.get("if_index") or entry.get("port") or "unknown")
            group = groups.setdefault(port_key, {
                "port": entry.get("port"), "if_index": entry.get("if_index"),
                "mac_count": 0, "macs": [], "ip_addresses": [], "vlans": [],
            })
            group["mac_count"] += 1
            group["macs"].append(entry["mac"])
            # Some devices expose an IP alongside the forwarding entry.
            # Keep it available for the UI; the API can also enrich this
            # from the ARP collector when the switch does not.
            ip_address = entry.get("ip_address") or entry.get("ip")
            if ip_address and ip_address not in group["ip_addresses"]:
                group["ip_addresses"].append(ip_address)
            if entry.get("vlan_id") is not None and entry["vlan_id"] not in group["vlans"]:
                group["vlans"].append(entry["vlan_id"])
        for key, group in groups.items():
            if key in lldp_ports or str(group.get("port")) in lldp_ports:
                group["classification"] = "UPLINK/TRUNK"
            elif group["mac_count"] == 1:
                group["classification"] = "ENDPOINT"
            else:
                group["classification"] = "UNKNOWN"

        return CollectorResponse.ok(
            self.name,
            {
                "entries":      entries,
                "entry_count":  len(entries),
                "vlan_aware":   any(e["vlan_id"] is not None for e in entries),
                "port_groups":  list(groups.values()),
            },
            missing,
            warnings,
        )
