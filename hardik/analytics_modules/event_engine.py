"""Phase-5 event engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


class EventEngine:
    """Normalize monitor samples, syslog entries, and traps into events."""

    def from_monitor_sample(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        """Create events from a monitoring sample."""
        events: list[dict[str, Any]] = []
        ip_address = sample.get("ip")
        timestamp = sample.get("timestamp") or datetime.now(timezone.utc).isoformat()

        if sample.get("monitor") == "icmp":
            state = "up" if sample.get("up") else "down"
            events.append(self._event(ip_address, "icmp.status", state, "info" if sample.get("up") else "critical", timestamp, sample))
            if sample.get("packet_loss_percent", 0) and sample.get("packet_loss_percent") > 0:
                events.append(self._event(ip_address, "icmp.packet_loss", sample.get("packet_loss_percent"), "warning", timestamp, sample))

        if sample.get("monitor") == "snmp":
            for metric in ("cpu_percent", "memory_percent", "bandwidth_total_octets", "temperature_celsius", "power_status"):
                if sample.get(metric) is not None:
                    events.append(self._event(ip_address, f"snmp.{metric}", sample.get(metric), "info", timestamp, sample))

        return events

    def normalize_external(self, raw_events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize syslog/trap events into the common event shape."""
        normalized: list[dict[str, Any]] = []
        for raw in raw_events:
            event_type = raw.get("source", "external")
            severity = self._severity(raw)
            normalized.append(
                self._event(
                    raw.get("source_ip"),
                    event_type,
                    raw.get("message"),
                    severity,
                    raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                    raw,
                )
            )
        return normalized

    @staticmethod
    def _event(ip_address: Any, event_type: str, value: Any, severity: str, timestamp: str, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "ip": ip_address,
            "type": event_type,
            "value": value,
            "severity": severity,
            "timestamp": timestamp,
            "raw": raw,
        }

    @staticmethod
    def _severity(raw: dict[str, Any]) -> str:
        severity = raw.get("severity")
        if isinstance(severity, int):
            if severity <= 2:
                return "critical"
            if severity <= 4:
                return "warning"
        return "info"

