"""
Firewall Collector — vendor-specific firewall metrics.

Supported vendors
-----------------
  Fortinet  FortiGate   (1.3.6.1.4.1.12356)
  Palo Alto PAN-OS      (1.3.6.1.4.1.25461)
  Sophos    UTM/XG      (1.3.6.1.4.1.2604)
  Cisco     ASA/FTD     (1.3.6.1.4.1.9.9.147 / 1.3.6.1.4.1.9.9.392)

Returned fields
---------------
  sessions_active      int | None
  sessions_max         int | None
  session_usage_pct    float | None
  vpn_users_active     int | None
  nat_sessions         int | None
  policy_hits          int | None
  threat_count         int | None
  ips_events           int | None
  ha_status            str | None   — "active" | "passive" | "standalone" | ...
  ha_peer_state        str | None
  cpu_percent          float | None  (firewall-specific, may differ from system CPU)
  memory_percent       float | None
  vendor               str
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# ---------------------------------------------------------------------------
# Fortinet FortiGate OIDs  (FORTINET-FORTIGATE-MIB)
# ---------------------------------------------------------------------------
_FG_SESSIONS        = "1.3.6.1.4.1.12356.101.4.1.8.0"
_FG_SESSION_MAX     = "1.3.6.1.4.1.12356.101.4.1.9.0"
_FG_CPU             = "1.3.6.1.4.1.12356.101.4.1.3.0"
_FG_MEM_TOTAL       = "1.3.6.1.4.1.12356.101.4.5.1.0"
_FG_MEM_USED        = "1.3.6.1.4.1.12356.101.4.5.2.0"
_FG_HA_STATE        = "1.3.6.1.4.1.12356.101.13.1.3.0"
_FG_HA_MODE         = "1.3.6.1.4.1.12356.101.13.1.1.0"
_FG_VPN_USERS       = "1.3.6.1.4.1.12356.101.12.2.3.1.1.0"
_FG_IPS_EVENTS      = "1.3.6.1.4.1.12356.101.9.1.1.0"
_FG_THREAT_COUNT    = "1.3.6.1.4.1.12356.101.9.1.2.0"

_FG_HA_STATE_MAP: dict[str, str] = {
    "1": "standalone", "2": "active", "3": "passive", "4": "electing",
}

# ---------------------------------------------------------------------------
# Palo Alto PAN-OS OIDs  (PAN-COMMON-MIB)
# ---------------------------------------------------------------------------
_PA_SESSIONS        = "1.3.6.1.4.1.25461.2.1.2.4.3.0"
_PA_SESSION_MAX     = "1.3.6.1.4.1.25461.2.1.2.4.6.0"
_PA_TCP_SESSIONS    = "1.3.6.1.4.1.25461.2.1.2.4.4.0"
_PA_UDP_SESSIONS    = "1.3.6.1.4.1.25461.2.1.2.4.5.0"
_PA_MGMT_CPU        = "1.3.6.1.4.1.25461.2.1.2.1.3.0"
_PA_DATA_CPU        = "1.3.6.1.4.1.25461.2.1.2.1.4.0"
_PA_MEM_TOTAL       = "1.3.6.1.4.1.25461.2.1.2.1.5.0"
_PA_MEM_USED        = "1.3.6.1.4.1.25461.2.1.2.1.6.0"
_PA_HA_LOCAL        = "1.3.6.1.4.1.25461.2.1.2.1.11.0"
_PA_HA_PEER         = "1.3.6.1.4.1.25461.2.1.2.1.12.0"
_PA_THREAT_COUNT    = "1.3.6.1.4.1.25461.2.1.3.4.0"
_PA_IPS_EVENTS      = "1.3.6.1.4.1.25461.2.1.3.5.0"
_PA_VPN_TUNNELS     = "1.3.6.1.4.1.25461.2.1.2.5.1.0"

_PA_HA_STATE_MAP: dict[str, str] = {
    "0": "disabled", "1": "passive", "2": "active",
    "3": "active-primary", "4": "active-secondary",
}

# ---------------------------------------------------------------------------
# Sophos UTM/XG OIDs
# ---------------------------------------------------------------------------
_SOPHOS_SESSIONS    = "1.3.6.1.4.1.2604.5.1.5.1.0"
_SOPHOS_CONN_MAX    = "1.3.6.1.4.1.2604.5.1.5.2.0"
_SOPHOS_CPU         = "1.3.6.1.4.1.2604.5.1.2.1.0"
_SOPHOS_MEM_TOTAL   = "1.3.6.1.4.1.2604.5.1.3.1.0"
_SOPHOS_MEM_FREE    = "1.3.6.1.4.1.2604.5.1.3.2.0"
_SOPHOS_HA_STATUS   = "1.3.6.1.4.1.2604.5.1.1.3.0"
_SOPHOS_LIVE_USERS  = "1.3.6.1.4.1.2604.5.1.6.1.0"
_SOPHOS_IPS_EVENTS  = "1.3.6.1.4.1.2604.5.1.7.1.0"

_SOPHOS_HA_MAP: dict[str, str] = {
    "0": "standalone", "1": "primary", "2": "auxiliary", "3": "faulty",
}

# ---------------------------------------------------------------------------
# Cisco ASA OIDs  (CISCO-FIREWALL-MIB / CISCO-REMOTE-ACCESS-MONITOR-MIB)
# ---------------------------------------------------------------------------
_CISCO_CONN_COUNT   = "1.3.6.1.4.1.9.9.147.1.2.2.2.1.5.40.6"
_CISCO_CONN_LIMIT   = "1.3.6.1.4.1.9.9.147.1.2.2.2.1.5.40.7"
_CISCO_VPN_USERS    = "1.3.6.1.4.1.9.9.392.1.3.29.0"
_CISCO_VPN_TUNNELS  = "1.3.6.1.4.1.9.9.392.1.3.29.0"


class FirewallCollector(BaseCollector):
    """
    Collects firewall-specific metrics.
    Falls back gracefully when vendor is not a firewall.
    """

    name = "firewall"

    _FIREWALL_VENDORS = {"fortinet", "paloalto", "sophos", "cisco"}
    _FIREWALL_TYPES   = {"firewall"}

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
            vendor   = raw.vendor or "generic"
            dtype    = raw.device_type or "unknown"
        else:
            from ..normalizer import NormalizationLayer  # noqa: PLC0415
            device   = NormalizationLayer().normalize(raw)
            raw_flat = raw
            vendor   = device.vendor or "generic"
            dtype    = device.device_type or "unknown"

        # Only run for firewall vendors / device types
        if vendor not in self._FIREWALL_VENDORS and dtype not in self._FIREWALL_TYPES:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    f"Firewall metrics are vendor-specific; "
                    f"detected vendor={vendor!r} device_type={dtype!r} is not a supported firewall"
                ),
            )

        # Dispatch to vendor parser
        parser = {
            "fortinet":  self._parse_fortinet,
            "paloalto":  self._parse_paloalto,
            "sophos":    self._parse_sophos,
            "cisco":     self._parse_cisco_asa,
        }.get(vendor, self._parse_generic)

        data = parser(raw_flat, vendor_profile)
        data["vendor"] = vendor

        # Nothing useful collected
        if all(v is None for k, v in data.items() if k != "vendor"):
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    f"No firewall OIDs responded for vendor={vendor!r} — "
                    "verify SNMP access and MIB support"
                ),
                missing=["sessions_active", "ha_status"],
            )

        # Warn on high session usage
        if data.get("session_usage_pct") and data["session_usage_pct"] > 80:
            self.warn(
                warnings,
                f"Session table at {data['session_usage_pct']:.1f}% capacity",
            )

        return CollectorResponse.ok(self.name, data, missing, warnings)

    # ------------------------------------------------------------------
    # Fortinet
    # ------------------------------------------------------------------

    def _parse_fortinet(
        self, raw: dict[str, Any], vp: Any
    ) -> dict[str, Any]:
        sessions     = self.num(self._g(raw, _FG_SESSIONS))
        session_max  = self.num(self._g(raw, _FG_SESSION_MAX))
        cpu          = self.num(self._g(raw, _FG_CPU))
        mem_total    = self.num(self._g(raw, _FG_MEM_TOTAL))
        mem_used     = self.num(self._g(raw, _FG_MEM_USED))
        ha_code      = str(self._g(raw, _FG_HA_STATE) or "1").strip()
        vpn_users    = self.num(self._g(raw, _FG_VPN_USERS))
        ips          = self.num(self._g(raw, _FG_IPS_EVENTS))
        threats      = self.num(self._g(raw, _FG_THREAT_COUNT))

        mem_pct = self.percent(mem_used, mem_total) if mem_total else None
        sess_pct = self.percent(sessions, session_max) if session_max else None

        return {
            "sessions_active":   int(sessions) if sessions else None,
            "sessions_max":      int(session_max) if session_max else None,
            "session_usage_pct": sess_pct,
            "cpu_percent":       float(cpu) if cpu is not None else None,
            "memory_percent":    mem_pct,
            "vpn_users_active":  int(vpn_users) if vpn_users else None,
            "nat_sessions":      None,
            "policy_hits":       None,
            "ips_events":        int(ips) if ips else None,
            "threat_count":      int(threats) if threats else None,
            "ha_status":         _FG_HA_STATE_MAP.get(ha_code, ha_code),
            "ha_peer_state":     None,
        }

    # ------------------------------------------------------------------
    # Palo Alto
    # ------------------------------------------------------------------

    def _parse_paloalto(
        self, raw: dict[str, Any], vp: Any
    ) -> dict[str, Any]:
        sessions     = self.num(self._g(raw, _PA_SESSIONS))
        session_max  = self.num(self._g(raw, _PA_SESSION_MAX))
        mgmt_cpu     = self.num(self._g(raw, _PA_MGMT_CPU))
        data_cpu     = self.num(self._g(raw, _PA_DATA_CPU))
        mem_total    = self.num(self._g(raw, _PA_MEM_TOTAL))
        mem_used     = self.num(self._g(raw, _PA_MEM_USED))
        ha_local     = str(self._g(raw, _PA_HA_LOCAL) or "0").strip()
        ha_peer      = str(self._g(raw, _PA_HA_PEER) or "0").strip()
        threats      = self.num(self._g(raw, _PA_THREAT_COUNT))
        ips          = self.num(self._g(raw, _PA_IPS_EVENTS))
        vpn_tunnels  = self.num(self._g(raw, _PA_VPN_TUNNELS))
        tcp_s        = self.num(self._g(raw, _PA_TCP_SESSIONS))
        udp_s        = self.num(self._g(raw, _PA_UDP_SESSIONS))

        mem_pct   = self.percent(mem_used, mem_total) if mem_total else None
        sess_pct  = self.percent(sessions, session_max) if session_max else None
        # Use management plane CPU as overall
        cpu = mgmt_cpu if mgmt_cpu is not None else data_cpu

        return {
            "sessions_active":   int(sessions) if sessions else None,
            "sessions_max":      int(session_max) if session_max else None,
            "session_usage_pct": sess_pct,
            "tcp_sessions":      int(tcp_s) if tcp_s else None,
            "udp_sessions":      int(udp_s) if udp_s else None,
            "cpu_percent":       float(cpu) if cpu is not None else None,
            "memory_percent":    mem_pct,
            "vpn_users_active":  int(vpn_tunnels) if vpn_tunnels else None,
            "nat_sessions":      None,
            "policy_hits":       None,
            "ips_events":        int(ips) if ips else None,
            "threat_count":      int(threats) if threats else None,
            "ha_status":         _PA_HA_STATE_MAP.get(ha_local, ha_local),
            "ha_peer_state":     _PA_HA_STATE_MAP.get(ha_peer, ha_peer),
        }

    # ------------------------------------------------------------------
    # Sophos
    # ------------------------------------------------------------------

    def _parse_sophos(
        self, raw: dict[str, Any], vp: Any
    ) -> dict[str, Any]:
        sessions     = self.num(self._g(raw, _SOPHOS_SESSIONS))
        conn_max     = self.num(self._g(raw, _SOPHOS_CONN_MAX))
        cpu          = self.num(self._g(raw, _SOPHOS_CPU))
        mem_total_kb = self.num(self._g(raw, _SOPHOS_MEM_TOTAL))
        mem_free_kb  = self.num(self._g(raw, _SOPHOS_MEM_FREE))
        ha_code      = str(self._g(raw, _SOPHOS_HA_STATUS) or "0").strip()
        live_users   = self.num(self._g(raw, _SOPHOS_LIVE_USERS))
        ips          = self.num(self._g(raw, _SOPHOS_IPS_EVENTS))

        mem_pct: float | None = None
        if mem_total_kb and mem_free_kb is not None:
            used_kb = float(mem_total_kb) - float(mem_free_kb)
            mem_pct = self.percent(used_kb, mem_total_kb)
        sess_pct = self.percent(sessions, conn_max) if conn_max else None

        return {
            "sessions_active":   int(sessions) if sessions else None,
            "sessions_max":      int(conn_max) if conn_max else None,
            "session_usage_pct": sess_pct,
            "cpu_percent":       float(cpu) if cpu is not None else None,
            "memory_percent":    mem_pct,
            "vpn_users_active":  int(live_users) if live_users else None,
            "nat_sessions":      None,
            "policy_hits":       None,
            "ips_events":        int(ips) if ips else None,
            "threat_count":      None,
            "ha_status":         _SOPHOS_HA_MAP.get(ha_code, ha_code),
            "ha_peer_state":     None,
        }

    # ------------------------------------------------------------------
    # Cisco ASA
    # ------------------------------------------------------------------

    def _parse_cisco_asa(
        self, raw: dict[str, Any], vp: Any
    ) -> dict[str, Any]:
        sessions     = self.num(self._g(raw, _CISCO_CONN_COUNT))
        session_max  = self.num(self._g(raw, _CISCO_CONN_LIMIT))
        vpn_users    = self.num(self._g(raw, _CISCO_VPN_USERS))
        sess_pct = self.percent(sessions, session_max) if session_max else None

        return {
            "sessions_active":   int(sessions) if sessions else None,
            "sessions_max":      int(session_max) if session_max else None,
            "session_usage_pct": sess_pct,
            "cpu_percent":       None,
            "memory_percent":    None,
            "vpn_users_active":  int(vpn_users) if vpn_users else None,
            "nat_sessions":      None,
            "policy_hits":       None,
            "ips_events":        None,
            "threat_count":      None,
            "ha_status":         None,
            "ha_peer_state":     None,
        }

    # ------------------------------------------------------------------
    # Generic / unknown firewall
    # ------------------------------------------------------------------

    def _parse_generic(
        self, raw: dict[str, Any], vp: Any
    ) -> dict[str, Any]:
        return {
            "sessions_active":   None,
            "sessions_max":      None,
            "session_usage_pct": None,
            "cpu_percent":       None,
            "memory_percent":    None,
            "vpn_users_active":  None,
            "nat_sessions":      None,
            "policy_hits":       None,
            "ips_events":        None,
            "threat_count":      None,
            "ha_status":         None,
            "ha_peer_state":     None,
        }

    @staticmethod
    def _g(raw: dict[str, Any], oid: str) -> Any:
        v = raw.get(oid)
        if v is None and not oid.endswith(".0"):
            v = raw.get(oid + ".0")
        return v
