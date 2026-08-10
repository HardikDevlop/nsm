"""
Agnigate NMS — BaseCollector
==============================
Foundation class for every SNMP collector.

Design contract
---------------
- Every collector inherits BaseCollector.
- Every collector returns CollectorResponse — never raises.
- CollectorResponse.supported=False instead of "Not Supported" strings.
- Collectors never import OID strings directly; they call
  oid_registry.resolve() / oid_registry.value() which probes the walk.
- Adding a new vendor = adding entries to oid_catalog.py only.
  No collector code changes needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CollectorResponse — canonical response envelope
# ---------------------------------------------------------------------------

@dataclass
class CollectorResponse:
    """
    Returned by every collector.

    Fields
    ------
    collector  : snake_case name  (e.g. "cpu")
    supported  : True when data was found
    data       : normalized payload (empty dict when unsupported)
    missing    : OID keys probed but absent from the walk
    warnings   : non-fatal notes
    reason     : set when supported=False; human-readable explanation
    timestamp  : UTC ISO-8601
    """
    collector:  str
    supported:  bool                     = True
    data:       dict[str, Any]           = field(default_factory=dict)
    missing:    list[str]                = field(default_factory=list)
    warnings:   list[str]                = field(default_factory=list)
    reason:     str | None               = None
    timestamp:  str                      = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # -- Constructors --

    @classmethod
    def ok(
        cls,
        collector: str,
        data: dict[str, Any],
        missing:  list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> "CollectorResponse":
        return cls(collector=collector, supported=True, data=data,
                   missing=missing or [], warnings=warnings or [])

    @classmethod
    def unsupported(
        cls,
        collector: str,
        reason: str,
        missing: list[str] | None = None,
    ) -> "CollectorResponse":
        return cls(collector=collector, supported=False, data={},
                   missing=missing or [], reason=reason)

    # -- Serialization --

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "collector": self.collector,
            "supported": self.supported,
            "timestamp": self.timestamp,
        }
        if self.supported:
            out["data"]     = self.data
            out["missing"]  = self.missing
            out["warnings"] = self.warnings
        else:
            out["reason"]  = self.reason
            out["missing"] = self.missing
        return out


# ---------------------------------------------------------------------------
# Legacy shim — kept for backward compatibility
# ---------------------------------------------------------------------------

@dataclass
class CollectorResult:
    """Legacy result type. New code should use CollectorResponse."""
    collector:   str
    data:        dict[str, Any] = field(default_factory=dict)
    unsupported: list[str]      = field(default_factory=list)

    def json(self) -> dict[str, Any]:
        return {"collector": self.collector, "data": self.data,
                "unsupported": self.unsupported}

    @classmethod
    def from_response(cls, resp: CollectorResponse) -> "CollectorResult":
        if resp.supported:
            return cls(resp.collector, resp.data, resp.missing)
        return cls(resp.collector,
                   {"supported": False, "reason": resp.reason},
                   resp.missing)


# ---------------------------------------------------------------------------
# BaseCollector
# ---------------------------------------------------------------------------

class BaseCollector:
    """
    Abstract base.  Sub-classes MUST override name and collect().

    collect() signature:
        def collect(self, raw, oid_registry, vendor_profile) -> CollectorResponse

    - raw           : RawDevice | dict  (the normalized device snapshot)
    - oid_registry  : OIDRegistry       (resolves OIDs from oid_catalog)
    - vendor_profile: DynamicVendorProfile
    """

    name: str = "base"

    def collect(
        self,
        raw: Any,
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement collect()"
        )

    # ------------------------------------------------------------------
    # Shared helpers  (no OID knowledge here — all in oid_catalog)
    # ------------------------------------------------------------------

    @staticmethod
    def num(value: Any) -> float | int | None:
        if isinstance(value, (int, float)):
            return value
        try:
            f = float(str(value).replace(",", "").strip())
            return int(f) if f == int(f) else f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def text(value: Any) -> str | None:
        s = str(value).strip() if value is not None else ""
        bad = {"", "N/A", "None", "noSuchObject", "noSuchInstance",
               "No Such Object", "No Such Instance", "endOfMibView"}
        return s if s not in bad else None

    @staticmethod
    def mac(value: Any) -> str | None:
        raw = str(value or "").replace("0x","").replace(":","").replace("-","").strip()
        if len(raw) == 12 and all(c in "0123456789abcdefABCDEF" for c in raw):
            return ":".join(raw[i:i+2] for i in range(0, 12, 2)).upper()
        return None

    @staticmethod
    def percent(used: Any, total: Any) -> float | None:
        u, t = BaseCollector.num(used), BaseCollector.num(total)
        if u is None or t is None or t == 0:
            return None
        return round(float(u) / float(t) * 100, 2)

    @staticmethod
    def oid_last(oid: str, parts: int = 1) -> str:
        return ".".join(str(oid).split(".")[-parts:])

    @staticmethod
    def find(raw: dict[str, Any], oid_prefix: str) -> dict[str, Any]:
        """Return walk entries whose key starts with oid_prefix as {suffix: value}."""
        prefix_dot = oid_prefix.rstrip(".") + "."
        return {k[len(prefix_dot):]: v for k, v in raw.items()
                if k.startswith(prefix_dot)}

    @staticmethod
    def get(raw: dict[str, Any], oid: str) -> Any:
        v = raw.get(oid)
        if v is None and not oid.endswith(".0"):
            v = raw.get(oid + ".0")
        return v

    def probe(
        self,
        raw: dict[str, Any],
        oid: str,
        missing: list[str],
        label: str | None = None,
    ) -> Any:
        """Look up OID in raw; append label to missing list if absent."""
        v = self.get(raw, oid)
        if v is None:
            missing.append(label or oid)
        return v

    def probe_oids(
        self,
        raw: dict[str, Any],
        oid_map: dict[str, str],
    ) -> dict[str, Any]:
        """
        Probe a dict of {metric: oid} against the walk.
        Returns {metric: value} for every OID that had a value.
        Metrics with no walk response are silently absent from the result.

        This is the dynamic discovery mechanism: callers pass all
        candidate OIDs for a domain and receive only what the device
        actually supports — no static assumptions.
        """
        found: dict[str, Any] = {}
        for metric, oid in oid_map.items():
            v = self.get(raw, oid)
            if v is not None and str(v).strip() not in (
                "", "noSuchObject", "noSuchInstance",
                "No Such Object", "No Such Instance", "endOfMibView"
            ):
                found[metric] = v
        return found

    def warn(self, warnings: list[str], message: str) -> None:
        warnings.append(message)
        logger.debug("[%s] warning: %s", self.name, message)


# ---------------------------------------------------------------------------
# Legacy alias
# ---------------------------------------------------------------------------

class SNMPCollectorBase(BaseCollector):
    """Backward-compatible alias for old collector bodies."""

    def collect(  # type: ignore[override]
        self,
        raw: Any,
        oid_registry: Any = None,
        vendor_profile: Any = None,
    ) -> CollectorResult:
        raise NotImplementedError

    @staticmethod
    def value(raw: dict[str, Any], key: str, unsupported: list[str]) -> Any:
        v = raw.get(key)
        if v in (None, "", "No Such Object", "No Such Instance",
                 "noSuchObject", "noSuchInstance"):
            unsupported.append(key)
            return None
        return v


# Convenience aliases for external imports
_safe_num  = BaseCollector.num
_safe_str  = BaseCollector.text
_safe_mac  = BaseCollector.mac

def _find_in_raw(raw: dict[str, Any], prefix: str) -> dict[str, Any]:
    return BaseCollector.find(raw, prefix)

def _get_oid(raw: dict[str, Any], oid: str) -> Any:
    return BaseCollector.get(raw, oid)
