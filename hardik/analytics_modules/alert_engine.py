"""Phase-5 alert engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from config import ALERT_THRESHOLDS


class AlertEngine:
    """Evaluate events and monitor samples against alert thresholds."""

    def __init__(self, thresholds: dict[str, float] | None = None) -> None:
        self.thresholds = thresholds or ALERT_THRESHOLDS

    def evaluate_samples(self, samples: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create alerts from monitoring samples."""
        alerts: list[dict[str, Any]] = []
        for sample in samples:
            alerts.extend(self._evaluate_sample(sample))
        return alerts

    def evaluate_events(self, events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Promote critical/warning events into alerts."""
        alerts: list[dict[str, Any]] = []
        for event in events:
            if event.get("severity") in {"critical", "warning"}:
                alerts.append(self._alert(event.get("ip"), event.get("severity"), event.get("type"), event.get("value"), event))
        return alerts

    def _evaluate_sample(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        ip_address = sample.get("ip")

        if sample.get("monitor") == "icmp" and sample.get("up") is False:
            alerts.append(self._alert(ip_address, "critical", "device_down", "ICMP unreachable", sample))

        for metric, threshold in self.thresholds.items():
            value = sample.get(metric)
            if value is None:
                continue

            if metric == "power_status":
                if value != "normal":
                    alerts.append(self._alert(ip_address, "critical", "power_status", value, sample))
                continue

            if isinstance(value, (int, float)) and value >= threshold:
                severity = "critical" if metric in {"cpu_percent", "memory_percent", "temperature_celsius"} and value >= threshold + 10 else "warning"
                alerts.append(self._alert(ip_address, severity, metric, value, sample))

        return alerts

    @staticmethod
    def _alert(ip_address: Any, severity: Any, alert_type: Any, value: Any, source: dict[str, Any]) -> dict[str, Any]:
        return {
            "ip": ip_address,
            "severity": severity,
            "type": alert_type,
            "value": value,
            "source": source.get("monitor") or source.get("source") or source.get("type"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
        }

