"""
CPU Collector — multi-vendor CPU utilization.

Resolution order (highest priority first)
------------------------------------------
1.  Vendor OID  (from loaded vendor profile, e.g. Cisco cpmCPUTotal5min)
2.  UCD-SNMP    (Linux net-snmp cpuIdle → 100 - idle)
3.  HOST-RESOURCES-MIB hrProcessorLoad table (average of all cores)

Returned fields
---------------
    overall_percent   float | None   – scalar 0–100
    average_percent   float | None   – same as overall (alias)
    per_core          list[CoreStat] – per-processor-index utilization
    highest_core      CoreStat | None
    lowest_core       CoreStat | None
    core_count        int
    display           str            – "42.1%"
    load_avg          dict | None    – {1min, 5min, 15min} for Linux only
    timestamp         str            – ISO-8601 UTC (from CollectorResponse)

CoreStat shape  {"index": str, "percent": float}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import BaseCollector, CollectorResponse
from ..normalizer import RawDevice


@dataclass
class CoreStat:
    index: str
    percent: float

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "percent": self.percent}


class CPUCollector(BaseCollector):
    """
    Enterprise CPU collector.
    Supports: HOST-RESOURCES-MIB, UCD-SNMP, Cisco, Fortinet,
              Huawei, Juniper, Palo Alto, Linux, Windows, MikroTik.
    """

    name = "cpu"

    # OID roots used for per-core discovery
    _HR_PROCESSOR_PREFIX = "1.3.6.1.2.1.25.3.3.1.2."   # hrProcessorLoad.<index>

    # UCD-SNMP scalars
    _UCD_IDLE   = "1.3.6.1.4.1.2021.11.11.0"
    _UCD_USER   = "1.3.6.1.4.1.2021.11.9.0"
    _UCD_SYS    = "1.3.6.1.4.1.2021.11.10.0"
    _UCD_LOAD1  = "1.3.6.1.4.1.2021.10.1.5.1"
    _UCD_LOAD5  = "1.3.6.1.4.1.2021.10.1.5.2"
    _UCD_LOAD15 = "1.3.6.1.4.1.2021.10.1.5.3"

    def collect(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        vendor_profile: Any,
    ) -> CollectorResponse:

        missing:  list[str] = []
        warnings: list[str] = []

        # Unpack the RawDevice if normalizer was already run
        if isinstance(raw, RawDevice):
            device = raw
            raw_flat = device.raw
        else:
            from ..normalizer import NormalizationLayer  # noqa: PLC0415
            device = NormalizationLayer().normalize(raw)
            raw_flat = raw

        overall:   float | None = None
        per_core:  list[CoreStat] = []
        cpu_user:   float | None = None
        cpu_system: float | None = None
        cpu_idle:   float | None = None
        load_avg:   dict[str, Any] | None = None
        source:     str = "none"

        # ---------------------------------------------------------------
        # 1. Vendor-specific OID (highest priority)
        # ---------------------------------------------------------------
        if oid_registry:
            overall, per_core, source = self._try_vendor(
                raw_flat, oid_registry, warnings
            )

        # ---------------------------------------------------------------
        # 2. UCD-SNMP (Linux / net-snmp)  — idle-based calculation
        # ---------------------------------------------------------------
        if overall is None:
            overall, cpu_user, cpu_system, cpu_idle, load_avg = self._try_ucd(
                raw_flat, warnings
            )
            if overall is not None:
                source = "ucd-snmp"

        # ---------------------------------------------------------------
        # 3. HOST-RESOURCES-MIB hrProcessorLoad table
        # ---------------------------------------------------------------
        if overall is None:
            per_core = self._try_hr_processor(raw_flat, warnings)
            if per_core:
                overall = round(sum(c.percent for c in per_core) / len(per_core), 2)
                source = "hr-processor"

        # ---------------------------------------------------------------
        # 4. Pre-normalised value from RawDevice (normalizer already ran)
        # ---------------------------------------------------------------
        if overall is None and device.cpu_overall is not None:
            overall = device.cpu_overall
            source = "normalizer"
            if device.cpu_cores:
                per_core = [
                    CoreStat(idx, pct)
                    for idx, pct in device.cpu_cores.items()
                ]

        # ---------------------------------------------------------------
        # 5. UCD load-average fallback
        #    Some devices (embedded Linux, NVRs, routers running net-snmp)
        #    expose laLoad (1.3.6.1.4.1.2021.10.1.x) but NOT the
        #    cpuIdle/cpuUser scalars (1.3.6.1.4.1.2021.11.x).
        #    Use 1-min load avg scaled to a rough % (clamped 0–100).
        # ---------------------------------------------------------------
        if overall is None:
            overall, load_avg = self._try_ucd_loadavg(raw_flat, warnings)
            if overall is not None:
                source = "ucd-loadavg"

        # ---------------------------------------------------------------
        # Nothing found
        # ---------------------------------------------------------------
        if overall is None:
            return CollectorResponse.unsupported(
                self.name,
                reason=(
                    "No CPU OID responded: tried vendor profile OIDs, "
                    "UCD-SNMP (1.3.6.1.4.1.2021.11.x), "
                    "hrProcessorLoad (1.3.6.1.2.1.25.3.3.1.2), "
                    "and UCD load-average (1.3.6.1.4.1.2021.10.1.5.x)"
                ),
                missing=["cpu.overall", "hrProcessorLoad", "ucdCpuIdle", "ucdLoadAvg1"],
            )

        # ---------------------------------------------------------------
        # Build per-core stats from RawDevice if not already populated
        # ---------------------------------------------------------------
        if not per_core and device.cpu_cores:
            per_core = [
                CoreStat(idx, pct)
                for idx, pct in sorted(device.cpu_cores.items())
            ]

        core_count  = len(per_core)
        highest     = max(per_core, key=lambda c: c.percent, default=None)
        lowest      = min(per_core, key=lambda c: c.percent, default=None)
        average     = (
            round(sum(c.percent for c in per_core) / core_count, 2)
            if core_count > 0 else overall
        )

        data: dict[str, Any] = {
            "overall_percent": round(overall, 2),
            "average_percent": round(average, 2) if average is not None else round(overall, 2),
            "per_core":        [c.to_dict() for c in sorted(per_core, key=lambda c: c.index)],
            "core_count":      core_count,
            "highest_core":    highest.to_dict() if highest else None,
            "lowest_core":     lowest.to_dict() if lowest else None,
            "cpu_user":        round(cpu_user, 2) if cpu_user is not None else None,
            "cpu_system":      round(cpu_system, 2) if cpu_system is not None else None,
            "cpu_idle":        round(cpu_idle, 2) if cpu_idle is not None else None,
            "load_avg":        load_avg,
            "display":         f"{round(overall, 1)}%",
            "source":          source,
        }

        return CollectorResponse.ok(self.name, data, missing, warnings)

    # ------------------------------------------------------------------
    # Private — vendor OID strategy
    # ------------------------------------------------------------------

    def _try_vendor(
        self,
        raw: dict[str, Any],
        oid_registry: Any,
        warnings: list[str],
    ) -> tuple[float | None, list[CoreStat], str]:
        """
        Try vendor profile OIDs.
        Returns (overall_percent, per_core_list, source_label).
        """
        per_core: list[CoreStat] = []

        # Single overall scalar
        for metric in ("overall", "overall_5min", "overall_1min",
                        "mgmt_cpu", "data_cpu", "routing_engine",
                        "nexus_overall"):
            oid = oid_registry.resolve("cpu", metric)
            if not oid:
                continue
            val = self.num(self._gv(raw, oid))
            if val is not None and 0 <= val <= 100:
                return float(val), [], f"vendor:{metric}"

        # Per-CPU table (cisco cpmCPUTotal5min, huawei cpu_table, etc.)
        for metric in ("per_cpu_5min", "per_cpu_1min", "per_cpu_5s",
                        "cpu_table", "dp_cpu_table"):
            oid_prefix = oid_registry.resolve("cpu", metric)
            if not oid_prefix:
                continue
            prefix_dot = oid_prefix.rstrip(".") + "."
            vals = {
                k[len(prefix_dot):]: self.num(v)
                for k, v in raw.items()
                if k.startswith(prefix_dot) and self.num(v) is not None
            }
            if vals:
                per_core = [
                    CoreStat(idx, float(pct))          # type: ignore[arg-type]
                    for idx, pct in vals.items()
                    if pct is not None and 0 <= float(pct) <= 100
                ]
                if per_core:
                    overall = round(
                        sum(c.percent for c in per_core) / len(per_core), 2
                    )
                    return overall, per_core, f"vendor:{metric}_table"

        return None, [], "none"

    # ------------------------------------------------------------------
    # Private — UCD-SNMP strategy
    # ------------------------------------------------------------------

    def _try_ucd(
        self,
        raw: dict[str, Any],
        warnings: list[str],
    ) -> tuple[float | None, float | None, float | None, float | None,
               dict[str, Any] | None]:
        """
        Return (overall, user, system, idle, load_avg) from UCD-SNMP OIDs.
        """
        idle = self.num(self._gv(raw, self._UCD_IDLE))
        if idle is None:
            return None, None, None, None, None

        user   = self.num(self._gv(raw, self._UCD_USER))
        system = self.num(self._gv(raw, self._UCD_SYS))
        overall = round(100.0 - float(idle), 2)
        overall = max(0.0, min(100.0, overall))   # clamp to [0, 100]

        load_avg: dict[str, Any] | None = None
        l1 = self.num(self._gv(raw, self._UCD_LOAD1))
        l5 = self.num(self._gv(raw, self._UCD_LOAD5))
        l15 = self.num(self._gv(raw, self._UCD_LOAD15))
        if any(x is not None for x in (l1, l5, l15)):
            load_avg = {
                "1min":  round(float(l1) / 100, 2) if l1 is not None else None,
                "5min":  round(float(l5) / 100, 2) if l5 is not None else None,
                "15min": round(float(l15) / 100, 2) if l15 is not None else None,
            }

        return overall, (float(user) if user is not None else None), \
               (float(system) if system is not None else None), \
               float(idle), load_avg

    # ------------------------------------------------------------------
    # Private — UCD load-average only (no cpu-idle available)
    # ------------------------------------------------------------------

    def _try_ucd_loadavg(
        self,
        raw: dict[str, Any],
        warnings: list[str],
    ) -> tuple[float | None, dict[str, Any] | None]:
        """
        Return (overall_pct, load_avg) from UCD laLoad table only.
        Used for devices that publish load averages but not cpu-idle scalars.
        overall_pct is derived from the 1-min load average:
          clamp(load_1min * 100 / max(1, core_count), 0, 100)
        load_avg values are the raw float strings from the table.
        """
        # laLoadFloat (column 3 of laTable) — floating point load averages
        # 1.3.6.1.4.1.2021.10.1.3.{1,2,3}
        _LA_FLOAT_PREFIX = "1.3.6.1.4.1.2021.10.1.3."
        # laLoad (column 5) — integer percent scaled ×100 (e.g. 5 = 0.05)
        _LA_INT_PREFIX   = "1.3.6.1.4.1.2021.10.1.5."

        floats: dict[int, float] = {}
        ints:   dict[int, float] = {}

        for k, v in raw.items():
            sk = str(k)
            if sk.startswith(_LA_FLOAT_PREFIX):
                idx = sk[len(_LA_FLOAT_PREFIX):]
                val = self.num(v)
                if val is not None and idx.isdigit():
                    floats[int(idx)] = float(val)
            elif sk.startswith(_LA_INT_PREFIX):
                idx = sk[len(_LA_INT_PREFIX):]
                val = self.num(v)
                if val is not None and idx.isdigit():
                    ints[int(idx)] = float(val)

        if not floats and not ints:
            return None, None

        # Prefer float values (more precise)
        src = floats if floats else {}
        # Integer column stores load*100 as integer percentage points
        # e.g. value "5" means 0.05 load → convert to real float
        if not src:
            src = {k: v / 100.0 for k, v in ints.items()}

        l1  = src.get(1)
        l5  = src.get(2)
        l15 = src.get(3)

        if l1 is None:
            return None, None

        # Estimate % — load avg of 1.0 on a single-core ≈ 100% busy
        # We don't know core count; cap at 100
        overall = min(round(l1 * 100.0, 2), 100.0)

        load_avg = {
            "1min":  round(l1,  3) if l1  is not None else None,
            "5min":  round(l5,  3) if l5  is not None else None,
            "15min": round(l15, 3) if l15 is not None else None,
        }
        return overall, load_avg

    # ------------------------------------------------------------------
    # Private — hrProcessorLoad strategy
    # ------------------------------------------------------------------

    def _try_hr_processor(
        self,
        raw: dict[str, Any],
        warnings: list[str],
    ) -> list[CoreStat]:
        """Scan raw for hrProcessorLoad entries and return per-core list."""
        prefix = self._HR_PROCESSOR_PREFIX
        cores: list[CoreStat] = []
        for k, v in raw.items():
            if not str(k).startswith(prefix):
                continue
            idx = k[len(prefix):]
            val = self.num(v)
            if val is not None and 0 <= float(val) <= 100:
                cores.append(CoreStat(idx, float(val)))
        return sorted(cores, key=lambda c: c.index)

    # ------------------------------------------------------------------
    # Static helper
    # ------------------------------------------------------------------

    @staticmethod
    def _gv(raw: dict[str, Any], oid: str) -> Any:
        """Get value by OID with .0 fallback."""
        v = raw.get(oid)
        if v is None and not oid.endswith(".0"):
            v = raw.get(oid + ".0")
        return v
