"""
Topology Collector — multi-source Layer-2/3 topology builder.

Data sources (in priority order)
----------------------------------
  1. LLDP-MIB     — most reliable, vendor-neutral
  2. CDP           — Cisco-only fallback
  3. ARP table     — Layer-3 adjacency
  4. MAC table     — Layer-2 adjacency (when LLDP/CDP absent)
  5. Routing table — gateway/next-hop links

Returned graph model
---------------------
  nodes     list[Node]    — unique devices discovered
  links     list[Link]    — connections between nodes
  source    str           — "lldp" | "cdp" | "arp" | "mac_table" | "routing" | "mixed"

Node shape
----------
  {
    "id":           str,    (IP or chassis ID — unique per graph)
    "hostname":     str | None,
    "ip":           str | None,
    "mac":          str | None,
    "vendor":       str | None,
    "device_type":  str | None,
    "interfaces":   list[str],
  }

Link shape
----------
  {
    "source_node":    str,   (Node.id)
    "target_node":    str,
    "source_port":    str | None,
    "target_port":    str | None,
    "protocol":       str,   "lldp" | "cdp" | "arp" | "mac_table" | "routing"
    "bidirectional":  bool,
  }
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# Sentinel for "this device" in the graph
_LOCAL_NODE_ID = "__local__"


class TopologyCollector(BaseCollector):
    """
    Aggregates LLDP, CDP, ARP, MAC table and routing data
    into a portable graph model.
    """

    name = "topology"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        missing:  list[str] = []
        warnings: list[str] = []

        if isinstance(raw, RawDevice):
            device   = raw
            raw_flat = raw.raw
        else:
            from ..normalizer import NormalizationLayer  # noqa: PLC0415
            device   = NormalizationLayer().normalize(raw)
            raw_flat = raw

        nodes: dict[str, dict[str, Any]] = {}
        links: list[dict[str, Any]] = []
        sources_used: list[str] = []

        # Local node (this device)
        local_hostname = device.hostname or "local-device"
        local_id = device.sys_object_id or local_hostname
        nodes[local_id] = {
            "id":          local_id,
            "hostname":    local_hostname,
            "ip":          None,
            "mac":         None,
            "vendor":      device.vendor,
            "device_type": device.device_type,
            "interfaces":  [],
        }

        # ---------------------------------------------------------------
        # 1. LLDP neighbors
        # ---------------------------------------------------------------
        lldp_neighbors = self._extract_lldp(raw_flat)
        if lldp_neighbors:
            sources_used.append("lldp")
            for nb in lldp_neighbors:
                nb_id = nb.get("remote_chassis_id") or nb.get("remote_sys_name") or nb.get("mgmt_address", "")
                if not nb_id:
                    continue
                if nb_id not in nodes:
                    nodes[nb_id] = {
                        "id":         nb_id,
                        "hostname":   nb.get("remote_sys_name"),
                        "ip":         nb.get("mgmt_address"),
                        "mac":        nb.get("remote_chassis_id") if ":" in str(nb.get("remote_chassis_id", "")) else None,
                        "vendor":     None,
                        "device_type": None,
                        "interfaces": [nb.get("remote_port_id")] if nb.get("remote_port_id") else [],
                    }
                links.append({
                    "source_node":   local_id,
                    "target_node":   nb_id,
                    "source_port":   nb.get("local_port_desc") or nb.get("local_port_num"),
                    "target_port":   nb.get("remote_port_id") or nb.get("remote_port_desc"),
                    "protocol":      "lldp",
                    "bidirectional": True,
                })

        # ---------------------------------------------------------------
        # 2. CDP neighbors  (Cisco only)
        # ---------------------------------------------------------------
        cdp_neighbors = self._extract_cdp(raw_flat, device.vendor)
        if cdp_neighbors:
            sources_used.append("cdp")
            for nb in cdp_neighbors:
                nb_id = nb.get("device_id", "")
                if not nb_id:
                    continue
                if nb_id not in nodes:
                    nodes[nb_id] = {
                        "id":         nb_id,
                        "hostname":   nb.get("device_id"),
                        "ip":         nb.get("mgmt_address"),
                        "mac":        None,
                        "vendor":     "cisco",
                        "device_type": None,
                        "interfaces": [],
                    }
                links.append({
                    "source_node":   local_id,
                    "target_node":   nb_id,
                    "source_port":   nb.get("local_port_index"),
                    "target_port":   nb.get("remote_port"),
                    "protocol":      "cdp",
                    "bidirectional": True,
                })

        # ---------------------------------------------------------------
        # 3. ARP table — Layer-3 adjacency
        # ---------------------------------------------------------------
        arp_entries = self._extract_arp(raw_flat)
        if arp_entries and not lldp_neighbors and not cdp_neighbors:
            sources_used.append("arp")
            for entry in arp_entries:
                ip  = entry.get("ip_address", "")
                mac = entry.get("mac", "")
                if not ip:
                    continue
                nb_id = ip
                if nb_id not in nodes:
                    nodes[nb_id] = {
                        "id":         nb_id,
                        "hostname":   None,
                        "ip":         ip,
                        "mac":        mac,
                        "vendor":     None,
                        "device_type": None,
                        "interfaces": [],
                    }
                links.append({
                    "source_node":   local_id,
                    "target_node":   nb_id,
                    "source_port":   None,
                    "target_port":   None,
                    "protocol":      "arp",
                    "bidirectional": False,
                })

        # ---------------------------------------------------------------
        # 4. MAC table — L2 adjacency (only when nothing else found)
        # ---------------------------------------------------------------
        if not links:
            mac_entries = self._extract_mac(raw_flat)
            if mac_entries:
                sources_used.append("mac_table")
                for entry in mac_entries:
                    mac = entry.get("mac", "")
                    if not mac or entry.get("status") == "self":
                        continue
                    nb_id = mac
                    if nb_id not in nodes:
                        nodes[nb_id] = {
                            "id":         nb_id,
                            "hostname":   None,
                            "ip":         None,
                            "mac":        mac,
                            "vendor":     None,
                            "device_type": None,
                            "interfaces": [],
                        }
                    links.append({
                        "source_node":   local_id,
                        "target_node":   nb_id,
                        "source_port":   str(entry.get("if_index") or entry.get("port") or ""),
                        "target_port":   None,
                        "protocol":      "mac_table",
                        "bidirectional": False,
                    })

        # ---------------------------------------------------------------
        # 5. Routing next-hops
        # ---------------------------------------------------------------
        route_gws = self._extract_route_gws(raw_flat)
        if route_gws:
            if "routing" not in sources_used:
                sources_used.append("routing")
            for gw_ip in route_gws:
                if gw_ip not in nodes:
                    nodes[gw_ip] = {
                        "id":         gw_ip,
                        "hostname":   None,
                        "ip":         gw_ip,
                        "mac":        None,
                        "vendor":     None,
                        "device_type": "router",
                        "interfaces": [],
                    }
                    links.append({
                        "source_node":   local_id,
                        "target_node":   gw_ip,
                        "source_port":   None,
                        "target_port":   None,
                        "protocol":      "routing",
                        "bidirectional": False,
                    })

        if len(nodes) <= 1 and not links:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "No topology data found — LLDP, CDP, ARP and MAC table all empty. "
                    "Enable LLDP on the device for rich topology."
                ),
                missing=["lldpRemSysName", "cdpCacheDeviceId"],
            )

        # Deduplicate links
        seen_links: set[str] = set()
        unique_links: list[dict[str, Any]] = []
        for lnk in links:
            lkey = f"{lnk['source_node']}>>{lnk['target_node']}:{lnk['protocol']}"
            if lkey not in seen_links:
                seen_links.add(lkey)
                unique_links.append(lnk)

        source_label = "mixed" if len(sources_used) > 1 else (sources_used[0] if sources_used else "none")

        return CollectorResponse.ok(
            self.name,
            {
                "nodes":        list(nodes.values()),
                "links":        unique_links,
                "node_count":   len(nodes),
                "link_count":   len(unique_links),
                "source":       source_label,
                "sources_used": sources_used,
            },
            missing,
            warnings,
        )

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_lldp(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Quick-parse LLDP neighbor sysName from lldpRemTable."""
        _REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9."
        _REM_CHASSIS  = "1.0.8802.1.1.2.1.4.1.1.5."
        _REM_PORT_ID  = "1.0.8802.1.1.2.1.4.1.1.7."
        _REM_PORT_DSC = "1.0.8802.1.1.2.1.4.1.1.8."
        _LOC_PORT_DSC = "1.0.8802.1.1.2.1.3.7.1.3."
        _MGMT_ADDR    = "1.0.8802.1.1.2.1.4.2.1.3."

        rows: dict[str, dict[str, Any]] = {}
        for k, v in raw.items():
            sk = str(k)
            for prefix, col in (
                (_REM_SYS_NAME, "remote_sys_name"),
                (_REM_CHASSIS,  "remote_chassis_id"),
                (_REM_PORT_ID,  "remote_port_id"),
                (_REM_PORT_DSC, "remote_port_desc"),
            ):
                if sk.startswith(prefix):
                    suffix = sk[len(prefix):]
                    parts  = suffix.split(".", 2)
                    if len(parts) == 3:
                        key = (parts[0], parts[1], parts[2])
                        rows.setdefault(str(key), {})[col] = self.text(v)
                        rows[str(key)]["local_port_num"] = parts[1]

        # Local port descriptions
        loc_ports: dict[str, str] = {}
        for k, v in raw.items():
            if str(k).startswith(_LOC_PORT_DSC):
                pn = str(k)[len(_LOC_PORT_DSC):]
                loc_ports[pn] = self.text(v) or pn

        # Management addresses
        mgmt: dict[str, str] = {}
        for k, v in raw.items():
            sk = str(k)
            if sk.startswith(_MGMT_ADDR):
                suffix = sk[len(_MGMT_ADDR):]
                parts  = suffix.split(".")
                if len(parts) >= 3 and parts[3:7]:
                    key = str((parts[0], parts[1], parts[2]))
                    if len(parts) >= 9 and parts[3] == "1" and parts[4] == "4":
                        mgmt[key] = ".".join(parts[5:9])

        results: list[dict[str, Any]] = []
        for key, row in rows.items():
            port_num = row.get("local_port_num", "")
            results.append({
                **row,
                "local_port_desc": loc_ports.get(port_num),
                "mgmt_address":    mgmt.get(key),
            })
        return results

    def _extract_cdp(
        self, raw: dict[str, Any], vendor: str | None
    ) -> list[dict[str, Any]]:
        if vendor != "cisco":
            return []
        _CDP_DEV_ID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6."
        _CDP_PORT   = "1.3.6.1.4.1.9.9.23.1.2.1.1.7."
        _CDP_ADDR   = "1.3.6.1.4.1.9.9.23.1.2.2.1.4."

        rows: dict[str, dict[str, Any]] = {}
        for k, v in raw.items():
            sk = str(k)
            for prefix, col in ((_CDP_DEV_ID, "device_id"), (_CDP_PORT, "remote_port")):
                if sk.startswith(prefix):
                    rows.setdefault(sk[len(prefix):], {})[col] = self.text(v)

        return [
            {"device_id": row.get("device_id"), "remote_port": row.get("remote_port"),
             "mgmt_address": None, "local_port_index": idx}
            for idx, row in rows.items()
            if row.get("device_id")
        ]

    def _extract_arp(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        _ARP_MAC = "1.3.6.1.2.1.4.22.1.2."
        entries: list[dict[str, Any]] = []
        for k, v in raw.items():
            if str(k).startswith(_ARP_MAC):
                suffix = str(k)[len(_ARP_MAC):]
                parts  = suffix.split(".", 1)
                if len(parts) == 2:
                    ip_parts = parts[1].split(".")
                    if len(ip_parts) == 4:
                        try:
                            ip = ".".join(str(int(p)) for p in ip_parts)
                            mac = self.mac(v)
                            if mac and mac not in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
                                entries.append({"ip_address": ip, "mac": mac})
                        except ValueError:
                            pass
        return entries

    def _extract_mac(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        _FDB_PORT   = "1.3.6.1.2.1.17.4.3.1.2."
        _FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3."
        entries: list[dict[str, Any]] = []
        for k, v in raw.items():
            sk = str(k)
            if sk.startswith(_FDB_PORT):
                mac_sfx = sk[len(_FDB_PORT):]
                parts   = mac_sfx.split(".")
                if len(parts) == 6:
                    try:
                        mac = ":".join(f"{int(p):02X}" for p in parts)
                        status_code = str(raw.get(_FDB_STATUS + mac_sfx, "3")).strip()
                        if status_code != "2":  # skip invalid
                            entries.append({
                                "mac": mac, "port": self.num(v), "if_index": None,
                                "status": {"3": "learned", "4": "self", "5": "mgmt"}.get(status_code, "other"),
                            })
                    except (ValueError, TypeError):
                        pass
        return entries[:500]    # cap at 500 for large L2 devices

    def _extract_route_gws(self, raw: dict[str, Any]) -> list[str]:
        _FWD_NEXTHOP = "1.3.6.1.2.1.4.21.1.4."
        gws: set[str] = set()
        for k, v in raw.items():
            if str(k).startswith(_FWD_NEXTHOP):
                gw = str(v).strip()
                if gw and gw != "0.0.0.0":
                    gws.add(gw)
        return list(gws)[:50]   # cap at 50 gateway IPs
