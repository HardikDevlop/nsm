"""
Wireless Collector — SSID, client, AP, channel, signal metrics.

MIBs / OIDs used
-----------------
  IEEE 802.11 MIB      (1.2.840.10036.1 — rarely implemented)
  Cisco WLC MIB        (1.3.6.1.4.1.9.9.512 / 1.3.6.1.4.1.9.9.619)
  MikroTik Wireless    (1.3.6.1.4.1.14988.1.1.1)
  Ubiquiti / Aruba     (via vendor profiles — future extension)

Returned fields
---------------
  ssids          list[SSIDRecord]
  access_points  list[APRecord]
  total_clients  int
  ap_count       int

SSIDRecord  {ssid, bssid, clients, channel, band, security}
APRecord    {name, mac, ip, clients, signal_dbm, noise_dbm, channel, status}
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# ---------------------------------------------------------------------------
# Cisco WLC (CISCO-LWAPP-AP-MIB / CISCO-CAPWAP-DOT11-STATISTICS-MIB)
# ---------------------------------------------------------------------------
_CISCO_AP_COUNT      = "1.3.6.1.4.1.9.9.619.1.1.1.0"
_CISCO_CLIENT_COUNT  = "1.3.6.1.4.1.9.9.619.1.2.1.0"
_CISCO_SSID_TABLE    = "1.3.6.1.4.1.9.9.512.1.1.1.1"
_CISCO_AP_TABLE      = "1.3.6.1.4.1.9.9.513.1.1.1.1"

# Cisco SSID table column suffixes
_CISCO_SSID_COLS: dict[str, str] = {
    "4": "ssid",
    "5": "bssid_raw",
    "6": "clients",
    "7": "channel",
    "34": "security",
}

# ---------------------------------------------------------------------------
# MikroTik Wireless  (MIKROTIK-MIB)
# ---------------------------------------------------------------------------
_MT_IFACE_TABLE  = "1.3.6.1.4.1.14988.1.1.1.3.1"   # mtxrWlApTable
_MT_SSID_COL     = "1.3.6.1.4.1.14988.1.1.1.3.1.4." # mtxrWlApSsid
_MT_CLIENT_COL   = "1.3.6.1.4.1.14988.1.1.1.3.1.6." # mtxrWlApClientCount
_MT_CHANNEL_COL  = "1.3.6.1.4.1.14988.1.1.1.3.1.5." # mtxrWlApChannel

_MT_STA_TABLE    = "1.3.6.1.4.1.14988.1.1.1.2.1"    # mtxrWlRtabTable
_MT_STA_SIGNAL   = "1.3.6.1.4.1.14988.1.1.1.2.1.3." # mtxrWlRtabStrength
_MT_STA_NOISE    = "1.3.6.1.4.1.14988.1.1.1.2.1.17." # mtxrWlRtabTxStrength


class WirelessCollector(BaseCollector):
    """
    Collects wireless metrics.
    Supports Cisco WLC, MikroTik, and generic 802.11 MIB.
    """

    name = "wireless"

    _WIRELESS_VENDORS = {"cisco", "mikrotik", "aruba", "ubiquiti", "generic"}
    _WIRELESS_TYPES   = {"wireless_controller", "access_point"}

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

        ssids:   list[dict[str, Any]] = []
        aps:     list[dict[str, Any]] = []
        ap_count:    int | None = None
        total_clients: int | None = None

        # ---------------------------------------------------------------
        # Cisco WLC
        # ---------------------------------------------------------------
        if vendor == "cisco":
            ap_count      = self._int(raw_flat.get(_CISCO_AP_COUNT))
            total_clients = self._int(raw_flat.get(_CISCO_CLIENT_COUNT))
            ssids         = self._parse_cisco_ssid(raw_flat)

        # ---------------------------------------------------------------
        # MikroTik
        # ---------------------------------------------------------------
        elif vendor == "mikrotik":
            ssids, total_clients = self._parse_mikrotik(raw_flat)
            ap_count = 1 if ssids else 0

        # ---------------------------------------------------------------
        # Vendor-profile based (OIDRegistry)
        # ---------------------------------------------------------------
        elif oid_registry:
            ssids, ap_count, total_clients = self._parse_via_registry(
                raw_flat, oid_registry, vendor_profile
            )

        if not ssids and ap_count is None and total_clients is None:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    f"No wireless OIDs responded for vendor={vendor!r} "
                    f"device_type={dtype!r} — WLAN may not be supported"
                ),
                missing=["ssid", "clients", "ap_count"],
            )

        # Compute totals if not already set
        if total_clients is None and ssids:
            total_clients = sum(s.get("clients") or 0 for s in ssids)
        if ap_count is None:
            ap_count = len(aps) or (1 if ssids else 0)

        return CollectorResponse.ok(
            self.name,
            {
                "ssids":         ssids,
                "access_points": aps,
                "ssid_count":    len(ssids),
                "ap_count":      ap_count,
                "total_clients": total_clients,
            },
            missing,
            warnings,
        )

    # ------------------------------------------------------------------
    # Cisco SSID parser
    # ------------------------------------------------------------------

    def _parse_cisco_ssid(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        ssids: list[dict[str, Any]] = {}   # type: ignore[assignment]
        prefix = _CISCO_SSID_TABLE + "."
        for k, v in raw.items():
            sk = str(k)
            if not sk.startswith(prefix):
                continue
            rest  = sk[len(prefix):]
            parts = rest.split(".", 1)
            if len(parts) < 2:
                continue
            col, idx = parts[0], parts[1]
            field = _CISCO_SSID_COLS.get(col)
            if field:
                ssids.setdefault(idx, {})[field] = v  # type: ignore[index]

        result: list[dict[str, Any]] = []
        for idx, row in ssids.items():  # type: ignore[attr-defined]
            ssid_name = self.text(row.get("ssid"))
            if not ssid_name:
                continue
            result.append({
                "ssid":     ssid_name,
                "bssid":    self.mac(row.get("bssid_raw")),
                "clients":  self._int(row.get("clients")),
                "channel":  self._int(row.get("channel")),
                "band":     None,
                "security": self.text(row.get("security")),
            })
        return result

    # ------------------------------------------------------------------
    # MikroTik parser
    # ------------------------------------------------------------------

    def _parse_mikrotik(
        self, raw: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int | None]:
        ssids: list[dict[str, Any]] = []
        indexes: set[str] = set()

        for k in raw:
            sk = str(k)
            if sk.startswith(_MT_SSID_COL):
                indexes.add(sk[len(_MT_SSID_COL):])

        total_clients = 0
        for idx in sorted(indexes):
            ssid_val    = self.text(raw.get(_MT_SSID_COL  + idx))
            clients_val = self._int(raw.get(_MT_CLIENT_COL + idx))
            channel_val = self.text(raw.get(_MT_CHANNEL_COL + idx))

            if not ssid_val:
                continue

            total_clients += clients_val or 0
            ssids.append({
                "ssid":     ssid_val,
                "bssid":    None,
                "clients":  clients_val,
                "channel":  channel_val,
                "band":     None,
                "security": None,
            })

        return ssids, (total_clients if ssids else None)

    # ------------------------------------------------------------------
    # OIDRegistry-based fallback
    # ------------------------------------------------------------------

    def _parse_via_registry(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> tuple[list[dict[str, Any]], int | None, int | None]:
        ssids: list[dict[str, Any]] = []
        ap_count:    int | None = None
        tot_clients: int | None = None

        # Try SSID table
        ssid_oid = oid_registry.resolve("wireless", "ssid")
        if ssid_oid:
            prefix = ssid_oid.rstrip(".") + "."
            for k, v in raw.items():
                if str(k).startswith(prefix):
                    ssid_val = self.text(v)
                    if ssid_val:
                        ssids.append({
                            "ssid": ssid_val, "bssid": None,
                            "clients": None, "channel": None,
                            "band": None, "security": None,
                        })

        # AP count
        ap_oid = oid_registry.resolve("wireless", "ap_count")
        if ap_oid:
            v = raw.get(ap_oid) or raw.get(ap_oid + ".0")
            ap_count = self._int(v)

        # Total clients
        cli_oid = oid_registry.resolve("wireless", "client_count")
        if cli_oid:
            v = raw.get(cli_oid) or raw.get(cli_oid + ".0")
            tot_clients = self._int(v)

        return ssids, ap_count, tot_clients

    @staticmethod
    def _int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None
