"""
Unit tests for VendorDetector.

Tests vendor identification via sysObjectID prefix and sysDescr regex patterns.
No network access required — all inputs are mocked strings.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.vendor_detector import VendorDetector


@pytest.fixture()
def detector() -> VendorDetector:
    return VendorDetector()


# ---------------------------------------------------------------------------
# sysObjectID-based detection
# ---------------------------------------------------------------------------

class TestSysObjectIDDetection:
    """Vendor detection from sysObjectID prefix matches."""

    @pytest.mark.parametrize("oid, expected", [
        ("1.3.6.1.4.1.9.1.208",          "cisco"),
        ("1.3.6.1.4.1.9.9.109",          "cisco"),
        ("1.3.6.1.4.1.12356.101.1",       "fortinet"),
        ("1.3.6.1.4.1.2011.5.25.31",      "huawei"),
        ("1.3.6.1.4.1.2636.3.1.13",       "juniper"),
        ("1.3.6.1.4.1.25461.2.1.2.1",     "paloalto"),
        ("1.3.6.1.4.1.14988.1",           "mikrotik"),
        ("1.3.6.1.4.1.6876.1",            "vmware"),
        ("1.3.6.1.4.1.2604.5",            "sophos"),
        ("1.3.6.1.4.1.311.1.1.3",         "windows"),
        ("1.3.6.1.4.1.8072.3.2.10",       "linux"),
    ])
    def test_sysoid_match(self, detector, oid, expected):
        assert detector.detect(sys_object_id=oid) == expected

    def test_unknown_oid_returns_generic(self, detector):
        result = detector.detect(sys_object_id="1.3.6.1.4.1.99999.1.2.3")
        assert result == "generic"

    def test_empty_oid_falls_through_to_generic(self, detector):
        result = detector.detect(sys_object_id="")
        assert result == "generic"


# ---------------------------------------------------------------------------
# sysDescr-based detection
# ---------------------------------------------------------------------------

class TestSysDescrDetection:
    """Vendor detection from sysDescr string patterns."""

    @pytest.mark.parametrize("descr, expected", [
        ("Cisco IOS Software, Version 15.6(3)M",     "cisco"),
        ("Cisco NX-OS(tm) n9000, Software (n9000-dk9)", "cisco"),
        ("FortiGate-60F v7.0.6",                     "fortinet"),
        ("Fortinet FortiOS 7.2.0",                   "fortinet"),
        ("Huawei Versatile Routing Platform Software", "huawei"),
        ("Juniper Networks, Inc. ex2300-24t",         "juniper"),
        ("Junos Space 20.3R1",                       "juniper"),
        ("Palo Alto Networks PAN-OS 10.1.3",          "paloalto"),
        ("MikroTik RouterOS 6.49.6",                  "mikrotik"),
        ("VMware ESXi 7.0.3",                         "vmware"),
        ("Sophos XG 210 SFOS 18.5",                   "sophos"),
        ("Windows Server 2019 Version 10.0",          "windows"),
        ("Linux raspberrypi 5.15.0-1023-raspi",       "linux"),
        ("Ubuntu 22.04.1 LTS",                        "linux"),
        ("Net-SNMP version 5.9.1",                    "linux"),
    ])
    def test_descr_match(self, detector, descr, expected):
        assert detector.detect(sys_descr=descr) == expected

    def test_completely_unknown_descr(self, detector):
        result = detector.detect(sys_descr="ACME Superswitch ProXL v1.0")
        assert result == "generic"

    def test_none_inputs_returns_generic(self, detector):
        assert detector.detect() == "generic"
        assert detector.detect(sys_object_id=None, sys_descr=None) == "generic"


# ---------------------------------------------------------------------------
# OID takes priority over sysDescr
# ---------------------------------------------------------------------------

class TestPriorityOrder:
    """sysObjectID must win over sysDescr when both are present."""

    def test_oid_overrides_descr(self, detector):
        # OID says Cisco, but description says MikroTik
        result = detector.detect(
            sys_object_id="1.3.6.1.4.1.9.1.208",
            sys_descr="MikroTik RouterOS 6.49",
        )
        assert result == "cisco"

    def test_fallback_to_descr_when_oid_unknown(self, detector):
        result = detector.detect(
            sys_object_id="1.3.6.1.4.1.99999.1",
            sys_descr="Junos Space Platform",
        )
        assert result == "juniper"


# ---------------------------------------------------------------------------
# Device type detection
# ---------------------------------------------------------------------------

class TestDeviceTypeDetection:
    @pytest.mark.parametrize("descr, expected", [
        ("Cisco IOS Software, Catalyst 3750",       "switch"),
        ("Cisco ASA 5505 Adaptive Security Appliance", "firewall"),
        ("Cisco Aironet 1815i",                     "access_point"),
        ("VMware ESXi 7.0",                         "hypervisor"),
        ("Synology DSM 7.1 NAS",                    "nas"),
        ("Windows Server 2022",                     "server"),
        ("Ubuntu Linux 22.04",                      "server"),
    ])
    def test_device_type(self, detector, descr, expected):
        result = detector.detect_device_type(sys_descr=descr)
        assert result == expected

    def test_full_detect_returns_both(self, detector):
        result = detector.full_detect(
            sys_object_id="1.3.6.1.4.1.12356.101.1",
            sys_descr="FortiGate-100F v7.0.5",
        )
        assert result["vendor"] == "fortinet"
        assert isinstance(result["device_type"], str)
