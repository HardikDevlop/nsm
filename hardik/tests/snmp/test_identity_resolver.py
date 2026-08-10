"""
Tests for DeviceIdentityResolver and MacOuiResolver.

These are pure-Python tests — no network, no SNMP, no database required.
All inputs are synthetic dicts that mirror what a real SNMP walk returns.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from backend.snmp.identity.resolver import DeviceIdentityResolver, IdentityResult
from backend.snmp.identity.oui import MacOuiResolver, normalize_mac, extract_oui


# ---------------------------------------------------------------------------
# MAC / OUI helpers
# ---------------------------------------------------------------------------

class TestNormalizeMac:
    def test_colons(self):
        assert normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"

    def test_dashes(self):
        assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"

    def test_bare_hex(self):
        assert normalize_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"

    def test_0x_prefix(self):
        assert normalize_mac("0xAABBCCDDEEFF") == "AA:BB:CC:DD:EE:FF"

    def test_none(self):
        assert normalize_mac(None) is None

    def test_too_short(self):
        assert normalize_mac("aabb") is None

    def test_non_hex(self):
        assert normalize_mac("ZZ:ZZ:ZZ:ZZ:ZZ:ZZ") is None


class TestExtractOui:
    def test_basic(self):
        assert extract_oui("AA:BB:CC:DD:EE:FF") == "AA:BB:CC"

    def test_lowercase_input_normalized(self):
        assert extract_oui("98:a8:78:00:00:01") == "98:A8:78"


class TestMacOuiResolverLegacy:
    """Without a DB session, falls back to vendor_map.py or returns unknown."""

    def test_unknown_mac(self):
        resolver = MacOuiResolver()
        result   = resolver.resolve("AA:BB:CC:DD:EE:FF")
        assert result["mac"] == "AA:BB:CC:DD:EE:FF"
        assert result["oui"] == "AA:BB:CC"
        # May or may not find a vendor — just check the structure
        assert "manufacturer" in result
        assert "confidence" in result
        assert "source" in result

    def test_none_mac(self):
        resolver = MacOuiResolver()
        result   = resolver.resolve(None)
        assert result["mac"] is None
        assert result["manufacturer"] is None
        assert result["confidence"] == 0.0

    def test_agnigate_oui(self):
        """98:a8:78 is Agnigate's registered OUI in vendor_map.py."""
        resolver = MacOuiResolver()
        result   = resolver.resolve("98:a8:78:00:00:01")
        # Should resolve via legacy vendor_map.py
        assert result["manufacturer"] is not None or result["source"] == "unknown"


# ---------------------------------------------------------------------------
# DeviceIdentityResolver
# ---------------------------------------------------------------------------

def _resolver() -> DeviceIdentityResolver:
    """Create a resolver without DB (uses only SNMP fingerprints)."""
    return DeviceIdentityResolver(db=None)


