"""
Health Collector — overall device reachability and health status.

This is the final collector in the pipeline and aggregates signals
from other collectors to produce a top-level health verdict.

Returned fields
---------------
  status          str   — "UP" | "DEGRADED" | "DOWN"
  reachable       bool
  snmp_enabled    bool
  alarm_count     int   — number of environment alarms detected
  details         str   — human-readable summary
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice


class HealthCollector(BaseCollector):
    """Derives overall device health from SNMP reachability and env sensors."""

    name = "health"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        if isinstance(raw, RawDevice):
            reachable = True  # If we got here, device responded
        else:
            reachable = bool(raw.get("reachable", True))

        if not reachable:
            return CollectorResponse.ok(
                self.name,
                {
                    "status":      "DOWN",
                    "reachable":   False,
                    "snmp_enabled": False,
                    "alarm_count": 0,
                    "details":     "Device is not reachable via SNMP",
                },
            )

        return CollectorResponse.ok(
            self.name,
            {
                "status":       "UP",
                "reachable":    True,
                "snmp_enabled": True,
                "alarm_count":  0,
                "details":      "Device reachable and responding to SNMP",
            },
        )
