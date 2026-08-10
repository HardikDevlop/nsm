"""
Environment Collector — temperatures, fans, power supplies, voltages, currents.

Standard MIBs used
-------------------
  ENTITY-SENSOR-MIB (RFC 3433)
    entPhysicalTable      1.3.6.1.2.1.47.1.1.1.1
    entPhySensorTable     1.3.6.1.2.1.99.1.1.1

Vendor fallbacks via OIDRegistry
---------------------------------
  Cisco  CISCO-ENVMON-MIB  (1.3.6.1.4.1.9.9.13)
  Fortinet               (1.3.6.1.4.1.12356.101.4.3)
  Huawei                 (1.3.6.1.4.1.2011.5.25.31.1.1)
  Juniper                (1.3.6.1.4.1.2636.3.1.14)
  MikroTik               (1.3.6.1.4.1.14988.1.1.3)

Returned fields
---------------
  temperatures  list[SensorReading]
  fans          list[SensorReading]
  power_supplies list[SensorReading]
  voltages      list[SensorReading]
  currents      list[SensorReading]
  sensor_count  int
  health        str  — "ok" | "warning" | "critical"

SensorReading shape
-------------------
  {
    "name":    str,
    "index":   str,
    "type":    str,       # "temperature" | "fan" | "psu" | "voltage" | "current"
    "value":   float | None,
    "unit":    str | None,  # "celsius" | "rpm" | "watts" | "volts" | "amperes"
    "status":  str,       # "ok" | "warning" | "critical" | "notPresent" | "unknown"
    "alarm":   bool,
    "source":  str,       # "entity-sensor" | "cisco" | "fortinet" | ...
  }
"""

from __future__ import annotations

from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice

# ---------------------------------------------------------------------------
# ENTITY-SENSOR-MIB columns
# ---------------------------------------------------------------------------
_ENT_PHYS_NAME    = "1.3.6.1.2.1.47.1.1.1.1.7."   # entPhysicalName
_ENT_PHYS_CLASS   = "1.3.6.1.2.1.47.1.1.1.1.5."   # entPhysicalClass
_SENSOR_TYPE      = "1.3.6.1.2.1.99.1.1.1.1."      # entPhySensorType
_SENSOR_SCALE     = "1.3.6.1.2.1.99.1.1.1.2."      # entPhySensorScale
_SENSOR_PRECISION = "1.3.6.1.2.1.99.1.1.1.3."      # entPhySensorPrecision
_SENSOR_VALUE     = "1.3.6.1.2.1.99.1.1.1.4."      # entPhySensorValue
_SENSOR_STATUS    = "1.3.6.1.2.1.99.1.1.1.5."      # entPhySensorOperStatus
_SENSOR_UNITS_STR = "1.3.6.1.2.1.99.1.1.1.6."      # entPhySensorUnitsDisplay

# entPhySensorType codes → (type_label, unit_label)
_SENSOR_TYPE_MAP: dict[str, tuple[str, str]] = {
    "1":  ("other",       ""),
    "2":  ("unknown",     ""),
    "3":  ("voltage",     "V AC"),
    "4":  ("voltage",     "V DC"),
    "5":  ("current",     "A"),
    "6":  ("power",       "W"),
    "7":  ("frequency",   "Hz"),
    "8":  ("temperature", "°C"),
    "9":  ("humidity",    "%RH"),
    "10": ("fan",         "RPM"),
    "11": ("flow",        "cmm"),
    "12": ("state",       "boolean"),
}

# entPhySensorScale codes → multiplier
_SCALE_MAP: dict[str, float] = {
    "1": 1e-24, "2": 1e-21, "3": 1e-18, "4": 1e-15,
    "5": 1e-12, "6": 1e-9,  "7": 1e-6,  "8": 1e-3,
    "9": 1.0,   "10": 1e3,  "11": 1e6,  "12": 1e9,
    "13": 1e12, "14": 1e15, "15": 1e18, "16": 1e21,
    "17": 1e24,
}

# entPhySensorOperStatus codes
_SENSOR_OPER_STATUS: dict[str, str] = {
    "1": "ok", "2": "unavailable", "3": "nonoperational",
}

# ---------------------------------------------------------------------------
# Cisco CISCO-ENVMON-MIB  (for devices without ENTITY-SENSOR-MIB)
# ---------------------------------------------------------------------------
_CISCO_TEMP_VALUE  = "1.3.6.1.4.1.9.9.13.1.3.1.3."  # ciscoEnvMonTemperatureStatusValue
_CISCO_TEMP_STATE  = "1.3.6.1.4.1.9.9.13.1.3.1.6."  # ciscoEnvMonTemperatureState
_CISCO_TEMP_DESC   = "1.3.6.1.4.1.9.9.13.1.3.1.2."  # ciscoEnvMonTemperatureStatusDescr
_CISCO_FAN_STATE   = "1.3.6.1.4.1.9.9.13.1.4.1.3."  # ciscoEnvMonFanState
_CISCO_FAN_DESC    = "1.3.6.1.4.1.9.9.13.1.4.1.2."  # ciscoEnvMonFanStatusDescr
_CISCO_PSU_STATE   = "1.3.6.1.4.1.9.9.13.1.5.1.3."  # ciscoEnvMonSupplyState
_CISCO_PSU_DESC    = "1.3.6.1.4.1.9.9.13.1.5.1.2."  # ciscoEnvMonSupplyStatusDescr
_CISCO_ENV_STATUS_MAP = {
    "1": "normal", "2": "warning", "3": "critical",
    "4": "shutdown", "5": "notPresent", "6": "notFunctioning",
}