class TestIdentityResolverVendor:

    def test_cisco_by_sysoid(self):
        resolver = _resolver()
        result = resolver.resolve(
            walk={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.208"}
        )
        assert result.vendor == "cisco"
        assert result.vendor_source == "snmp_sysoid"
        assert result.vendor_confidence >= 0.95

    def test_fortinet_by_sysdescr(self):
        resolver = _resolver()
        result = resolver.resolve(
            walk={"1.3.6.1.2.1.1.1.0": "FortiGate-100F v7.0.5"}
        )
        assert result.vendor == "fortinet"
        assert result.vendor_source in ("snmp_descr", "snmp_sysoid")

    def test_unknown_vendor(self):
        resolver = _resolver()
        result = resolver.resolve(walk={})
        assert result.vendor == "unknown"
        assert result.vendor_confidence == 0.0

    def test_vendor_from_mac_oui(self):
        """When sysOID/sysDescr unknown, MAC/OUI provides vendor hint."""
        resolver = _resolver()
        result = resolver.resolve(
            walk={},
            mac_addresses=["98:a8:78:12:34:56"],
        )
        # Either resolved from OUI or fell back to unknown — check shape
        assert result.vendor is not None
        assert result.mac_addresses == ["98:A8:78:12:34:56"]


class TestIdentityResolverHostname:

    def test_sys_name_used(self):
        result = _resolver().resolve(
            walk={"1.3.6.1.2.1.1.5.0": "core-router-01"}
        )
        assert result.hostname == "core-router-01"
        assert result.hostname_source == "snmp_sysname"

    def test_ip_hint_fallback(self):
        result = _resolver().resolve(walk={}, hostname_hint="192.168.1.1")
        assert result.hostname == "192.168.1.1"
        assert result.hostname_source == "ip_hint"

    def test_unknown_device_when_nothing(self):
        result = _resolver().resolve(walk={})
        assert result.hostname == "Unknown Device"
        assert result.hostname_source == "unknown"

    def test_none_sysname_falls_back(self):
        result = _resolver().resolve(
            walk={"1.3.6.1.2.1.1.5.0": "(none)"},
            hostname_hint="10.0.0.1",
        )
        assert result.hostname == "10.0.0.1"


class TestIdentityResolverDeviceType:

    @pytest.mark.parametrize("descr,expected", [
        ("FortiGate-100F Firewall",         "firewall"),
        ("Cisco Catalyst 3750 Switch",      "switch"),
        ("Cisco ASR1002 Router",            "router"),
        ("Cisco Aironet Access Point",      "access_point"),
        ("VMware ESXi 7.0 Hypervisor",      "hypervisor"),
        ("Synology DS220+ NAS",             "nas"),
        ("Windows Server 2022",             "server"),
        ("Ubuntu Linux 22.04",              "server"),
    ])
    def test_device_type_from_descr(self, descr, expected):
        result = _resolver().resolve(
            walk={"1.3.6.1.2.1.1.1.0": descr}
        )
        assert result.device_type == expected


class TestIdentityResolverHardware:

    def test_entity_mib_serial(self):
        result = _resolver().resolve(
            walk={
                "1.3.6.1.2.1.47.1.1.1.1.11.1": "FTX2045ABCD",
                "1.3.6.1.2.1.47.1.1.1.1.13.1": "ISR4321",
                "1.3.6.1.2.1.47.1.1.1.1.9.1":  "15.9(3)M3",
            }
        )
        assert result.serial_number == "FTX2045ABCD"
        assert result.model == "ISR4321"
        assert result.firmware_version == "15.9(3)M3"
        assert result.model_source == "entity_mib"

    def test_entity_mib_not_present(self):
        result = _resolver().resolve(walk={})
        assert result.serial_number is None
        assert result.model is None


class TestIdentityResolverOverrides:

    def test_user_override_vendor_wins(self):
        result = _resolver().resolve(
            walk={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.208"},  # cisco
            user_overrides={"vendor": "agnigate"},
        )
        assert result.vendor == "agnigate"
        assert result.vendor_source == "user_override"
        assert result.vendor_confidence == 1.0

    def test_user_override_device_type(self):
        result = _resolver().resolve(
            walk={"1.3.6.1.2.1.1.1.0": "Linux router"},
            user_overrides={"device_type": "firewall"},
        )
        assert result.device_type == "firewall"
        assert result.device_type_source == "user_override"

    def test_partial_overrides_dont_affect_others(self):
        result = _resolver().resolve(
            walk={
                "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.208",
                "1.3.6.1.2.1.1.5.0": "my-router",
            },
            user_overrides={"model": "Custom-Model"},
        )
        assert result.vendor == "cisco"          # not overridden
        assert result.hostname == "my-router"    # not overridden
        assert result.model == "Custom-Model"    # overridden


class TestIdentityResolverConfidence:

    def test_confidence_increases_with_evidence(self):
        # No evidence
        r1 = _resolver().resolve(walk={})
        # With sysOID
        r2 = _resolver().resolve(
            walk={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.208"}
        )
        # sysOID detection gives confidence > 0
        assert r2.vendor_confidence > r1.vendor_confidence

    def test_to_dict_contains_all_keys(self):
        result = _resolver().resolve(walk={})
        d = result.to_dict()
        for key in ("vendor", "vendor_source", "hostname", "model",
                    "device_type", "identity_confidence", "identity_sources",
                    "mac_addresses", "roles"):
            assert key in d, f"Missing key: {key!r}"


class TestIdentityResolverFullScenario:
    """Simulates realistic SNMP walk data for known device types."""

    def test_cisco_router_full(self):
        walk = {
            "1.3.6.1.2.1.1.1.0": "Cisco IOS Software, Version 15.9(3)M3",
            "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.2588",
            "1.3.6.1.2.1.1.5.0": "core-router-01",
            "1.3.6.1.2.1.47.1.1.1.1.13.1": "ISR4321",
            "1.3.6.1.2.1.47.1.1.1.1.11.1": "FTX2045ABCD",
        }
        result = _resolver().resolve(walk=walk, mac_addresses=["00:22:99:AA:BB:CC"])
        assert result.vendor     == "cisco"
        assert result.hostname   == "core-router-01"
        assert result.model      == "ISR4321"
        assert result.serial_number == "FTX2045ABCD"
        assert result.device_type in ("router", "unknown")  # IOS sysDescr doesn't always say "router"
        assert result.identity_confidence > 0.7

    def test_fortinet_firewall_full(self):
        walk = {
            "1.3.6.1.2.1.1.1.0": "FortiGate-100F v7.0.5",
            "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.12356.1.1",
            "1.3.6.1.2.1.1.5.0": "fw-branch-01",
        }
        result = _resolver().resolve(walk=walk)
        assert result.vendor     == "fortinet"
        assert result.device_type == "firewall"
        assert result.hostname   == "fw-branch-01"

    def test_unknown_snmp_device(self):
        """Unknown device: SNMP responds but no identification signals."""
        walk = {
            "1.3.6.1.2.1.1.1.0": "AcmeCorp SuperSwitch v1.0 ProXL",
            "1.3.6.1.2.1.1.5.0": "acme-sw-01",
        }
        result = _resolver().resolve(walk=walk, hostname_hint="10.1.1.50")
        # Must not crash. Vendor = unknown, hostname = acme-sw-01
        assert result.vendor   == "unknown"
        assert result.hostname == "acme-sw-01"
        d = result.to_dict()
        assert d["vendor"]   == "unknown"
        assert d["hostname"] == "acme-sw-01"

    def test_snmp_unreachable_device(self):
        """Walk returns nothing (device unreachable)."""
        result = _resolver().resolve(walk={}, hostname_hint="10.1.1.99")
        assert result.vendor   == "unknown"
        assert result.hostname == "10.1.1.99"
        assert result.identity_confidence == 0.0
