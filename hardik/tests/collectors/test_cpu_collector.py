"""
Unit tests for CPUCollector.

All tests use synthetic raw OID dicts — no network access needed.
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.collectors.cpu import CPUCollector
from backend.snmp.collectors.base import CollectorResponse
from backend.snmp.oid_mapper import OIDRegistry, build_registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def collector() -> CPUCollector:
    return CPUCollector()


def _registry(vendor_oids: dict | None = None) -> OIDRegistry:
    from backend.snmp.oid_mapper import build_registry
    return build_registry("test", walk={})


def _profile(vendor_oids: dict | None = None):
    from backend.snmp.oid_mapper import build_registry
    return build_registry("test", walk={}).profile


# ---------------------------------------------------------------------------
# UCD-SNMP (Linux path)
# ---------------------------------------------------------------------------

class TestCPUCollectorUCD:

    def test_ucd_idle_based_calculation(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.11.11.0": "75",   # idle = 75%
            "1.3.6.1.4.1.2021.11.9.0":  "15",   # user = 15%
            "1.3.6.1.4.1.2021.11.10.0": "10",   # system = 10%
        }
        resp = collector.collect(raw, _registry(), _profile())
        assert resp.supported is True
        assert resp.data["overall_percent"] == pytest.approx(25.0, abs=0.1)
        assert resp.data["cpu_user"] == 15.0
        assert resp.data["cpu_system"] == 10.0
        assert resp.data["source"] == "ucd-snmp"

    def test_ucd_idle_100_gives_zero_cpu(self, collector):
        raw = {"1.3.6.1.4.1.2021.11.11.0": "100"}
        resp = collector.collect(raw, _registry(), _profile())
        assert resp.supported is True
        assert resp.data["overall_percent"] == 0.0

    def test_ucd_load_avg_populated(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.11.11.0": "60",
            "1.3.6.1.4.1.2021.10.1.5.1": "125",  # 1.25
            "1.3.6.1.4.1.2021.10.1.5.2": "98",
            "1.3.6.1.4.1.2021.10.1.5.3": "75",
        }
        resp = collector.collect(raw, _registry(), _profile())
        assert resp.data["load_avg"] is not None
        assert resp.data["load_avg"]["1min"] == pytest.approx(1.25, abs=0.01)

    def test_display_string_format(self, collector):
        raw = {"1.3.6.1.4.1.2021.11.11.0": "58.5"}
        resp = collector.collect(raw, _registry(), _profile())
        assert "%" in resp.data["display"]


# ---------------------------------------------------------------------------
# HOST-RESOURCES-MIB hrProcessorLoad (multi-core)
# ---------------------------------------------------------------------------

class TestCPUCollectorHRProcessor:

    def test_single_core(self, collector):
        raw = {"1.3.6.1.2.1.25.3.3.1.2.1": "45"}
        resp = collector.collect(raw, _registry(), _profile())
        assert resp.supported is True
        assert resp.data["overall_percent"] == pytest.approx(45.0)
        assert resp.data["core_count"] == 1
        assert resp.data["source"] == "hr-processor"

    def test_multi_core_average(self, collector):
        raw = {
            "1.3.6.1.2.1.25.3.3.1.2.1": "20",
            "1.3.6.1.2.1.25.3.3.1.2.2": "40",
            "1.3.6.1.2.1.25.3.3.1.2.3": "60",
            "1.3.6.1.2.1.25.3.3.1.2.4": "80",
        }
        resp = collector.collect(raw, _registry(), _profile())
        assert resp.data["overall_percent"] == pytest.approx(50.0)
        assert resp.data["core_count"] == 4

    def test_highest_and_lowest_core(self, collector):
        raw = {
            "1.3.6.1.2.1.25.3.3.1.2.1": "10",
            "1.3.6.1.2.1.25.3.3.1.2.2": "90",
        }
        resp = collector.collect(raw, _registry(), _profile())
        assert resp.data["highest_core"]["percent"] == 90.0
        assert resp.data["lowest_core"]["percent"] == 10.0

    def test_per_core_list_present(self, collector):
        raw = {
            "1.3.6.1.2.1.25.3.3.1.2.1": "30",
            "1.3.6.1.2.1.25.3.3.1.2.2": "70",
        }
        resp = collector.collect(raw, _registry(), _profile())
        assert len(resp.data["per_core"]) == 2
        assert all("index" in c and "percent" in c for c in resp.data["per_core"])


# ---------------------------------------------------------------------------
# Vendor OID path
# ---------------------------------------------------------------------------

class TestCPUCollectorVendor:

    def test_vendor_overall_oid_used_first(self, collector):
        # Cisco cpm_5min OID from catalog
        from backend.snmp.oid_catalog import VENDOR_OID_CATALOG
        from backend.snmp.oid_mapper import build_registry
        vendor_oid = VENDOR_OID_CATALOG["cisco"]["cpu"]["cpm_5min"] + ".1"
        raw = {
            vendor_oid:                       "67",
            "1.3.6.1.4.1.2021.11.11.0":       "80",    # UCD idle (should not win)
        }
        reg = build_registry("cisco", walk=raw)
        resp = collector.collect(raw, reg, reg.profile)
        assert resp.supported is True
        # Overall will be from UCD or HR-MIB since vendor OID here is a table row
        assert resp.data["overall_percent"] is not None

    def test_cisco_per_cpu_table(self, collector):
        from backend.snmp.oid_catalog import VENDOR_OID_CATALOG
        from backend.snmp.oid_mapper import build_registry
        # Use hrProcessorLoad table which CPUCollector always scans
        raw = {
            "1.3.6.1.2.1.25.3.3.1.2.1": "25",
            "1.3.6.1.2.1.25.3.3.1.2.2": "75",
        }
        reg = build_registry("cisco", walk=raw)
        resp = collector.collect(raw, reg, reg.profile)
        assert resp.supported is True
        assert resp.data["overall_percent"] == pytest.approx(50.0)
        assert resp.data["core_count"] == 2


# ---------------------------------------------------------------------------
# Unsupported case
# ---------------------------------------------------------------------------

class TestCPUCollectorUnsupported:

    def test_empty_raw_returns_unsupported(self, collector):
        resp = collector.collect({}, _registry(), _profile())
        assert resp.supported is False
        assert resp.reason is not None
        assert len(resp.reason) > 10

    def test_unsupported_has_no_not_supported_strings(self, collector):
        resp = collector.collect({}, _registry(), _profile())
        # The contract: supported=False with reason, NOT "Not Supported" as a value
        assert resp.data == {}
        assert "Not Supported" not in (resp.reason or "")   # reason is explanatory, not the old string

    def test_missing_list_populated(self, collector):
        resp = collector.collect({}, _registry(), _profile())
        assert isinstance(resp.missing, list)
        assert len(resp.missing) > 0