# ---------------------------------------------------------------------------
# Fortinet / Huawei / MikroTik env OIDs  (via vendor profile)
# ---------------------------------------------------------------------------


def _is_alarm(status: str) -> bool:
    return status in ("critical", "nonoperational", "alarm", "warning", "abnormal",
                      "failed", "notFunctioning")


class EnvironmentCollector(BaseCollector):
    """
    Collects all environmental sensors.
    Tries ENTITY-SENSOR-MIB first, then falls back to vendor-specific tables.
    """

    name = "environment"

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

        sensors: list[dict[str, Any]] = []

        # ---------------------------------------------------------------
        # 1. ENTITY-SENSOR-MIB  (RFC 3433)
        # ---------------------------------------------------------------
        entity_sensors = self._parse_entity_sensor(raw_flat)
        sensors.extend(entity_sensors)

        # ---------------------------------------------------------------
        # 2. Cisco CISCO-ENVMON-MIB fallback
        # ---------------------------------------------------------------
        if not sensors and vendor == "cisco":
            sensors.extend(self._parse_cisco_envmon(raw_flat))

        # ---------------------------------------------------------------
        # 3. Vendor-specific via OIDRegistry
        # ---------------------------------------------------------------
        if not sensors and oid_registry:
            sensors.extend(
                self._parse_vendor(raw_flat, oid_registry, vendor_profile, vendor)
            )

        if not sensors:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "No environmental sensor data found — tried "
                    "ENTITY-SENSOR-MIB (RFC 3433), CISCO-ENVMON-MIB, "
                    "and vendor profile OIDs"
                ),
                missing=["entPhySensorValue", "ciscoEnvMon", "vendor.environment"],
            )

        # ---------------------------------------------------------------
        # Categorise sensors
        # ---------------------------------------------------------------
        temps   = [s for s in sensors if s["type"] == "temperature"]
        fans    = [s for s in sensors if s["type"] == "fan"]
        psus    = [s for s in sensors if s["type"] in ("psu", "power")]
        voltages = [s for s in sensors if s["type"] == "voltage"]
        currents = [s for s in sensors if s["type"] == "current"]
        others   = [s for s in sensors if s["type"] not in
                    ("temperature", "fan", "psu", "power", "voltage", "current")]

        # Overall health
        alarm_count = sum(1 for s in sensors if s.get("alarm"))
        critical = sum(1 for s in sensors if s.get("status") == "critical")
        if critical:
            health = "critical"
        elif alarm_count:
            health = "warning"
        else:
            health = "ok"

        if alarm_count:
            for s in sensors:
                if s.get("alarm"):
                    self.warn(warnings, f"Sensor alarm: {s['name']} = {s.get('value')} {s.get('unit','')} ({s['status']})")

        return CollectorResponse.ok(
            self.name,
            {
                "temperatures":    temps,
                "fans":            fans,
                "power_supplies":  psus,
                "voltages":        voltages,
                "currents":        currents,
                "other_sensors":   others,
                "sensor_count":    len(sensors),
                "alarm_count":     alarm_count,
                "health":          health,
            },
            missing,
            warnings,
        )

    # ------------------------------------------------------------------
    # ENTITY-SENSOR-MIB parser
    # ------------------------------------------------------------------

    def _parse_entity_sensor(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse entPhySensorTable and cross-reference entPhysicalName."""
        sensors: list[dict[str, Any]] = []

        # Collect sensor indexes from entPhySensorValue
        sensor_indexes: set[str] = set()
        for k in raw:
            if str(k).startswith(_SENSOR_VALUE):
                sensor_indexes.add(str(k)[len(_SENSOR_VALUE):])

        if not sensor_indexes:
            return []

        for idx in sensor_indexes:
            type_code  = str(raw.get(_SENSOR_TYPE + idx, "2")).strip()
            scale_code = str(raw.get(_SENSOR_SCALE + idx, "9")).strip()
            precision  = self.num(raw.get(_SENSOR_PRECISION + idx)) or 0
            raw_val    = self.num(raw.get(_SENSOR_VALUE + idx))
            status_code = str(raw.get(_SENSOR_STATUS + idx, "1")).strip()
            units_str  = self.text(raw.get(_SENSOR_UNITS_STR + idx))
            phys_name  = self.text(raw.get(_ENT_PHYS_NAME + idx)) or f"Sensor-{idx}"

            type_label, unit_label = _SENSOR_TYPE_MAP.get(type_code, ("unknown", ""))
            scale_mult = _SCALE_MAP.get(scale_code, 1.0)

            # Apply scale and precision
            value: float | None = None
            if raw_val is not None:
                value = round(float(raw_val) * scale_mult / (10 ** int(precision)), 3)
                # Sanity check for temperature
                if type_label == "temperature" and not (-60 <= value <= 200):
                    value = None

            status = _SENSOR_OPER_STATUS.get(status_code, "unknown")

            sensors.append({
                "name":   phys_name,
                "index":  idx,
                "type":   type_label,
                "value":  value,
                "unit":   units_str or unit_label or None,
                "status": status,
                "alarm":  _is_alarm(status),
                "source": "entity-sensor",
            })

        return sensors

    # ------------------------------------------------------------------
    # Cisco ENVMON parser
    # ------------------------------------------------------------------

    def _parse_cisco_envmon(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        sensors: list[dict[str, Any]] = []

        # Temperatures
        for k, v in raw.items():
            if str(k).startswith(_CISCO_TEMP_VALUE):
                idx  = str(k)[len(_CISCO_TEMP_VALUE):]
                val  = self.num(v)
                desc = self.text(raw.get(_CISCO_TEMP_DESC + idx)) or f"Temperature-{idx}"
                state_code = str(raw.get(_CISCO_TEMP_STATE + idx, "5")).strip()
                status = _CISCO_ENV_STATUS_MAP.get(state_code, "unknown")
                sensors.append({
                    "name": desc, "index": idx, "type": "temperature",
                    "value": float(val) if val is not None else None,
                    "unit": "°C", "status": status,
                    "alarm": _is_alarm(status), "source": "cisco-envmon",
                })

        # Fans
        for k, v in raw.items():
            if str(k).startswith(_CISCO_FAN_STATE):
                idx  = str(k)[len(_CISCO_FAN_STATE):]
                desc = self.text(raw.get(_CISCO_FAN_DESC + idx)) or f"Fan-{idx}"
                status = _CISCO_ENV_STATUS_MAP.get(str(v).strip(), "unknown")
                sensors.append({
                    "name": desc, "index": idx, "type": "fan",
                    "value": None, "unit": None,
                    "status": status, "alarm": _is_alarm(status), "source": "cisco-envmon",
                })

        # PSUs
        for k, v in raw.items():
            if str(k).startswith(_CISCO_PSU_STATE):
                idx  = str(k)[len(_CISCO_PSU_STATE):]
                desc = self.text(raw.get(_CISCO_PSU_DESC + idx)) or f"PSU-{idx}"
                status = _CISCO_ENV_STATUS_MAP.get(str(v).strip(), "unknown")
                sensors.append({
                    "name": desc, "index": idx, "type": "psu",
                    "value": None, "unit": None,
                    "status": status, "alarm": _is_alarm(status), "source": "cisco-envmon",
                })

        return sensors

    # ------------------------------------------------------------------
    # Generic vendor profile fallback
    # ------------------------------------------------------------------

    def _parse_vendor(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
        vendor: str,
    ) -> list[dict[str, Any]]:
        """Try vendor profile environment OIDs."""
        sensors: list[dict[str, Any]] = []

        def _scan(metric_type: str, sensor_type: str, unit: str) -> None:
            oid_prefix = oid_registry.resolve("environment", f"{metric_type}_table") \
                         or oid_registry.resolve("environment", f"{metric_type}_value")
            if not oid_prefix:
                return
            prefix_dot = oid_prefix.rstrip(".") + "."
            for k, v in raw.items():
                if str(k).startswith(prefix_dot):
                    idx = str(k)[len(prefix_dot):]
                    val = self.num(v)
                    sensors.append({
                        "name":   f"{sensor_type.capitalize()}-{idx}",
                        "index":  idx,
                        "type":   sensor_type,
                        "value":  float(val) if val is not None else None,
                        "unit":   unit,
                        "status": "ok",
                        "alarm":  False,
                        "source": f"vendor:{vendor}",
                    })

        _scan("temp",    "temperature", "°C")
        _scan("fan",     "fan",         "RPM")
        _scan("psu",     "psu",         None)
        _scan("voltage", "voltage",     "V")

        # Scalar temp (MikroTik, etc.)
        temp_oid = oid_registry.resolve("environment", "temp_value")
        if temp_oid and not sensors:
            val = self.num(raw.get(temp_oid) or raw.get(temp_oid + ".0"))
            if val is not None:
                sensors.append({
                    "name": "Temperature", "index": "0", "type": "temperature",
                    "value": float(val) / 10 if float(val) > 200 else float(val),
                    "unit": "°C", "status": "ok", "alarm": False,
                    "source": f"vendor:{vendor}",
                })

        return sensors
