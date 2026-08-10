"""MAC address -> Vendor name lookup.

This is the primary source of truth for device naming by MAC prefix
(OUI). Add new prefixes here and they will automatically be picked up
by the discovery pipeline and the REST API.

Prefixes MUST be lowercase hex, colon-separated, and at least 3 octets
(6 hex chars). Longer prefixes win over shorter ones on a tie.
"""

from __future__ import annotations

# Ordered list of (prefix, vendor). Longer prefixes are matched first.
OUI_TABLE: list[tuple[str, str]] = [
    # --- User-supplied seed list ---
 
    ("98:a8:78", "Agnigate Technologies Private Limited"),
    
]

# Pre-sorted once at import time: longest prefix first, then lexicographic.
_OUI_SORTED = sorted(OUI_TABLE, key=lambda kv: (-len(kv[0]), kv[0]))


def _normalize(mac: str | None) -> str:
    if not mac:
        return ""
    # Accept "AA-BB-CC...", "AABBCCDDEEFF", "aa:bb:cc..." — normalize to lowercase "aa:bb:cc".
    cleaned = mac.strip().lower().replace("-", ":")
    if ":" not in cleaned:
        # bare hex -> insert colons every 2 chars
        if len(cleaned) >= 6 and all(c in "0123456789abcdef" for c in cleaned):
            cleaned = ":".join(cleaned[i:i + 2] for i in range(0, min(len(cleaned), 12), 2))
    return cleaned


def lookup_vendor(mac: str | None, default: str = "Unknown") -> str:
    """Return the vendor name for a MAC address, or ``default`` if unknown."""
    normalized = _normalize(mac)
    if not normalized:
        return default
    for prefix, vendor in _OUI_SORTED:
        if normalized.startswith(prefix):
            return vendor
    return default


def list_vendors() -> list[dict[str, str]]:
    """Expose the OUI table (useful for a REST endpoint)."""
    return [{"prefix": p, "vendor": v} for p, v in _OUI_SORTED]


def add_vendor(prefix: str, vendor: str) -> None:
    """Append a new OUI entry at runtime (in-memory only)."""
    cleaned = _normalize(prefix)
    if not cleaned or len(cleaned) < 8:
        raise ValueError(f"prefix {prefix!r} is too short; need at least 3 octets")
    OUI_TABLE.append((cleaned, vendor))
    _OUI_SORTED.sort(key=lambda kv: (-len(kv[0]), kv[0]))
