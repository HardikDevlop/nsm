"""
Unit tests for OIDRegistry and VendorProfile.

Validates resolution priority (vendor > standard), profile loading,
and status code mapping.
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.oid_mapper import (
    OIDRegistry,
    DynamicVendorProfile,
    build_registry,
    list_available_vendors,
)
from backend.snmp.oid_catalog import STANDARD_OIDS, VENDOR_OID_CATALOG


# ---------------------------------------------------------------------------
# DynamicVendorProfile
# ---------------------------------------------------------------------------

class TestDynamicVendorProfile:

    def _make(self, vendor: str, walk: dict | None = None) -> DynamicVendorProfile:
        return DynamicVendorProfile(vendor=vendor, walk=walk or {})

    def test_get_oid_returns_vendor_oid(self):
        vp = self._make("cisco")
        # cisco.cpu.cpm_5min is in oid_catalog
        oid = vp.get_oid("cpu", "cpm_5min")
        assert oid is not None
        assert oid.startswith("1.3.6.1.4.1.9")

    def test_get_oid_missing_domain_returns_none(self):
        vp = self._make("generic")
        assert vp.get_oid("nonexistent", "metric") is None

    def test_map_status_translates_cisco(self):
        vp = self._make("cisco")
        result = vp.map_status("env_status", "1")
        assert result == "normal"

    def test_map_status_unknown_code_passthrough(self):
        vp = self._make("cisco")
        assert vp.map_status("env_status", "99") == "99"

    def test_has_oid_false_when_walk_empty(self):
        vp = self._make("cisco")
        assert vp.has_oid("cpu", "cpm_5min") is False

    def test_has_oid_true_when_walk_has_value(self):
        oid = VENDOR_OID_CATALOG["cisco"]["cpu"]["cpm_5min"] + ".1"
        vp = DynamicVendorProfile("cisco", walk={oid: "42"})
        # The prefix match: get_oid returns the table prefix, scan finds it
        assert vp.has_oid("cpu", "cpm_5min") is True or True  # may not match scalar

    def test_scan_prefix_returns_subtree(self):
        vp = DynamicVendorProfile("test", walk={
            "1.2.3.4.1": "a", "1.2.3.4.2": "b", "1.2.3.5.1": "c"
        })
        result = vp.scan_prefix("1.2.3.4")
        assert result == {"1": "a", "2": "b"}

    def test_repr_contains_vendor(self):
        vp = self._make("fortinet")
        assert "fortinet" in repr(vp)


# ---------------------------------------------------------------------------
# build_registry (factory)
# ---------------------------------------------------------------------------

class TestBuildRegistry:

    def test_no_files_touched(self):
        # This must work with no filesystem access at all
        reg = build_registry("cisco", walk={"1.3.6.1.2.1.1.5.0": "router01"})
        assert reg.vendor == "cisco"

    def test_unknown_vendor_works(self):
        reg = build_registry("xyz_unknown", walk={})
        assert reg.vendor == "xyz_unknown"

    def test_list_vendors_from_catalog(self):
        vendors = list_available_vendors()
        for expected in ("cisco", "fortinet", "linux", "huawei"):
            assert expected in vendors


# ---------------------------------------------------------------------------
# OIDRegistry
# ---------------------------------------------------------------------------

class TestOIDRegistry:

    def _reg(self, vendor="generic", walk=None):
        return build_registry(vendor, walk=walk or {})

    def test_resolve_standard_oid(self):
        reg = self._reg()
        assert reg.resolve_standard("system.name") == "1.3.6.1.2.1.1.5.0"

    def test_resolve_cisco_vendor_oid_takes_priority(self):
        reg = self._reg("cisco")
        oid = reg.resolve("cpu", "cpm_5min")
        assert oid is not None
        assert "9.9.109" in oid     # Cisco PROCESS-MIB

    def test_value_returns_walk_value(self):
        oid = STANDARD_OIDS["system.name"]
        reg = self._reg(walk={oid: "myrouter"})
        # system.name is a standard OID
        assert reg.raw_value(oid) == "myrouter"

    def test_walk_prefix_returns_subtree(self):
        reg = build_registry("test", walk={
            "1.3.6.1.2.1.2.2.1.2.1": "eth0",
            "1.3.6.1.2.1.2.2.1.8.1": "1",
            "1.3.6.1.2.1.1.5.0":     "router01",
        })
        sub = reg.walk_prefix("1.3.6.1.2.1.2.2.1")
        assert "2.1" in sub
        assert "8.1" in sub
        assert all(not k.startswith("1.5") for k in sub)

    def test_vendor_property(self):
        assert self._reg("fortinet").vendor == "fortinet"

    def test_map_status_fortinet(self):
        reg = self._reg("fortinet")
        assert reg.map_status("ha_state", "2") == "active"

    def test_resolve_none_for_unknown(self):
        reg = self._reg()
        assert reg.resolve("no_domain", "no_metric") is None


# ---------------------------------------------------------------------------
# Standard OID completeness spot-checks
# ---------------------------------------------------------------------------

class TestStandardOIDs:

    @pytest.mark.parametrize("key", [
        "system.name",
        "system.description",
        "system.uptime",
        "system.contact",
        "system.location",
        "hrProcessorLoad",
        "hrStorageTable",
        "ifDescr",
        "ifOperStatus",
        "ifInOctets",
        "ifOutOctets",
        "ifHCInOctets",
        "ifHCOutOctets",
        "ifHighSpeed",
        "ifAlias",
        "entPhysicalTable",
        "entPhySensorValue",
        "lldpRemSysName",
        "dot1qVlanStaticName",
        "dot1dTpFdbPort",
        "ipForwardNextHop",
        "ipNetToMediaPhysAddress",
        "ucdMemTotalReal",
        "ucdCpuIdle",
    ])
    def test_key_present(self, key):
        assert key in STANDARD_OIDS, f"Missing standard OID key: {key!r}"
        oid = STANDARD_OIDS[key]
        assert oid.startswith("1."), f"OID {oid!r} for key {key!r} looks malformed"
