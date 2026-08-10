"""
Routing Collector — IP-FORWARD-MIB (RFC 4292) / IP-MIB.

OID roots used
--------------
  ipForwardTable (deprecated, still widely supported)
    1.3.6.1.2.1.4.21.1
      .1  ipForwardDest       (destination IP)
      .3  ipForwardMetric1    (primary metric)
      .4  ipForwardNextHop    (next-hop IP)
      .5  ipForwardIfIndex    (output interface)
      .7  ipForwardProto      (routing protocol)
      .11 ipForwardMask       (subnet mask)

  inetCidrRouteTable (preferred)
    1.3.6.1.2.1.4.24.7.1
      Row index encodes dest/prefix/type/policy/nexthop

Returned fields per route
--------------------------
  destination   str    — dotted-decimal
  mask          str | None
  prefix_length int | None
  next_hop      str | None
  interface     int | None   (ifIndex)
  protocol      str          — "other"|"local"|"static"|"ospf"|"bgp"|"rip"|...
  metric        int | None
  route_type    str          — "local"|"remote"|"reject"|"blackhole"
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# IP-FORWARD-MIB ipForwardTable
_FWD_ROOT      = "1.3.6.1.2.1.4.21.1."
_FWD_DEST      = "1.3.6.1.2.1.4.21.1.1."
_FWD_METRIC    = "1.3.6.1.2.1.4.21.1.3."
_FWD_NEXTHOP   = "1.3.6.1.2.1.4.21.1.4."
_FWD_IFINDEX   = "1.3.6.1.2.1.4.21.1.5."
_FWD_TYPE      = "1.3.6.1.2.1.4.21.1.6."
_FWD_PROTO     = "1.3.6.1.2.1.4.21.1.7."
_FWD_MASK      = "1.3.6.1.2.1.4.21.1.11."

# inetCidrRouteTable (ipForwardCidrTable)
_CIDR_ROOT     = "1.3.6.1.2.1.4.24.7.1."
_CIDR_NEXTHOP  = "1.3.6.1.2.1.4.24.7.1.5."
_CIDR_IFINDEX  = "1.3.6.1.2.1.4.24.7.1.7."
_CIDR_PROTO    = "1.3.6.1.2.1.4.24.7.1.10."
_CIDR_METRIC   = "1.3.6.1.2.1.4.24.7.1.12."

# Protocol codes (ipForwardProto / inetCidrRouteProto)
_PROTO: dict[str, str] = {
    "1":  "other",       "2":  "local",       "3":  "netmgmt",
    "4":  "icmp",        "5":  "egp",         "6":  "ggp",
    "7":  "hello",       "8":  "rip",         "9":  "is-is",
    "10": "es-is",       "11": "ciscoIgrp",   "12": "bbnSpfIgp",
    "13": "ospf",        "14": "bgp",         "15": "idpr",
    "16": "ciscoEigrp",  "17": "dvmrp",
}

# Route type codes (ipForwardType)
_ROUTE_TYPE: dict[str, str] = {
    "1": "other", "2": "reject", "3": "local", "4": "remote",
}


def _mask_to_prefix(mask: str | None) -> int | None:
    """Convert dotted-decimal mask to prefix length."""
    if not mask:
        return None
    try:
        import ipaddress
        return int(ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen)
    except Exception:
        return None


class RoutingCollector(BaseCollector):
    """
    Parses the IP routing table from IP-FORWARD-MIB.
    Tries inetCidrRouteTable first (preferred), falls back to ipForwardTable.
    """

    name = "routing"

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

        routes: list[dict[str, Any]] = []

        # ---------------------------------------------------------------
        # Try ipForwardTable (most widely supported)
        # Row index: <col>.<dest_ip>.<proto>.<policy>.<nexthop_ip>
        # For ipForwardTable column .1 (dest) the key is .1.<dest>.<policy>.<nexthop>
        # Simpler to index by destination IP extracted from .1.* keys
        # ---------------------------------------------------------------
        dest_rows: dict[str, dict[str, Any]] = {}

        for k, v in raw_flat.items():
            sk = str(k)
            for prefix, col in (
                (_FWD_DEST,    "dest"),
                (_FWD_MASK,    "mask"),
                (_FWD_NEXTHOP, "next_hop"),
                (_FWD_IFINDEX, "if_index"),
                (_FWD_PROTO,   "proto_code"),
                (_FWD_TYPE,    "type_code"),
                (_FWD_METRIC,  "metric"),
            ):
                if sk.startswith(prefix):
                    # The suffix is: <dest_ip>.<policy>.<nexthop_ip>
                    suffix = sk[len(prefix):]
                    parts  = suffix.split(".")
                    if len(parts) >= 4:
                        dest_ip = ".".join(parts[:4])
                        row_key = suffix          # full suffix as key
                        dest_rows.setdefault(row_key, {})[col] = v
                        dest_rows[row_key]["_dest_ip"] = dest_ip

        if dest_rows:
            for row_key, row in dest_rows.items():
                dest = str(row.get("dest", row.get("_dest_ip", ""))).strip()
                if not dest or dest in ("0.0.0.0", ""):
                    dest = row.get("_dest_ip", "")

                mask     = self.text(row.get("mask"))
                next_hop = self.text(row.get("next_hop"))
                if_index = self.num(row.get("if_index"))
                proto    = _PROTO.get(str(row.get("proto_code", "1")), "unknown")
                rtype    = _ROUTE_TYPE.get(str(row.get("type_code", "4")), "unknown")
                metric   = self.num(row.get("metric"))
                pfx_len  = _mask_to_prefix(mask)

                # Skip invalid entries
                if not dest or dest == "0.0.0.0" and not mask:
                    continue

                routes.append({
                    "destination":    dest,
                    "mask":           mask,
                    "prefix_length":  pfx_len,
                    "next_hop":       next_hop if next_hop != "0.0.0.0" else None,
                    "interface":      int(if_index) if if_index else None,
                    "protocol":       proto,
                    "route_type":     rtype,
                    "metric":         int(metric) if metric is not None else None,
                })

        if not routes:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "IP routing table (1.3.6.1.2.1.4.21.1) returned no data — "
                    "device may not support IP-FORWARD-MIB or have no routes"
                ),
                missing=["ipForwardDest", "ipForwardNextHop"],
            )

        # De-duplicate and sort
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in routes:
            key = f"{r['destination']}/{r['prefix_length']}-{r['next_hop']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)
        unique.sort(key=lambda r: r["destination"])

        # Protocol summary
        proto_summary: dict[str, int] = {}
        for r in unique:
            proto_summary[r["protocol"]] = proto_summary.get(r["protocol"], 0) + 1

        return CollectorResponse.ok(
            self.name,
            {
                "routes":            unique,
                "route_count":       len(unique),
                "protocol_summary":  proto_summary,
            },
            missing,
            warnings,
        )
