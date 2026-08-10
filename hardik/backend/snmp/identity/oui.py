"""
MacOuiResolver — OUI (MAC prefix) → manufacturer lookup.

Priority
--------
1. Database-backed vendor_ouis table (updated at runtime, longest match wins)
2. In-memory hardik/vendor_map.py OUI_TABLE (legacy fallback)
3. "Unknown"

OUI formats accepted
--------------------
  AA:BB:CC:DD:EE:FF
  AA-BB-CC-DD-EE-FF
  AABBCCDDEEFF
  0xAABBCC...

All lookups are cached in-process for the lifetime of the request cycle.
The cache is a simple dict; it is NOT shared across processes.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# Regex: strip common separators and 0x prefix
_NORMALIZE_RE = re.compile(r"[:\-\s]|^0x", re.I)


def normalize_mac(raw: str | None) -> str | None:
    """
    Return uppercase colon-separated MAC, or None if not 12 hex chars.

    Example: "aa:bb:cc:dd:ee:ff" → "AA:BB:CC:DD:EE:FF"
    """
    if not raw:
        return None
    cleaned = _NORMALIZE_RE.sub("", raw).upper()
    if len(cleaned) != 12 or not all(c in "0123456789ABCDEF" for c in cleaned):
        return None
    return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))


def extract_oui(mac: str, bits: int = 24) -> str | None:
    """
    Extract OUI from normalized (colon-sep uppercase) MAC address.

    bits=24  → first 3 octets  ("AA:BB:CC")
    bits=28  → first 3.5 octets
    bits=36  → first 4.5 octets
    """
    norm = normalize_mac(mac)
    if not norm:
        return None
    # 24-bit OUI = first 3 bytes
    return ":".join(norm.split(":")[:3])


class MacOuiResolver:
    """
    Resolves MAC addresses to manufacturer names.

    Usage (with DB session):
        resolver = MacOuiResolver(db=db_session)
        result = resolver.resolve("AA:BB:CC:DD:EE:FF")
        # → {"manufacturer": "Agnigate Technologies", "vendor_key": "agnigate",
        #     "confidence": 0.95, "source": "database"}

    Usage (without DB — legacy fallback only):
        resolver = MacOuiResolver()
        result = resolver.resolve("AA:BB:CC:DD:EE:FF")
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._cache: dict[str, dict[str, Any]] = {}

    def resolve(self, mac: str | None) -> dict[str, Any]:
        """
        Resolve a MAC address to manufacturer information.

        Returns
        -------
        {
            "mac":          str | None,   # normalized XX:XX:XX:XX:XX:XX
            "oui":          str | None,   # XX:XX:XX
            "manufacturer": str | None,
            "vendor_key":   str | None,
            "confidence":   float,        # 0.0 – 1.0
            "source":       str           # "database" | "legacy_map" | "unknown"
        }
        """
        norm = normalize_mac(mac)
        if not norm:
            return self._empty(mac)

        oui = extract_oui(norm)
        if not oui:
            return self._empty(mac)

        # Cache hit
        if oui in self._cache:
            cached = dict(self._cache[oui])
            cached["mac"] = norm
            return cached

        # 1. Database lookup
        if self._db:
            result = self._db_lookup(oui)
            if result:
                result["mac"] = norm
                self._cache[oui] = {k: v for k, v in result.items() if k != "mac"}
                return result

        # 2. Legacy in-memory vendor_map.py
        result = self._legacy_lookup(norm)
        result["mac"] = norm
        self._cache[oui] = {k: v for k, v in result.items() if k != "mac"}
        return result

    def resolve_many(self, macs: list[str]) -> list[dict[str, Any]]:
        return [self.resolve(m) for m in macs]

    # ------------------------------------------------------------------

    def _db_lookup(self, oui: str) -> dict[str, Any] | None:
        """Query vendor_ouis table. Longest OUI match wins."""
        try:
            from backend.models.identity import VendorOUI  # noqa: PLC0415
            rows = (
                self._db.query(VendorOUI)
                .filter(VendorOUI.oui == oui)
                .all()
            )
            if not rows:
                return None
            # Pick longest OUI match (in case we later support 28/36-bit OUIs)
            best = max(rows, key=lambda r: len(r.oui))
            return {
                "oui":          best.oui,
                "manufacturer": best.manufacturer,
                "vendor_key":   best.vendor_key,
                "confidence":   0.95,
                "source":       "database",
            }
        except Exception as exc:
            logger.debug("DB OUI lookup failed: %s", exc)
            return None

    def _legacy_lookup(self, mac: str) -> dict[str, Any]:
        """Fallback to vendor_map.py in-memory table."""
        try:
            from vendor_map import lookup_vendor  # type: ignore  # noqa: PLC0415
            name = lookup_vendor(mac)
            if name and name.lower() not in ("unknown", ""):
                return {
                    "oui":          extract_oui(mac),
                    "manufacturer": name,
                    "vendor_key":   name.lower().replace(" ", "_")[:40],
                    "confidence":   0.7,
                    "source":       "legacy_map",
                }
        except Exception:
            pass
        return self._empty_base(extract_oui(mac) or "")

    @staticmethod
    def _empty(raw_mac: str | None) -> dict[str, Any]:
        return {
            "mac": raw_mac,
            "oui": None,
            "manufacturer": None,
            "vendor_key": None,
            "confidence": 0.0,
            "source": "unknown",
        }

    @staticmethod
    def _empty_base(oui: str) -> dict[str, Any]:
        return {
            "oui": oui,
            "manufacturer": None,
            "vendor_key": None,
            "confidence": 0.0,
            "source": "unknown",
        }
