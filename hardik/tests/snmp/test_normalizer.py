"""
Unit tests for NormalizationLayer and RawDevice.

Validates scalar extraction, unit conversion, and table slicing
from a synthetic raw OID dictionary without any SNMP connection.
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.normalizer import NormalizationLayer, RawDevice, uptime, mac, number


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _system_raw() -> dict:
    """Minimal system group OIDs."""
    return {
        "1.3.6.1.2.1.1.1.0": "Linux server01 5.15.0 #1 SMP x86_64",
        "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.8072.3.2.10",
        "1.3.6.1.2.1.1.3.0": "123456789",   # TimeTicks
        "1.3.6.1.2.1.1.4.0": "admin@example.com",
        "1.3.6.1.2.1.1.5.0": "server01.example.com",
        "1.3.6.1.2.1.1.6.0": "DC1-Rack-A2",
    }


def _ucd_cpu_raw() -> dict:
    return {
        "1.3.6.1.4.1.2021.11.9.0":  "15",   # cpu user
        "1.3.6.1.4.1.2021.11.10.0": "5",    # cpu system
        "1.3.6.1.4.1.2021.11.11.0": "80",   # cpu idle
    }


def _ucd_mem_raw() -> dict:
    return {
        "1.3.6.1.4.1.2021.4.5.0":  "8192000",  # total real KB
        "1.3.6.1.4.1.2021.4.6.0":  "4096000",  # avail real KB
        "1.3.6.1.4.1.2021.4.14.0": "200000",   # buffer KB
        "1.3.6.1.4.1.2021.4.15.0": "512000",   # cached KB
        "1.3.6.1.4.1.2021.4.3.0":  "2048000",  # swap total KB
        "1.3.6.1.4.1.2021.4.4.0":  "2000000",  # swap avail KB
    }


def _hr_cpu_raw() -> dict:
    """Two-core hrProcessorLoad."""
    return {
        "1.3.6.1.2.1.25.3.3.1.2.1": "22",
        "1.3.6.1.2.1.25.3.3.1.2.2": "38",
    }


# ---------------------------------------------------------------------------
# Helper scalars
# ---------------------------------------------------------------------------

class TestScalarHelpers:
    def test_number_int(self):
        assert number(42) == 42
        assert number("42") == 42

    def test_number_float(self):
        assert number("3.14") == 3.14

    def test_number_none_on_garbage(self):
        assert number("N/A") is None
        assert number(None) is None
        assert number("") is None

    def test_uptime_conversion(self):
        ut = uptime(36000)    # 360 seconds
        assert ut["seconds"] == 360.0
        assert "0d" in ut["display"]

    def test_uptime_none(self):
        ut = uptime(None)
        assert ut["seconds"] is None
        assert ut["display"] is None

    def test_mac_normalization(self):
        assert mac("001122334455")     == "00:11:22:33:44:55"
        assert mac("00:11:22:33:44:55") == "00:11:22:33:44:55"
        assert mac("00-11-22-33-44-55") == "00:11:22:33:44:55"
        assert mac("0x001122334455")   == "00:11:22:33:44:55"
        assert mac("short") is None
        assert mac(None) is None


# ---------------------------------------------------------------------------
# NormalizationLayer
# ---------------------------------------------------------------------------

class TestNormalizationLayer:

    def _make(self, raw: dict, vendor: str | None = None) -> RawDevice:
        return NormalizationLayer().normalize(raw, vendor=vendor)

    def test_system_scalars_populated(self):
        raw = _system_raw()
        device = self._make(raw)
        assert device.hostname == "server01.example.com"
        assert "Linux" in device.sys_descr
        assert device.contact == "admin@example.com"
        assert device.location == "DC1-Rack-A2"

    def test_vendor_detected_from_oid(self):
        raw = _system_raw()
        device = self._make(raw)
        assert device.vendor == "linux"

    def test_vendor_override(self):
        raw = _system_raw()
        device = self._make(raw, vendor="cisco")
        assert device.vendor == "cisco"

    def test_uptime_converted(self):
        raw = _system_raw()
        device = self._make(raw)
        assert device.uptime_ticks == 123456789
        assert device.uptime_seconds is not None
        assert device.uptime_seconds > 0
        assert device.uptime_display is not None

    # --- CPU ---

    def test_ucd_cpu_populated(self):
        raw = {**_system_raw(), **_ucd_cpu_raw()}
        device = self._make(raw)
        assert device.cpu_overall == pytest.approx(20.0, abs=0.1)  # 100 - 80
        assert device.cpu_user == 15.0
        assert device.cpu_system == 5.0
        assert device.cpu_idle == 80.0

    def test_hr_processor_cpu_fallback(self):
        raw = {**_system_raw(), **_hr_cpu_raw()}
        device = self._make(raw)
        # Should average the two cores: (22 + 38) / 2 = 30
        assert device.cpu_overall == pytest.approx(30.0, abs=0.1)
        assert "1" in device.cpu_cores
        assert "2" in device.cpu_cores

    def test_cpu_none_when_no_oids(self):
        raw = _system_raw()
        device = self._make(raw)
        assert device.cpu_overall is None

    # --- Memory ---

    def test_ucd_memory_populated(self):
        raw = {**_system_raw(), **_ucd_mem_raw()}
        device = self._make(raw)
        assert device.mem_total == 8192000 * 1024
        assert device.mem_free  == 4096000 * 1024
        assert device.mem_used  == (8192000 - 4096000) * 1024
        assert device.mem_cached  == 512000 * 1024
        assert device.mem_buffers == 200000 * 1024
        assert device.mem_swap_total == 2048000 * 1024

    def test_memory_none_when_no_oids(self):
        raw = _system_raw()
        device = self._make(raw)
        assert device.mem_total is None

    # --- Table slicing ---

    def test_if_table_sliced(self):
        raw = {
            **_system_raw(),
            "1.3.6.1.2.1.2.2.1.2.1": "eth0",
            "1.3.6.1.2.1.2.2.1.8.1": "1",
        }
        device = self._make(raw)
        assert len(device.raw_interfaces) == 2
        assert any("eth0" in str(v) for v in device.raw_interfaces.values())

    def test_raw_dict_attached(self):
        raw = _system_raw()
        device = self._make(raw)
        assert device.raw is raw
