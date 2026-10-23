"""Provider-neutral Windows hardware sensor contracts.

Providers are intentionally read-only.  A provider must use the already
authorized Windows connection supplied by the caller; this module never
creates a WinRM session or executes arbitrary PowerShell.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import math
from typing import Any, Literal, Protocol


SensorStatus = Literal[
    "ok",
    "unavailable",
    "unsupported",
    "permission_denied",
    "provider_not_installed",
    "collection_failed",
]


@dataclass(frozen=True)
class SensorReading:
    sensor_id: str
    name: str
    sensor_type: str
    value: float | None
    unit: str
    source: str
    status: SensorStatus
    collected_at: str
    error: str | None = None
    identifier: str | None = None
    hardware_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        # Keep the Phase 2A field available while the normalized contract uses
        # the shorter ``name`` field.
        result["sensor_name"] = self.name
        return result


@dataclass(frozen=True)
class SensorProviderResult:
    provider: str
    status: SensorStatus
    sensors: tuple[SensorReading, ...] = ()
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "error": self.error,
            "sensors": [sensor.as_dict() for sensor in self.sensors],
        }


class SensorProvider(Protocol):
    def discover(self) -> SensorProviderResult:
        """Collect read-only readings through an already-secured connection."""


def stable_sensor_id(source: str, sensor_type: str, name: str) -> str:
    """Return a deterministic, non-secret identifier for a sensor identity."""
    identity = "|".join((source, sensor_type, name)).encode("utf-8")
    return f"sensor-{sha256(identity).hexdigest()[:24]}"


def normalize_sensor(raw: dict[str, Any]) -> SensorReading:
    """Normalize legacy native-provider dictionaries into the Phase 2B contract."""
    name = str(raw.get("sensor_name") or raw.get("name") or "Unknown sensor")
    sensor_type = str(raw.get("sensor_type") or "unknown")
    source = str(raw.get("source") or "unknown")
    value = raw.get("value")
    invalid_value = False
    if value is not None:
        try:
            value = float(value)
            if not math.isfinite(value):
                value = None
                invalid_value = True
        except (TypeError, ValueError):
            value = None
            invalid_value = True
    status = raw.get("status") or ("ok" if value is not None else "unavailable")
    allowed = {"ok", "unavailable", "unsupported", "permission_denied", "provider_not_installed", "collection_failed"}
    if status not in allowed:
        status = "collection_failed"
    if invalid_value and status == "ok":
        status = "unavailable"
    if status != "ok":
        value = None
    return SensorReading(
        sensor_id=str(raw.get("sensor_id") or stable_sensor_id(source, sensor_type, str(raw.get("identifier") or name))),
        name=name,
        sensor_type=sensor_type,
        value=value,
        unit=str(raw.get("unit") or ""),
        source=source,
        status=status,
        collected_at=str(raw.get("collected_at") or ""),
        error=raw.get("error") or ("invalid_reading" if invalid_value else None),
        identifier=raw.get("identifier"),
        hardware_id=raw.get("hardware_id"),
    )


class NativeCIMSensorProvider:
    """Adapter for the existing native WMI/CIM sensor collector."""

    name = "native_wmi"

    def __init__(self, client: Any):
        self.client = client

    def discover(self) -> SensorProviderResult:
        try:
            readings = tuple(normalize_sensor(item) for item in self.client.native_sensor_discovery())
        except Exception as exc:
            return SensorProviderResult(self.name, "collection_failed", error=str(exc))
        return SensorProviderResult(self.name, "ok" if readings else "unsupported", readings)


class LibreHardwareMonitorProvider:
    """Read-only adapter for LibreHardwareMonitor's WMI provider."""

    name = "librehardwaremonitor"

    def __init__(self, client: Any | None = None):
        self.client = client

    @staticmethod
    def _mapping(sensor_type: str) -> tuple[str, str] | None:
        return {
            "Temperature": ("temperature", "°C"),
            "Fan": ("fan", "RPM"),
            "Load": ("load", "%"),
            "Clock": ("clock", "MHz"),
            "Voltage": ("voltage", "V"),
            "Power": ("power", "W"),
            "Data": ("data", ""),
        }.get(sensor_type or "")

    def discover(self) -> SensorProviderResult:
        if self.client is None:
            return SensorProviderResult(self.name, "provider_not_installed", error="Windows-side provider is not installed")
        try:
            rows = self.client.librehardwaremonitor_sensors()
        except Exception as exc:
            category = getattr(exc, "category", "protocol")
            if category in {"permission", "authentication"}:
                return SensorProviderResult(self.name, "permission_denied", error=getattr(exc, "message", str(exc)))
            if category in {"transport", "timeout", "tls"}:
                return SensorProviderResult(self.name, "collection_failed", error=str(exc))
            return SensorProviderResult(self.name, "provider_not_installed", error="LibreHardwareMonitor WMI namespace is unavailable")
        if not rows:
            return SensorProviderResult(self.name, "unsupported", error="No sensors were returned")
        collected_at = datetime.now(timezone.utc).isoformat()
        readings = []
        for row in rows:
            mapping = self._mapping(row.get("SensorType") or "")
            sensor_type, unit = mapping or ("unknown", "")
            raw = row.get("Value")
            try:
                value = float(raw) if raw is not None else None
                if value is not None and not math.isfinite(value):
                    value = None
            except (TypeError, ValueError):
                value = None
            identifier = row.get("Identifier") or row.get("Name") or "Unknown sensor"
            source = "librehardwaremonitor:root/LibreHardwareMonitor"
            readings.append(SensorReading(
                sensor_id=stable_sensor_id(source, sensor_type, identifier),
                name=row.get("Name") or identifier,
                sensor_type=sensor_type,
                value=value,
                unit=unit,
                source=source,
                status="ok" if value is not None else "unavailable",
                collected_at=collected_at,
                error=None if value is not None else "invalid_reading",
                identifier=identifier,
                hardware_id=row.get("HardwareId"),
            ))
        return SensorProviderResult(self.name, "ok", tuple(readings))
