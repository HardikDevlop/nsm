"""
Interface Collector — full IF-MIB + ifXTable (64-bit counters).

MIBs used
---------
  IF-MIB (RFC 2863)    1.3.6.1.2.1.2.2.1.*
  ifXTable (RFC 2863)  1.3.6.1.2.1.31.1.1.1.*

IF-MIB columns parsed
---------------------
  .1   ifIndex                .2   ifDescr
  .3   ifType                 .4   ifMtu
  .5   ifSpeed                .6   ifPhysAddress
  .7   ifAdminStatus          .8   ifOperStatus
  .9   ifLastChange
  .10  ifInOctets             .11  ifInUcastPkts
  .12  ifInNUcastPkts         .13  ifInDiscards
  .14  ifInErrors             .16  ifOutOctets
  .17  ifOutUcastPkts         .18  ifOutNUcastPkts
  .19  ifOutDiscards          .20  ifOutErrors

ifXTable columns parsed
-----------------------
  .1   ifName                 .2   ifInMulticastPkts
  .3   ifInBroadcastPkts      .4   ifOutMulticastPkts
  .5   ifOutBroadcastPkts     .6   ifHCInOctets
  .7   ifHCInUcastPkts        .8   ifHCInMulticastPkts
  .9   ifHCInBroadcastPkts    .10  ifHCOutOctets
  .11  ifHCOutUcastPkts       .12  ifHCOutMulticastPkts
  .13  ifHCOutBroadcastPkts   .15  ifHighSpeed
  .18  ifAlias

Returned fields per interface
-------------------------------
  ifIndex, name, description, alias, mac, type,
  mtu, speed_bps, speed_label,
  admin_status, oper_status, last_change,
  in_octets, out_octets,
  in_ucast_pkts, out_ucast_pkts,
  in_multicast_pkts, out_multicast_pkts,
  in_broadcast_pkts, out_broadcast_pkts,
  in_discards, out_discards,
  in_errors, out_errors,
  in_unknown_pkts,
  utilization_percent,    (requires speed_bps > 0)
  duplex                  (vendor-extended, None when not available)
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# ---------------------------------------------------------------------------
# IF-MIB table roots
# ---------------------------------------------------------------------------
_IF_ROOT    = "1.3.6.1.2.1.2.2.1."
_IFX_ROOT   = "1.3.6.1.2.1.31.1.1.1."

# IF-MIB column → field name
_IF_COLS: dict[str, str] = {
    "1":  "ifIndex",
    "2":  "if_descr",
    "3":  "if_type",
    "4":  "mtu",
    "5":  "speed_bps",
    "6":  "mac_raw",
    "7":  "admin_status_raw",
    "8":  "oper_status_raw",
    "9":  "last_change",
    "10": "in_octets",
    "11": "in_ucast_pkts",
    "12": "in_ncast_pkts",
    "13": "in_discards",
    "14": "in_errors",
    "15": "in_unknown_pkts",
    "16": "out_octets",
    "17": "out_ucast_pkts",
    "18": "out_ncast_pkts",
    "19": "out_discards",
    "20": "out_errors",
}

# ifXTable column → field name
_IFX_COLS: dict[str, str] = {
    "1":  "name",
    "2":  "in_multicast_pkts",
    "3":  "in_broadcast_pkts",
    "4":  "out_multicast_pkts",
    "5":  "out_broadcast_pkts",
    "6":  "hc_in_octets",
    "7":  "hc_in_ucast_pkts",
    "8":  "hc_in_multicast_pkts",
    "9":  "hc_in_broadcast_pkts",
    "10": "hc_out_octets",
    "11": "hc_out_ucast_pkts",
    "12": "hc_out_multicast_pkts",
    "13": "hc_out_broadcast_pkts",
    "15": "high_speed_mbps",
    "17": "connector_present",
    "18": "alias",
}

# Status code → label
_ADMIN_STATUS: dict[str, str] = {"1": "up", "2": "down", "3": "testing"}
_OPER_STATUS:  dict[str, str] = {
    "1": "up", "2": "down", "3": "testing",
    "4": "unknown", "5": "dormant", "6": "notPresent", "7": "lowerLayerDown",
}

# ifType numeric → human label (subset of IANAifType)
_IF_TYPE: dict[str, str] = {
    "6":   "ethernetCsmacd",
    "24":  "softwareLoopback",
    "53":  "propVirtual",
    "131": "tunnel",
    "161": "ieee8023adLag",
    "166": "mpls",
}


def _speed_label(bps: int | None, high_mbps: int | None) -> str:
    """Convert speed to human-readable string, preferring ifHighSpeed."""
    mbps: float | None = None
    if high_mbps and int(high_mbps) > 0:
        mbps = float(high_mbps)
    elif bps and int(bps) > 0:
        mbps = float(bps) / 1_000_000
    if mbps is None:
        return "unknown"
    if mbps >= 1000:
        return f"{mbps / 1000:g} Gbps"
    return f"{mbps:g} Mbps"


def _utilization(
    in_oct: int | None,
    out_oct: int | None,
    speed_bps: int | None,
) -> float | None:
    """
    Instantaneous bandwidth utilization cannot be computed from a single sample
    (requires delta over time).  We return None here; the polling engine
    computes deltas using interface_rates() in polling.py.
    """
    return None


class InterfaceCollector(BaseCollector):
    """
    Parses IF-MIB and ifXTable into structured interface records.
    Uses 64-bit HCOctet counters when available, falls back to 32-bit.
    """

    name = "interfaces"

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
        # Parse IF-MIB table into {index: {field: value}}
        # ---------------------------------------------------------------
        rows: dict[str, dict[str, Any]] = {}
        for k, v in raw_flat.items():
            sk = str(k)
            if sk.startswith(_IF_ROOT):
                rest = sk[len(_IF_ROOT):]
                parts = rest.split(".", 1)
                if len(parts) == 2:
                    col, idx = parts
                    field = _IF_COLS.get(col)
                    if field:
                        rows.setdefault(idx, {})[field] = v

        if not rows:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "IF-MIB table (1.3.6.1.2.1.2.2.1) returned no data — "
                    "SNMP agent may not support ifTable"
                ),
                missing=["ifDescr", "ifOperStatus"],
            )

        # ---------------------------------------------------------------
        # Merge ifXTable (64-bit counters + name + alias)
        # ---------------------------------------------------------------
        for k, v in raw_flat.items():
            sk = str(k)
            if sk.startswith(_IFX_ROOT):
                rest = sk[len(_IFX_ROOT):]
                parts = rest.split(".", 1)
                if len(parts) == 2:
                    col, idx = parts
                    field = _IFX_COLS.get(col)
                    if field and idx in rows:
                        rows[idx][field] = v

        # ---------------------------------------------------------------
        # Build result list
        # ---------------------------------------------------------------
        interfaces: list[dict[str, Any]] = []

        for idx in sorted(rows.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            row = rows[idx]

            # Index
            if_index = self.num(row.get("ifIndex", idx))

            # Names
            name    = self.text(row.get("name"))
            descr   = self.text(row.get("if_descr"))
            alias   = self.text(row.get("alias"))

            # MAC
            mac_val = self.mac(row.get("mac_raw"))

            # Speed — prefer ifHighSpeed (Mbps) over ifSpeed (bps)
            speed_bps:  int | None = None
            high_mbps:  int | None = None
            s_raw = self.num(row.get("speed_bps"))
            h_raw = self.num(row.get("high_speed_mbps"))
            if s_raw and int(s_raw) > 0:
                speed_bps = int(s_raw)
            if h_raw and int(h_raw) > 0:
                high_mbps = int(h_raw)
                # Derive speed_bps from ifHighSpeed if raw ifSpeed is 0/absent
                if not speed_bps:
                    speed_bps = high_mbps * 1_000_000

            # Status
            admin = _ADMIN_STATUS.get(str(row.get("admin_status_raw", "")), "unknown")
            oper  = _OPER_STATUS.get(str(row.get("oper_status_raw", "")), "unknown")

            # If-type
            if_type_raw = str(row.get("if_type", ""))
            if_type = _IF_TYPE.get(if_type_raw, if_type_raw or "unknown")

            # Counters — prefer 64-bit HCOctets
            in_oct  = self.num(row.get("hc_in_octets") or row.get("in_octets"))
            out_oct = self.num(row.get("hc_out_octets") or row.get("out_octets"))
            in_oct_32  = self.num(row.get("in_octets"))
            out_oct_32 = self.num(row.get("out_octets"))

            in_ucast  = self.num(row.get("hc_in_ucast_pkts") or row.get("in_ucast_pkts"))
            out_ucast = self.num(row.get("hc_out_ucast_pkts") or row.get("out_ucast_pkts"))
            in_mcast  = self.num(row.get("hc_in_multicast_pkts") or row.get("in_multicast_pkts"))
            out_mcast = self.num(row.get("hc_out_multicast_pkts") or row.get("out_multicast_pkts"))
            in_bcast  = self.num(row.get("hc_in_broadcast_pkts") or row.get("in_broadcast_pkts"))
            out_bcast = self.num(row.get("hc_out_broadcast_pkts") or row.get("out_broadcast_pkts"))

            in_disc  = self.num(row.get("in_discards"))
            out_disc = self.num(row.get("out_discards"))
            in_err   = self.num(row.get("in_errors"))
            out_err  = self.num(row.get("out_errors"))
            in_unk   = self.num(row.get("in_unknown_pkts"))

            # Warn on high error rates
            total_err = (in_err or 0) + (out_err or 0)
            total_pkt = (in_ucast or 0) + (out_ucast or 0)
            if total_pkt > 0 and total_err / total_pkt > 0.01:
                self.warn(warnings, f"Interface {name or idx}: error rate >1%")

            interfaces.append({
                "ifIndex":              int(if_index) if if_index is not None else int(idx) if idx.isdigit() else idx,
                "name":                 name or descr or f"IF-{idx}",
                "description":          descr,
                "alias":                alias,
                "mac":                  mac_val,
                "type":                 if_type,
                "mtu":                  self.num(row.get("mtu")),
                "speed_bps":            speed_bps,
                "speed_label":          _speed_label(speed_bps, high_mbps),
                "admin_status":         admin,
                "oper_status":          oper,
                "last_change":          self.text(row.get("last_change")),
                "in_octets":            in_oct,
                "out_octets":           out_oct,
                "in_octets_32":         in_oct_32,
                "out_octets_32":        out_oct_32,
                "in_ucast_pkts":        in_ucast,
                "out_ucast_pkts":       out_ucast,
                "in_multicast_pkts":    in_mcast,
                "out_multicast_pkts":   out_mcast,
                "in_broadcast_pkts":    in_bcast,
                "out_broadcast_pkts":   out_bcast,
                "in_discards":          in_disc,
                "out_discards":         out_disc,
                "in_errors":            in_err,
                "out_errors":           out_err,
                "in_unknown_pkts":      in_unk,
                "utilization_percent":  None,   # computed by polling engine (requires delta)
                "duplex":               None,   # requires vendor MIB (dot3StatsDuplexStatus)
            })

        if not interfaces:
            return CollectorResponse.unsupported(
                self.name,
                reason="IF-MIB table present but no parseable interface rows found",
                missing=["ifDescr"],
            )

        return CollectorResponse.ok(
            self.name,
            {
                "interfaces":      interfaces,
                "interface_count": len(interfaces),
                "up_count":        sum(1 for i in interfaces if i["oper_status"] == "up"),
                "down_count":      sum(1 for i in interfaces if i["oper_status"] == "down"),
            },
            missing,
            warnings,
        )
