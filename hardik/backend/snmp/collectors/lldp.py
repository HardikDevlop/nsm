"""
LLDP Collector — IEEE 802.1AB LLDP-MIB.

OID roots used
--------------
  lldpRemTable             1.0.8802.1.1.2.1.4.1.1
    .4  lldpRemChassisIdSubtype
    .5  lldpRemChassisId
    .6  lldpRemPortIdSubtype
    .7  lldpRemPortId
    .8  lldpRemPortDesc
    .9  lldpRemSysName
    .10 lldpRemSysDesc
    .11 lldpRemSysCapSupported
    .12 lldpRemSysCapEnabled

  lldpRemManAddrTable      1.0.8802.1.1.2.1.4.2.1
    .3  lldpRemManAddr

  lldpLocPortTable         1.0.8802.1.1.2.1.3.7.1
    .2  lldpLocPortId
    .3  lldpLocPortDesc

Row index: lldpRemTable.<time_mark>.<local_port_num>.<rem_index>

Returned fields per neighbor
-----------------------------
  local_port_num   int
  local_port_desc  str | None
  remote_chassis_id str
  remote_port_id   str
  remote_port_desc str | None
  remote_sys_name  str | None
  remote_sys_desc  str | None
  mgmt_address     str | None
  capabilities_supported list[str]
  capabilities_enabled   list[str]
  platform         str | None   (extracted from remote_sys_desc)
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# LLDP-MIB OID roots
_REM_ROOT   = "1.0.8802.1.1.2.1.4.1.1."
_MGMT_ROOT  = "1.0.8802.1.1.2.1.4.2.1."
_LOC_ROOT   = "1.0.8802.1.1.2.1.3.7.1."

# lldpRemTable column offsets (within _REM_ROOT)
_REM_COLS: dict[str, str] = {
    "4":  "chassis_id_subtype",
    "5":  "chassis_id",
    "6":  "port_id_subtype",
    "7":  "port_id",
    "8":  "port_desc",
    "9":  "sys_name",
    "10": "sys_desc",
    "11": "cap_supported",
    "12": "cap_enabled",
}

# LLDP capability bits (IEEE 802.1AB)
_CAP_BITS: list[str] = [
    "Other", "Repeater", "Bridge", "WLAN-AP", "Router",
    "Telephone", "DOCSIS-Cable-Device", "Station-Only",
]


def _decode_capabilities(bitmap_str: str) -> list[str]:
    """Decode a 2-byte LLDP capabilities bitmap into a list of names."""
    caps: list[str] = []
    raw = str(bitmap_str or "").replace(" ", "").replace("0x", "").replace(":", "")
    if not raw:
        return caps
    try:
        val = int(raw, 16)
        for bit_pos, name in enumerate(_CAP_BITS):
            if val & (0x8000 >> bit_pos):
                caps.append(name)
    except (ValueError, TypeError):
        pass
    return caps


def _extract_platform(sys_desc: str | None) -> str | None:
    """Try to extract a short platform label from sysDesc."""
    if not sys_desc:
        return None
    # Take first line / sentence
    first_line = sys_desc.split("\n")[0].split(";")[0].strip()
    return first_line[:120] if first_line else None


class LLDPCollector(BaseCollector):
    """
    Parses LLDP-MIB neighbor tables and local port descriptions.
    """

    name = "lldp"

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
        # Parse lldpLocPortTable for local port descriptions
        # ---------------------------------------------------------------
        local_ports: dict[str, str] = {}   # port_num → description
        for k, v in raw_flat.items():
            sk = str(k)
            if sk.startswith(_LOC_ROOT + "3."):    # lldpLocPortDesc
                port_num = sk[len(_LOC_ROOT) + 2:]
                desc = self.text(v)
                if desc:
                    local_ports[port_num] = desc

        # ---------------------------------------------------------------
        # Parse lldpRemTable
        # Row index format:  <col>.<time_mark>.<local_port_num>.<rem_index>
        # ---------------------------------------------------------------
        # Structure: {(time_mark, local_port_num, rem_index): {field: value}}
        rem_rows: dict[tuple[str, str, str], dict[str, Any]] = {}

        for k, v in raw_flat.items():
            sk = str(k)
            if not sk.startswith(_REM_ROOT):
                continue
            rest = sk[len(_REM_ROOT):]
            parts = rest.split(".", 3)
            if len(parts) < 4:
                continue
            col, time_mark, local_port, rem_idx = parts[0], parts[1], parts[2], parts[3]
            field = _REM_COLS.get(col)
            if not field:
                continue
            key = (time_mark, local_port, rem_idx)
            rem_rows.setdefault(key, {})[field] = v

        # ---------------------------------------------------------------
        # Parse lldpRemManAddrTable for management addresses
        # Index: <col>.<time_mark>.<local_port>.<rem_idx>.<addr_subtype>.<addr_len>.<addr>
        # ---------------------------------------------------------------
        mgmt_addrs: dict[tuple[str, str, str], str] = {}
        for k, v in raw_flat.items():
            sk = str(k)
            if not sk.startswith(_MGMT_ROOT + "3."):
                continue
            # Suffix after "3." is: time_mark.local_port.rem_idx.subtype.len.a.b.c.d
            suffix = sk[len(_MGMT_ROOT) + 2:]
            parts  = suffix.split(".")
            if len(parts) >= 3:
                key = (parts[0], parts[1], parts[2])
                # Management address is encoded as remaining parts
                # For IPv4: subtype=1, len=4, then 4 octets
                if len(parts) >= 8 and parts[3] == "1" and parts[4] == "4":
                    mgmt_addrs[key] = ".".join(parts[5:9])

        if not rem_rows:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "LLDP-MIB (1.0.8802.1.1.2.1.4.1.1) returned no neighbor data — "
                    "LLDP may be disabled or not supported"
                ),
                missing=["lldpRemSysName", "lldpRemPortId"],
            )

        # ---------------------------------------------------------------
        # Build result list
        # ---------------------------------------------------------------
        neighbors: list[dict[str, Any]] = []

        for (time_mark, local_port, rem_idx), row in sorted(rem_rows.items()):
            chassis_id = self.text(row.get("chassis_id"))
            port_id    = self.text(row.get("port_id"))
            port_desc  = self.text(row.get("port_desc"))
            sys_name   = self.text(row.get("sys_name"))
            sys_desc   = self.text(row.get("sys_desc"))
            cap_sup    = _decode_capabilities(str(row.get("cap_supported", "")))
            cap_en     = _decode_capabilities(str(row.get("cap_enabled", "")))
            mgmt_ip    = mgmt_addrs.get((time_mark, local_port, rem_idx))
            local_desc = local_ports.get(local_port)
            platform   = _extract_platform(sys_desc)

            if not chassis_id and not sys_name:
                continue    # Skip phantom entries

            neighbors.append({
                "local_port_num":             local_port,
                "local_port_desc":            local_desc,
                "remote_chassis_id":          chassis_id,
                "remote_port_id":             port_id,
                "remote_port_desc":           port_desc,
                "remote_sys_name":            sys_name,
                "remote_sys_desc":            sys_desc,
                "mgmt_address":               mgmt_ip,
                "capabilities_supported":     cap_sup,
                "capabilities_enabled":       cap_en,
                "platform":                   platform,
                "rem_index":                  rem_idx,
            })

        if not neighbors:
            return CollectorResponse.unsupported(
                self.name,
                reason="LLDP neighbor table present but no valid neighbor entries found",
                missing=["lldpRemSysName"],
            )

        return CollectorResponse.ok(
            self.name,
            {
                "neighbors":      neighbors,
                "neighbor_count": len(neighbors),
                "local_ports":    local_ports,
            },
            missing,
            warnings,
        )
