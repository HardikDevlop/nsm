"""Monitoring readiness and health summaries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence


class MonitoringServices:
    """Build health signals from discovery inventory."""

    def summarize(self, devices: Sequence[dict[str, Any]]) -> dict[str, Any]:
        """Return aggregate monitoring statistics."""
        total = len(devices)
        up = sum(1 for device in devices if device.get("reachable") or device.get("status") == "reachable")
        managed = sum(1 for device in devices if (device.get("snmp") or {}).get("reachable") or (device.get("wmi") or {}).get("reachable"))
        return {
            "total_devices": total,
            "up": up,
            "down": total - up,
            "managed": managed,
            "availability_percent": round((up / total) * 100, 2) if total else 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def build_device_health(self, device: dict[str, Any]) -> dict[str, Any]:
        """Return per-device health posture."""
        reachable = bool(device.get("reachable") or device.get("status") == "reachable")
        packet_loss = device.get("packet_loss")
        rtt = device.get("rtt")
        warnings: list[str] = []

        if not reachable:
            warnings.append("Device is unreachable")
        if isinstance(packet_loss, (int, float)) and packet_loss > 20:
            warnings.append("High packet loss")
        if isinstance(rtt, (int, float)) and rtt > 250:
            warnings.append("High latency")
        if not (device.get("snmp") or {}).get("reachable"):
            warnings.append("SNMP unavailable")

        return {
            "state": "critical" if not reachable else "warning" if warnings else "healthy",
            "warnings": warnings,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

