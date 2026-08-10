"""
CDP Collector — Cisco Discovery Protocol (Cisco-only).

CISCO-CDP-MIB OID roots
------------------------
  cdpCacheTable            1.3.6.1.4.1.9.9.23.1.2.1.1
    .6  cdpCacheDeviceId     (neighbor hostname)
    .7  cdpCacheDevicePort   (neighbor port)
    .8  cdpCachePlatform     (device model/platform)
    .9  cdpCacheCapabilities (capabilities bitmap)
    .10 cdpCacheVersion      (IOS version string)
    .11 cdpCacheDuplex       (duplex: 1=unknown, 2=half, 3=full)
    .19 cdpCacheLastChange

  cdpCacheAddressTable     1.3.6.1.4.1.9.9.23.1.2.2.1
    .4  cdpCacheAddress      (neighbor management IP)

Row index: <local_if_index>.<rem_index>

Returned fields per CDP neighbor
---------------------------------
  local_port_index  int
  device_id         str     (neighbor hostname)
  platform          str | None
  remote_port       str | None
  mgmt_address      str | None
  capabilities      list[str]
  ios_version       str | None
  duplex            str | None    — "full" | "half" | "unknown"
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# CDP-MIB OID roots
_CDP_CACHE_ROOT = "1.3.6.1.4.1.9.9.23.1.2.1.1."
_CDP_ADDR_ROOT  = "1.3.6.1.4.1.9.9.23.1.2.2.1.4."

# Column definitions
_CDP_COLS: dict[str, str] = {
    "6":  "device_id",
    "7":  "device_port",
    "8":  "platform",
    "9":  "capabilities_raw",
    "10": "version",
    "11": "duplex_code",
    "19": "last_change",
}

# Capability bits (Cisco CDP)
_CDP_CAP_BITS: list[tuple[int, str]] = [
    (0x0001, "Router"),
    (0x0002, "TransparentBridge"),
    (0x0004, "SourceRouteBridge"),
    (0x0008, "Switch"),
    (0x0010, "Host"),
    (0x0020, "IGMP"),
    (0x0040, "Repeater"),
    (0x0080, "VoIP-Phone"),
    (0x0100, "Remotely-Managed-Device"),
    (0x0200, "STP-Dispute"),
    (0x0400, "Video-Endpoint"),
    (0x4000, "Two-port-MAC-Relay"),
]

_DUPLEX: dict[str, str] = {
    "1": "unknown", "2": "half", "3": "full",
}


def _decode_cdp_capabilities(raw_str: str) -> list[str]:
    """Decode CDP capability bitmap (hex OCTET STRING)."""
    caps: list[str] = []
    cleaned = str(raw_str or "").replace(" ", "").replace("0x", "").replace(":", "")
    if not cleaned:
        return caps
    try:
        val = int(cleaned, 16)
        for bit, name in _CDP_CAP_BITS:
            if val & bit:
                caps.append(name)
    except (ValueError, TypeError):
        pass
    return caps


def _parse_cdp_address(raw_str: str) -> str | None:
    """
    Parse CDP address TLV.
    Format: <protocol_type(1)><protocol_length(1)><protocol(N)><addr_length(2)><address>
    For IPv4: type=1, proto_len=1, proto=0xcc (NLPID for IP), len=4, then 4 octets.
    """
    cleaned = str(raw_str or "").replace(" ", "").replace("0x", "").replace(":", "")
    if len(cleaned) >= 16:
        try:
            # Try the standard IPv4 CDP address encoding
            addr_start = 6   # skip protocol header (3 bytes = 6 hex chars)
            # Length field (2 bytes = 4 hex chars)
            addr_len = int(cleaned[addr_start:addr_start+4], 16)
            if addr_len == 4:
                start = addr_start + 4
                octets = [str(int(cleaned[i:i+2], 16)) for i in range(start, start+8, 2)]
                return ".".join(octets)
        except (ValueError, IndexError):
            pass
    # Last resort: try dotted decimal from raw
    parts = str(raw_str).replace(":", " ").split()
    if len(parts) == 4:
        try:
            return ".".join(str(int(p, 16)) for p in parts)
        except ValueError:
            pass
    return None


class CDPCollector(BaseCollector):
    """
    Cisco CDP neighbor collector.
    Returns unsupported for non-Cisco devices.
    """

    name = "cdp"

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
            vendor = raw.vendor or "generic"
        else:
            from ..normalizer import NormalizationLayer  # noqa: PLC0415
            device = NormalizationLayer().normalize(raw)
            raw_flat = raw
            vendor = device.vendor or "generic"

        # CDP is Cisco-only
        if vendor not in ("cisco", "generic"):
            return CollectorResponse.unsupported(
                self.name,
                reason=f"CDP is Cisco-only; detected vendor is {vendor!r}",
            )

        # ---------------------------------------------------------------
        # Parse cdpCacheTable
        # Row index: <col>.<local_if_index>.<rem_index>
        # ---------------------------------------------------------------
        rows: dict[tuple[str, str], dict[str, Any]] = {}

        for k, v in raw_flat.items():
            sk = str(k)
            if not sk.startswith(_CDP_CACHE_ROOT):
                continue
            rest = sk[len(_CDP_CACHE_ROOT):]
            parts = rest.split(".", 2)
            if len(parts) < 3:
                continue
            col, local_if, rem_idx = parts[0], parts[1], parts[2]
            field = _CDP_COLS.get(col)
            if not field:
                continue
            key = (local_if, rem_idx)
            rows.setdefault(key, {})[field] = v

        # ---------------------------------------------------------------
        # Parse cdpCacheAddress
        # ---------------------------------------------------------------
        cdp_addrs: dict[tuple[str, str], str] = {}
        for k, v in raw_flat.items():
            sk = str(k)
            if not sk.startswith(_CDP_ADDR_ROOT):
                continue
            rest = sk[len(_CDP_ADDR_ROOT):]
            parts = rest.split(".", 1)
            if len(parts) == 2:
                local_if, rem_idx = parts[0], parts[1]
                addr = _parse_cdp_address(str(v))
                if addr:
                    cdp_addrs[(local_if, rem_idx)] = addr

        if not rows:
            # Device may be Cisco but CDP may be disabled
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "Cisco CDP table (1.3.6.1.4.1.9.9.23.1.2.1.1) returned no data — "
                    "CDP may be disabled on this device"
                ),
                missing=["cdpCacheDeviceId"],
            )

        # ---------------------------------------------------------------
        # Build result list
        # ---------------------------------------------------------------
        neighbors: list[dict[str, Any]] = []

        for (local_if, rem_idx), row in sorted(rows.items()):
            device_id = self.text(row.get("device_id"))
            if not device_id:
                continue

            caps_raw  = str(row.get("capabilities_raw", ""))
            duplex_raw = str(row.get("duplex_code", "1")).strip()

            neighbors.append({
                "local_port_index":  local_if,
                "device_id":         device_id,
                "platform":          self.text(row.get("platform")),
                "remote_port":       self.text(row.get("device_port")),
                "mgmt_address":      cdp_addrs.get((local_if, rem_idx)),
                "capabilities":      _decode_cdp_capabilities(caps_raw),
                "ios_version":       self.text(row.get("version")),
                "duplex":            _DUPLEX.get(duplex_raw, "unknown"),
                "rem_index":         rem_idx,
            })

        if not neighbors:
            return CollectorResponse.unsupported(
                self.name,
                reason="CDP cache table present but no valid neighbor entries found",
                missing=["cdpCacheDeviceId"],
            )

        return CollectorResponse.ok(
            self.name,
            {
                "neighbors":      neighbors,
                "neighbor_count": len(neighbors),
            },
            missing,
            warnings,
        )
