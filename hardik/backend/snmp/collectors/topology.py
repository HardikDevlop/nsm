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
        verification_mismatches: list[dict[str, Any]] = []
        interfaces = self._extract_interfaces(raw_flat)

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
        lldp_neighbors = self._unique_lldp(self._extract_lldp(raw_flat))
        if lldp_neighbors:
            sources_used.append("lldp")
            mac_table = self._extract_mac(raw_flat)
            for nb in lldp_neighbors:
                nb_mac = self.mac(nb.get("remote_chassis_id"))
                learned = [e for e in mac_table if e.get("mac") == nb_mac]
                local_port = nb.get("local_port_desc") or nb.get("local_port_num")
                matching = [e for e in learned if self._port_matches(
                    local_port, nb.get("local_port_num"), e
                )]
                if not nb_mac:
                    verification_mismatches.append({
                        "mac": nb_mac or nb.get("remote_chassis_id"),
                        "local_port": local_port,
                        "mac_table_ports": [e.get("port_name") or e.get("port") for e in learned],
                        "reason": "MAC not found on local port" if learned else "MAC not found in MAC table",
                    })
                    continue
                if not matching:
                    verification_mismatches.append({
                        "mac": nb_mac,
                        "local_port": local_port,
                        "mac_table_ports": [e.get("port_name") or e.get("port") for e in learned],
                        "reason": "LLDP neighbor not present in MAC table on this port",
                    })
                nb_id = nb_mac
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
                    "verified": True,
                    "vlan_id": matching[0].get("vlan_id") if matching else None,
                    "interface": interfaces.get(str(nb.get("local_port_num")), {}),
                    "confidence": "CONFIRMED",
                })

        # ---------------------------------------------------------------
        # 2. CDP neighbors  (Cisco only)
        # ---------------------------------------------------------------
        cdp_neighbors = []
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
        arp_by_mac = {entry["mac"]: entry["ip_address"] for entry in arp_entries if entry.get("mac")}
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
        mac_entries = self._extract_mac(raw_flat)
        if mac_entries:
            sources_used.append("mac_table")
            confirmed_ports = {
                str(nb.get("local_port_desc") or nb.get("local_port_num") or "").strip().lower()
                for nb in lldp_neighbors
            }
            for entry in mac_entries:
                entry_port = str(entry.get("port_name") or entry.get("if_index") or entry.get("port") or "").strip().lower()
                # LLDP/CDP owns a confirmed device-to-device port. MAC table
                # entries on all other ports are endpoint candidates.
                if entry_port in confirmed_ports:
                    continue
                mac = entry.get("mac", "")
                if not mac or entry.get("status") == "self":
                    continue
                nb_id = mac
                if nb_id not in nodes:
                    nodes[nb_id] = {
                        "id":         nb_id,
                        "hostname":   None,
                        "ip":         arp_by_mac.get(mac),
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
                    "vlan_id": entry.get("vlan_id"),
                    "interface": interfaces.get(str(entry.get("if_index") or entry.get("port")), {}),
                    "confidence": "INFERRED",
                    "verified":      True,
                })

        # ---------------------------------------------------------------
        # 5. Routing next-hops
        # ---------------------------------------------------------------
        route_gws = []
        for route in self._extract_routes(raw_flat):
            if route.get("next_hop") and (route.get("destination") == "0.0.0.0" or route.get("prefix_length") == 0):
                route_gws.append(route["next_hop"])
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
                        "protocol": "routing",
                        "confidence": "INFERRED",
                        "gateway_path": True,
                        "verified":      True,
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
                "verification_mismatches": verification_mismatches,
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

    def _unique_lldp(self, neighbors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep one LLDP row per normalized remote chassis MAC."""
        unique: dict[str, dict[str, Any]] = {}
        for nb in neighbors:
            mac = self.mac(nb.get("remote_chassis_id"))
            if not mac:
                continue
            nb = {**nb, "remote_chassis_id": mac}
            unique.setdefault(mac, nb)
        return list(unique.values())

    @staticmethod
    def _port_matches(local_port: Any, local_port_num: Any, entry: dict[str, Any]) -> bool:
        wanted_values = {
            str(value).strip().lower()
            for value in (local_port, local_port_num)
            if value not in (None, "")
        }
        candidates = {
            str(entry.get(k) or "").strip().lower()
            for k in ("port_name", "if_index", "port")
        }
        # Accept common names such as GE15/GigabitEthernet15 when the
        # bridge table exposes only numeric port 15.
        numeric_wanted = {
            value.removeprefix("ge").removeprefix("gi")
            for value in wanted_values
        }
        numeric_candidates = {
            value.removeprefix("ge").removeprefix("gi")
            for value in candidates
        }
        return bool(wanted_values & candidates or numeric_wanted & numeric_candidates)

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
        # Prefer VLAN-aware Q-BRIDGE entries and retain the learned port.
        q_port = "1.3.6.1.2.1.17.7.1.2.2.1.2."
        q_status = "1.3.6.1.2.1.17.7.1.2.2.1.3."
        if_names = {
            str(k)[len("1.3.6.1.2.1.31.1.1.1.1."):]: self.text(v)
            for k, v in raw.items()
            if str(k).startswith("1.3.6.1.2.1.31.1.1.1.1.")
        }
        bridge_to_if = {
            int(str(k)[len("1.3.6.1.2.1.17.1.4.1.2."):]): int(self.num(v))
            for k, v in raw.items()
            if str(k).startswith("1.3.6.1.2.1.17.1.4.1.2.") and self.num(v) is not None
        }
        _FDB_PORT   = "1.3.6.1.2.1.17.4.3.1.2."
        _FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3."
        entries: list[dict[str, Any]] = []
        for k, v in raw.items():
            sk = str(k)
            if not sk.startswith(q_port):
                continue
            suffix = sk[len(q_port):]
            parts = suffix.split(".")
            if len(parts) != 7:
                continue
            try:
                vlan, octets = int(parts[0]), [int(x) for x in parts[1:]]
                if not all(0 <= x <= 255 for x in octets):
                    continue
                mac = ":".join(f"{x:02X}" for x in octets)
                status = str(raw.get(q_status + suffix, "3")).strip()
                if status == "2":
                    continue
                port = self.num(v)
                if_index = bridge_to_if.get(int(port)) if port is not None else None
                entries.append({"mac": mac, "port": port, "if_index": if_index,
                                "port_name": if_names.get(str(if_index)) if if_index is not None else None,
                                "vlan_id": vlan,
                                "status": {"3": "learned", "4": "self", "5": "mgmt"}.get(status, "other")})
            except (ValueError, TypeError):
                continue
        if entries:
            return entries
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
                                "port_name": None, "vlan_id": None,
                                "status": {"3": "learned", "4": "self", "5": "mgmt"}.get(status_code, "other"),
                            })
                    except (ValueError, TypeError):
                        pass
        return entries[:500]    # cap at 500 for large L2 devices

    def _extract_interfaces(self, raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Small indexed interface map used to annotate topology links."""
        rows: dict[str, dict[str, Any]] = {}
        fields = {
            "1.3.6.1.2.1.2.2.1.2.": "description",
            "1.3.6.1.2.1.2.2.1.5.": "speed_bps",
            "1.3.6.1.2.1.2.2.1.8.": "status",
            "1.3.6.1.2.1.31.1.1.1.1.": "name",
            "1.3.6.1.2.1.31.1.1.1.18.": "alias",
        }
        for oid, field in fields.items():
            for key, value in raw.items():
                if str(key).startswith(oid):
                    index = str(key)[len(oid):]
                    rows.setdefault(index, {})[field] = self.num(value) if field == "speed_bps" else self.text(value)
        return rows

    def _extract_routes(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        root = "1.3.6.1.2.1.4.21.1."
        columns = {"1": "destination", "4": "next_hop", "5": "interface", "11": "mask"}
        rows: dict[str, dict[str, Any]] = {}
        for key, value in raw.items():
            text_key = str(key)
            if not text_key.startswith(root):
                continue
            suffix = text_key[len(root):].split(".")
            if len(suffix) < 5 or suffix[0] not in columns:
                continue
            row = ".".join(suffix[1:])
            rows.setdefault(row, {})[columns[suffix[0]]] = self.text(value)
        return [row for row in rows.values() if row.get("next_hop")]

    def _extract_route_gws(self, raw: dict[str, Any]) -> list[str]:
        _FWD_NEXTHOP = "1.3.6.1.2.1.4.21.1.4."
        gws: set[str] = set()
        for k, v in raw.items():
            if str(k).startswith(_FWD_NEXTHOP):
                gw = str(v).strip()
                if gw and gw != "0.0.0.0":
                    gws.add(gw)
        return list(gws)[:50]   # cap at 50 gateway IPs
