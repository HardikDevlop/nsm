"""
CapabilityDiscoveryService — determines what each device actually supports.

Strategy
--------
For each capability domain, probe the raw SNMP walk result:
  - Does the walk contain any OIDs in this domain's tree?
  - Did the corresponding collector return supported=True?

This is purely evidence-based — no vendor name, no if/elif chains.
A Cisco router and a Linux server with the same MIB support get the
same capability flags.

Returns
-------
A dict mapping capability names to bool values, plus a detail dict
with per-collector evidence (missing OIDs, warnings, etc.)

Example:
    {
        "system":      True,
        "cpu":         True,
        "memory":      True,
        "interfaces":  True,
        "firewall":    False,
        "wireless":    False,
        ...
    }
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# OID prefixes that indicate a capability is present in the walk.
# Having ANY key under this prefix = collector has data to work with.
_CAPABILITY_OID_PROBES: dict[str, list[str]] = {
    "system":       ["1.3.6.1.2.1.1.1"],       # sysDescr
    "cpu":          ["1.3.6.1.2.1.25.3.3.1.2",  # hrProcessorLoad
                     "1.3.6.1.4.1.2021.11.11"], # ucdCpuIdle
    "memory":       ["1.3.6.1.2.1.25.2.3.1",    # hrStorageTable
                     "1.3.6.1.4.1.2021.4.5"],   # ucdMemTotalReal
    "storage":      ["1.3.6.1.2.1.25.2.3.1.2"], # hrStorageType
    "interfaces":   ["1.3.6.1.2.1.2.2.1.2"],    # ifDescr
    "environment":  ["1.3.6.1.2.1.99.1.1.1.4",  # entPhySensorValue
                     "1.3.6.1.4.1.9.9.13.1.3"], # cisco temp
    "inventory":    ["1.3.6.1.2.1.47.1.1.1.1.5"], # entPhysicalClass
    "vlan":         ["1.3.6.1.2.1.17.7.1.4.3.1", # dot1qVlanStaticName
                     "1.3.6.1.2.1.17.7.1.4.2.1"], # dot1qCurrentEgress
    "lldp":         ["1.0.8802.1.1.2.1.4.1.1.9"], # lldpRemSysName
    "cdp":          ["1.3.6.1.4.1.9.9.23.1.2.1.1.6"], # cdpCacheDeviceId
    "routing":      ["1.3.6.1.2.1.4.21.1.1"],    # ipForwardDest
    "arp":          ["1.3.6.1.2.1.4.22.1.2"],    # ipNetToMediaPhysAddress
    "mac_table":    ["1.3.6.1.2.1.17.4.3.1.2",   # dot1dTpFdbPort
                     "1.3.6.1.2.1.17.7.1.2.2.1.2"], # dot1qTpFdbPort
    "wireless":     ["1.3.6.1.4.1.14988.1.1.1.3", # mikrotik ssid
                     "1.3.6.1.4.1.9.9.512.1.1.1", # cisco ssid
                     "1.3.6.1.4.1.14823.2.2.1.1.7"], # aruba ssid
    "firewall":     ["1.3.6.1.4.1.12356.101.4.1.8", # fortinet sessions
                     "1.3.6.1.4.1.25461.2.1.2.4.3", # paloalto sessions
                     "1.3.6.1.4.1.2604.5.1.5.1",    # sophos conn
                     "1.3.6.1.4.1.9.9.147.1.2.2"],  # cisco asa
}

# Mapping from capability name to the bool column on DeviceCapabilities
_CAP_COLUMN: dict[str, str] = {
    "system":       "cap_system",
    "cpu":          "cap_cpu",
    "memory":       "cap_memory",
    "storage":      "cap_storage",
    "interfaces":   "cap_interfaces",
    "environment":  "cap_environment",
    "inventory":    "cap_inventory",
    "vlan":         "cap_vlan",
    "lldp":         "cap_lldp",
    "cdp":          "cap_cdp",
    "routing":      "cap_routing",
    "arp":          "cap_arp",
    "mac_table":    "cap_mac_table",
    "firewall":     "cap_firewall",
    "vpn":          "cap_vpn",
    "sdwan":        "cap_sdwan",
    "wireless":     "cap_wireless",
    "access_point": "cap_access_point",
    "topology":     "cap_topology",
}


class CapabilityDiscoveryService:
    """
    Discovers which capabilities a device supports by probing the walk.

    No vendor name is used in this class. A capability is 'supported'
    when the walk contains at least one OID in that capability's probe list.
    """

    def discover(
        self,
        walk: dict[str, Any],
        collector_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Return capability map + detail.

        Parameters
        ----------
        walk               : raw OID→value dict from SNMP walk
        collector_results  : optional dict of collector name → CollectorResponse dict

        Returns
        -------
        {
            "capabilities": {"system": True, "cpu": True, ...},
            "detail": {"cpu": {"supported": True, "missing": [], ...}, ...}
        }
        """
        capabilities: dict[str, bool] = {}
        detail: dict[str, Any] = {}

        walk_keys = set(walk.keys())

        for cap, oid_prefixes in _CAPABILITY_OID_PROBES.items():
            # Check OID probe first
            oid_supported = self._probe_walk(walk_keys, oid_prefixes)

            # Check collector result if available
            col_supported = None
            if collector_results and cap in collector_results:
                col_result = collector_results[cap]
                if isinstance(col_result, dict):
                    col_supported = col_result.get("supported", None)

            # Merge: walk probe OR collector result
            if col_supported is not None:
                final = bool(col_supported)
            else:
                final = oid_supported

            capabilities[cap] = final
            detail[cap] = {
                "supported": final,
                "oid_probe": oid_supported,
                "collector": col_supported,
            }
            if collector_results and cap in collector_results:
                col = collector_results[cap]
                if isinstance(col, dict):
                    detail[cap]["missing"]  = col.get("missing", [])
                    detail[cap]["warnings"] = col.get("warnings", [])
                    detail[cap]["reason"]   = col.get("reason")

        # Topology: true if any L2/L3 source has data
        capabilities["topology"] = any(
            capabilities.get(c) for c in ("lldp", "cdp", "arp", "mac_table", "routing")
        )

        return {"capabilities": capabilities, "detail": detail}

    def to_db_kwargs(self, capabilities: dict[str, bool]) -> dict[str, bool]:
        """Convert capability map to DeviceCapabilities column kwargs."""
        return {
            col: capabilities.get(cap, False)
            for cap, col in _CAP_COLUMN.items()
        }

    @staticmethod
    def _probe_walk(walk_keys: set[str], oid_prefixes: list[str]) -> bool:
        """Return True if any walk key starts with any of the given OID prefixes."""
        for prefix in oid_prefixes:
            prefix_dot = prefix.rstrip(".") + "."
            for k in walk_keys:
                if k.startswith(prefix_dot) or k == prefix:
                    return True
        return False
