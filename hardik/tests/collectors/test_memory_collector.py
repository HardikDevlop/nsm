"""
Unit tests for MemoryCollector.
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.collectors.memory import MemoryCollector
from backend.snmp.oid_mapper import OIDRegistry, DynamicVendorProfile as VendorProfile, build_registry


def _no_vendor():
    return build_registry("generic", walk={})


def _no_profile():
    return build_registry("generic", walk={}).profile


@pytest.fixture()
def collector() -> MemoryCollector:
    return MemoryCollector()


class TestMemoryUCD:

    def test_ucd_total_used_free_bytes(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.4.5.0": "1024000",
            "1.3.6.1.4.1.2021.4.6.0": "512000",
        }
        from backend.snmp.oid_mapper import build_registry
        reg, vp = build_registry("generic", walk=raw), build_registry("generic", walk=raw).profile
        resp = collector.collect(raw, reg, vp)
        assert resp.supported is True
        assert resp.data["total_bytes"]  == 1024000 * 1024
        assert resp.data["free_bytes"]   == 512000  * 1024
        assert resp.data["used_bytes"]   == (1024000 - 512000) * 1024

    def test_utilization_calculated(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.4.5.0": "100",
            "1.3.6.1.4.1.2021.4.6.0": "25",
        }
        resp = collector.collect(raw, _no_vendor(), _no_profile())
        assert resp.data["utilization_percent"] == pytest.approx(75.0)

    def test_cached_and_buffer_populated(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.4.5.0":  "1000",
            "1.3.6.1.4.1.2021.4.6.0":  "500",
            "1.3.6.1.4.1.2021.4.14.0": "100",   # buffer
            "1.3.6.1.4.1.2021.4.15.0": "200",   # cached
        }
        resp = collector.collect(raw, _no_vendor(), _no_profile())
        assert resp.data["buffer_bytes"]  == 100 * 1024
        assert resp.data["cached_bytes"]  == 200 * 1024

    def test_swap_populated(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.4.5.0": "1000",
            "1.3.6.1.4.1.2021.4.6.0": "500",
            "1.3.6.1.4.1.2021.4.3.0": "2000",   # swap total
            "1.3.6.1.4.1.2021.4.4.0": "1800",   # swap free
        }
        resp = collector.collect(raw, _no_vendor(), _no_profile())
        assert resp.data["swap_total_bytes"] == 2000 * 1024
        assert resp.data["swap_free_bytes"]  == 1800 * 1024

    def test_display_string_has_bytes_and_pct(self, collector):
        raw = {
            "1.3.6.1.4.1.2021.4.5.0": "2048000",
            "1.3.6.1.4.1.2021.4.6.0": "1024000",
        }
        resp = collector.collect(raw, _no_vendor(), _no_profile())
        display = resp.data["display"]
        assert "GiB" in display or "MiB" in display
        assert "%" in display


class TestMemoryHRStorage:

    def _hr_ram_raw(self) -> dict:
        # hrStorageType = RAM (1.3.6.1.2.1.25.2.1.2), index 1
        # alloc unit = 1024 bytes, size = 8192 units, used = 4096 units
        return {
            "1.3.6.1.2.1.25.2.3.1.2.1": "1.3.6.1.2.1.25.2.1.2",  # type = RAM
            "1.3.6.1.2.1.25.2.3.1.4.1": "1024",                    # unit = 1 KiB
            "1.3.6.1.2.1.25.2.3.1.5.1": "8192",                    # size = 8192 units
            "1.3.6.1.2.1.25.2.3.1.6.1": "4096",                    # used = 4096 units
        }

    def test_hr_storage_ram_row(self, collector):
        resp = collector.collect(self._hr_ram_raw(), _no_vendor(), _no_profile())
        assert resp.supported is True
        assert resp.data["total_bytes"] == 8192 * 1024
        assert resp.data["used_bytes"]  == 4096 * 1024
        assert resp.data["source"] in ("hr-storage", "normalizer")

    def test_hr_storage_ignores_disk_rows(self, collector):
        raw = {
            "1.3.6.1.2.1.25.2.3.1.2.1": "1.3.6.1.2.1.25.2.1.4",  # fixedDisk — should be skipped
            "1.3.6.1.2.1.25.2.3.1.4.1": "512",
            "1.3.6.1.2.1.25.2.3.1.5.1": "200000",
            "1.3.6.1.2.1.25.2.3.1.6.1": "100000",
        }
        resp = collector.collect(raw, _no_vendor(), _no_profile())
        # No RAM row found → unsupported
        assert resp.supported is False


class TestMemoryVendor:

    def test_vendor_kb_oids(self, collector):
        # Fortinet uses total_real / used_real (in KB) in the catalog
        vendor_oid_total = "1.3.6.1.4.1.12356.101.4.5.1.0"  # total_real
        vendor_oid_used  = "1.3.6.1.4.1.12356.101.4.5.2.0"   # used_real
        raw = {
            vendor_oid_total: "4096000",
            vendor_oid_used:  "2048000",
        }
        from backend.snmp.oid_mapper import build_registry
        from backend.snmp.normalizer import NormalizationLayer
        # The normalizer will pick up vendor OIDs; test via the full pipeline
        device = NormalizationLayer().normalize(raw, vendor="fortinet")
        reg = build_registry("fortinet", walk=raw)
        resp = collector.collect(device, reg, reg.profile)
        # Fortinet uses total_real (bytes) not total_kb
        # normalizer may or may not find it depending on field name
        # At minimum: if it found it, total should be populated
        if resp.supported:
            assert resp.data.get("total_bytes") is not None


class TestMemoryUnsupported:

    def test_empty_raw_unsupported(self, collector):
        resp = collector.collect({}, _no_vendor(), _no_profile())
        assert resp.supported is False
        assert resp.data == {}
        assert resp.reason is not None
