"""
General collector tests — contract compliance, interface, and key behaviours
for: StorageCollector, InterfaceCollector, EnvironmentCollector, VLANCollector,
     LLDPCollector, CDPCollector, RoutingCollector, ARPCollector,
     MACTableCollector, InventoryCollector, TopologyCollector,
     FirewallCollector, WirelessCollector, SystemCollector, HealthCollector.

Each collector is tested for:
  1. Unsupported path returns CollectorResponse.supported=False (never raises)
  2. When given valid synthetic OID data, returns supported=True
  3. Never emits the string "Not Supported" as a data value
"""

import pytest
import sys, os
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.collectors import (
    ARPCollector, CDPCollector, EnvironmentCollector, FirewallCollector,
    HealthCollector, InterfaceCollector, InventoryCollector, LLDPCollector,
    MACTableCollector, MemoryCollector, RoutingCollector, StorageCollector,
    SystemCollector, TopologyCollector, VLANCollector, WirelessCollector,
)
from backend.snmp.collectors.base import CollectorResponse
from backend.snmp.oid_mapper import OIDRegistry, build_registry


def _no_vendor() -> tuple[OIDRegistry, Any]:
    from backend.snmp.oid_mapper import build_registry
    reg = build_registry("generic", walk={})
    return reg, reg.profile


def _cisco_profile() -> tuple[OIDRegistry, Any]:
    from backend.snmp.oid_mapper import build_registry
    reg = build_registry("cisco", walk={})
    return reg, reg.profile


# ---------------------------------------------------------------------------
# Contract: every collector must return CollectorResponse, never raise
# ---------------------------------------------------------------------------

ALL_COLLECTORS = [
    ARPCollector(), CDPCollector(), EnvironmentCollector(), FirewallCollector(),
    HealthCollector(), InterfaceCollector(), InventoryCollector(), LLDPCollector(),
    MACTableCollector(), MemoryCollector(), RoutingCollector(), StorageCollector(),
    SystemCollector(), TopologyCollector(), VLANCollector(), WirelessCollector(),
]


class TestContractCompliance:

    @pytest.mark.parametrize("collector", ALL_COLLECTORS, ids=lambda c: c.name)
    def test_empty_raw_never_raises(self, collector):
        reg, vp = _no_vendor()
        resp = collector.collect({}, reg, vp)
        assert isinstance(resp, CollectorResponse)

    @pytest.mark.parametrize("collector", ALL_COLLECTORS, ids=lambda c: c.name)
    def test_unsupported_has_no_not_supported_string_in_data(self, collector):
        reg, vp = _no_vendor()
        resp = collector.collect({}, reg, vp)
        _assert_no_not_supported_string(resp.data)

    @pytest.mark.parametrize("collector", ALL_COLLECTORS, ids=lambda c: c.name)
    def test_response_has_required_keys(self, collector):
        reg, vp = _no_vendor()
        resp = collector.collect({}, reg, vp)
        d = resp.to_dict()
        assert "collector"  in d
        assert "supported"  in d
        assert "timestamp"  in d
        if resp.supported:
            assert "data"     in d
            assert "missing"  in d
            assert "warnings" in d
        else:
            assert "reason"   in d

    @pytest.mark.parametrize("collector", ALL_COLLECTORS, ids=lambda c: c.name)
    def test_collector_has_name_attribute(self, collector):
        assert isinstance(collector.name, str)
        assert len(collector.name) > 0


def _assert_no_not_supported_string(obj, path="root"):
    """Recursively check that no value in obj is the string 'Not Supported'."""
    if isinstance(obj, str):
        assert obj != "Not Supported", f"'Not Supported' found at {path}"
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_not_supported_string(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_not_supported_string(v, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# StorageCollector
# ---------------------------------------------------------------------------

class TestStorageCollector:

    def test_fixed_disk_row_returned(self):
        raw = {
            "1.3.6.1.2.1.25.2.3.1.2.1": "1.3.6.1.2.1.25.2.1.4",  # fixedDisk
            "1.3.6.1.2.1.25.2.3.1.3.1": "/",
            "1.3.6.1.2.1.25.2.3.1.4.1": "4096",   # 4 KiB units
            "1.3.6.1.2.1.25.2.3.1.5.1": "50000",  # 50000 units total
            "1.3.6.1.2.1.25.2.3.1.6.1": "25000",  # 25000 used
        }
        reg, vp = _no_vendor()
        resp = StorageCollector().collect(raw, reg, vp)
        assert resp.supported is True
        vols = resp.data["volumes"]
        assert len(vols) == 1
        assert vols[0]["filesystem"] == "/"
        assert vols[0]["total_bytes"] == 50000 * 4096
        assert vols[0]["used_bytes"]  == 25000 * 4096
        assert vols[0]["utilization_percent"] == pytest.approx(50.0)

    def test_ram_rows_excluded(self):
        raw = {
            "1.3.6.1.2.1.25.2.3.1.2.1": "1.3.6.1.2.1.25.2.1.2",  # RAM — must be excluded
            "1.3.6.1.2.1.25.2.3.1.4.1": "1024",
            "1.3.6.1.2.1.25.2.3.1.5.1": "8192",
            "1.3.6.1.2.1.25.2.3.1.6.1": "4096",
        }
        reg, vp = _no_vendor()
        resp = StorageCollector().collect(raw, reg, vp)
        assert resp.supported is False  # Only RAM row, no disk volumes

    def test_multiple_volumes(self):
        raw = {}
        for idx, (typ, descr, size, used) in enumerate([
            ("1.3.6.1.2.1.25.2.1.4", "/",      100000, 40000),
            ("1.3.6.1.2.1.25.2.1.4", "/home",   200000, 100000),
        ], start=1):
            raw[f"1.3.6.1.2.1.25.2.3.1.2.{idx}"] = typ
            raw[f"1.3.6.1.2.1.25.2.3.1.3.{idx}"] = descr
            raw[f"1.3.6.1.2.1.25.2.3.1.4.{idx}"] = "1024"
            raw[f"1.3.6.1.2.1.25.2.3.1.5.{idx}"] = str(size)
            raw[f"1.3.6.1.2.1.25.2.3.1.6.{idx}"] = str(used)
        reg, vp = _no_vendor()
        resp = StorageCollector().collect(raw, reg, vp)
        assert resp.data["volume_count"] == 2


# ---------------------------------------------------------------------------
# InterfaceCollector
# ---------------------------------------------------------------------------

class TestInterfaceCollector:

    def _if_raw(self) -> dict:
        return {
            "1.3.6.1.2.1.2.2.1.1.1":  "1",          # ifIndex
            "1.3.6.1.2.1.2.2.1.2.1":  "GigabitEthernet0/0",  # ifDescr
            "1.3.6.1.2.1.2.2.1.5.1":  "1000000000",  # ifSpeed
            "1.3.6.1.2.1.2.2.1.6.1":  "001122334455", # ifPhysAddress
            "1.3.6.1.2.1.2.2.1.7.1":  "1",            # adminStatus = up
            "1.3.6.1.2.1.2.2.1.8.1":  "1",            # operStatus = up
            "1.3.6.1.2.1.2.2.1.10.1": "1000000",      # inOctets
            "1.3.6.1.2.1.2.2.1.16.1": "2000000",      # outOctets
        }

    def test_basic_interface_parsed(self):
        reg, vp = _no_vendor()
        resp = InterfaceCollector().collect(self._if_raw(), reg, vp)
        assert resp.supported is True
        ifaces = resp.data["interfaces"]
        assert len(ifaces) == 1
        iface = ifaces[0]
        assert iface["ifIndex"] == 1
        assert iface["description"] == "GigabitEthernet0/0"
        assert iface["admin_status"] == "up"
        assert iface["oper_status"] == "up"
        assert iface["mac"] == "00:11:22:33:44:55"
        assert iface["speed_label"] == "1 Gbps"

    def test_hc_octets_preferred(self):
        raw = dict(self._if_raw())
        raw["1.3.6.1.2.1.31.1.1.1.6.1"]  = "9999999999"   # ifHCInOctets
        raw["1.3.6.1.2.1.31.1.1.1.10.1"] = "8888888888"   # ifHCOutOctets
        reg, vp = _no_vendor()
        resp = InterfaceCollector().collect(raw, reg, vp)
        iface = resp.data["interfaces"][0]
        assert iface["in_octets"]  == 9999999999
        assert iface["out_octets"] == 8888888888

    def test_up_down_counts(self):
        raw = {}
        for i, status in enumerate(["1", "2", "1"], start=1):
            raw[f"1.3.6.1.2.1.2.2.1.2.{i}"] = f"eth{i}"
            raw[f"1.3.6.1.2.1.2.2.1.8.{i}"] = status
        reg, vp = _no_vendor()
        resp = InterfaceCollector().collect(raw, reg, vp)
        assert resp.data["up_count"]   == 2
        assert resp.data["down_count"] == 1

    def test_alias_from_ifxtable(self):
        raw = dict(self._if_raw())
        raw["1.3.6.1.2.1.31.1.1.1.18.1"] = "uplink-to-core"
        reg, vp = _no_vendor()
        resp = InterfaceCollector().collect(raw, reg, vp)
        assert resp.data["interfaces"][0]["alias"] == "uplink-to-core"


# ---------------------------------------------------------------------------
# VLANCollector
# ---------------------------------------------------------------------------

class TestVLANCollector:

    def test_single_vlan_parsed(self):
        raw = {
            "1.3.6.1.2.1.17.7.1.4.3.1.1.10":  "Management",   # name for vlan 10
            "1.3.6.1.2.1.17.7.1.4.3.1.2.10":  "C0",           # egress bitmap
            "1.3.6.1.2.1.17.7.1.4.3.1.4.10":  "C0",           # untagged bitmap
            "1.3.6.1.2.1.17.7.1.4.3.1.5.10":  "1",            # status = active
        }
        reg, vp = _no_vendor()
        resp = VLANCollector().collect(raw, reg, vp)
        assert resp.supported is True
        vlans = resp.data["vlans"]
        assert len(vlans) == 1
        assert vlans[0]["vlan_id"] == 10
        assert vlans[0]["name"] == "Management"
        assert vlans[0]["status"] == "active"

    def test_multiple_vlans(self):
        raw = {}
        for vid in [1, 10, 20, 100]:
            raw[f"1.3.6.1.2.1.17.7.1.4.3.1.1.{vid}"] = f"VLAN{vid}"
            raw[f"1.3.6.1.2.1.17.7.1.4.3.1.5.{vid}"] = "1"
        reg, vp = _no_vendor()
        resp = VLANCollector().collect(raw, reg, vp)
        assert resp.data["vlan_count"] == 4


# ---------------------------------------------------------------------------
# RoutingCollector
# ---------------------------------------------------------------------------

class TestRoutingCollector:

    def test_route_parsed(self):
        raw = {
            "1.3.6.1.2.1.4.21.1.1.10.0.0.0.0.0.0.0.0.0":   "10.0.0.0",
            "1.3.6.1.2.1.4.21.1.11.10.0.0.0.0.0.0.0.0.0":  "255.0.0.0",
            "1.3.6.1.2.1.4.21.1.4.10.0.0.0.0.0.0.0.0.0":   "192.168.1.1",
            "1.3.6.1.2.1.4.21.1.5.10.0.0.0.0.0.0.0.0.0":   "1",
            "1.3.6.1.2.1.4.21.1.7.10.0.0.0.0.0.0.0.0.0":   "13",   # OSPF
            "1.3.6.1.2.1.4.21.1.3.10.0.0.0.0.0.0.0.0.0":   "10",
        }
        reg, vp = _no_vendor()
        resp = RoutingCollector().collect(raw, reg, vp)
        assert resp.supported is True
        routes = resp.data["routes"]
        assert len(routes) >= 1
        route = routes[0]
        assert route["protocol"] == "ospf"
        assert route["next_hop"] == "192.168.1.1"


# ---------------------------------------------------------------------------
# ARPCollector
# ---------------------------------------------------------------------------

class TestARPCollector:

    def test_arp_entry_parsed(self):
        raw = {
            "1.3.6.1.2.1.4.22.1.2.1.192.168.1.100": "aabbccddeeff",
            "1.3.6.1.2.1.4.22.1.4.1.192.168.1.100": "3",   # dynamic
        }
        reg, vp = _no_vendor()
        resp = ARPCollector().collect(raw, reg, vp)
        assert resp.supported is True
        assert resp.data["entry_count"] == 1
        entry = resp.data["entries"][0]
        assert entry["ip_address"] == "192.168.1.100"
        assert entry["mac"] == "AA:BB:CC:DD:EE:FF"
        assert entry["entry_type"] == "dynamic"


# ---------------------------------------------------------------------------
# LLDPCollector
# ---------------------------------------------------------------------------

class TestLLDPCollector:

    def test_lldp_neighbor_parsed(self):
        raw = {
            "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": "switch02.example.com",   # remSysName
            "1.0.8802.1.1.2.1.4.1.1.5.0.1.1": "001122334455",           # remChassisId
            "1.0.8802.1.1.2.1.4.1.1.7.0.1.1": "GigabitEthernet0/1",    # remPortId
        }
        reg, vp = _no_vendor()
        resp = LLDPCollector().collect(raw, reg, vp)
        assert resp.supported is True
        assert resp.data["neighbor_count"] == 1
        nb = resp.data["neighbors"][0]
        assert nb["remote_sys_name"] == "switch02.example.com"
        assert nb["local_port_num"] == "1"


# ---------------------------------------------------------------------------
# InventoryCollector
# ---------------------------------------------------------------------------

class TestInventoryCollector:

    def test_chassis_detected(self):
        raw = {
            "1.3.6.1.2.1.47.1.1.1.1.5.1":  "3",                       # class = chassis
            "1.3.6.1.2.1.47.1.1.1.1.7.1":  "Chassis",                  # name
            "1.3.6.1.2.1.47.1.1.1.1.11.1": "FTX1234ABCD",              # serial
            "1.3.6.1.2.1.47.1.1.1.1.13.1": "Catalyst 9300",            # model
        }
        reg, vp = _no_vendor()
        resp = InventoryCollector().collect(raw, reg, vp)
        assert resp.supported is True
        assert resp.data["chassis"] is not None
        assert resp.data["chassis"]["serial"] == "FTX1234ABCD"

    def test_fans_and_psus_categorised(self):
        raw = {
            "1.3.6.1.2.1.47.1.1.1.1.5.1": "6",   # powerSupply
            "1.3.6.1.2.1.47.1.1.1.1.5.2": "7",   # fan
            "1.3.6.1.2.1.47.1.1.1.1.7.1": "PSU1",
            "1.3.6.1.2.1.47.1.1.1.1.7.2": "Fan1",
        }
        reg, vp = _no_vendor()
        resp = InventoryCollector().collect(raw, reg, vp)
        assert len(resp.data["power_supplies"]) == 1
        assert len(resp.data["fans"]) == 1


# ---------------------------------------------------------------------------
# CDPCollector — Cisco only
# ---------------------------------------------------------------------------

class TestCDPCollector:

    def test_cdp_unsupported_for_non_cisco(self):
        raw = {"1.3.6.1.2.1.1.1.0": "Juniper EX2300"}
        reg, vp = _no_vendor()
        resp = CDPCollector().collect(raw, reg, vp)
        assert resp.supported is False
        assert "cisco" in resp.reason.lower()

    def test_cdp_neighbor_parsed(self):
        raw = {
            "1.3.6.1.2.1.1.1.0": "Cisco IOS ...",
            "1.3.6.1.4.1.9.9.23.1.2.1.1.6.1.1": "switch02.example.com",
            "1.3.6.1.4.1.9.9.23.1.2.1.1.7.1.1": "GigabitEthernet1/0/1",
        }
        from backend.snmp.oid_mapper import build_registry
        from backend.snmp.normalizer import NormalizationLayer
        device = NormalizationLayer().normalize(raw, vendor="cisco")
        reg, cisco_vp = _cisco_profile()
        resp = CDPCollector().collect(device, reg, cisco_vp)
        assert resp.supported is True
        assert resp.data["neighbor_count"] == 1


# ---------------------------------------------------------------------------
# FirewallCollector
# ---------------------------------------------------------------------------

class TestFirewallCollector:

    def test_non_firewall_vendor_unsupported(self):
        raw = {"1.3.6.1.2.1.1.1.0": "Linux server"}
        reg, vp = _no_vendor()
        resp = FirewallCollector().collect(raw, reg, vp)
        assert resp.supported is False

    def test_fortinet_sessions_parsed(self):
        raw = {
            "1.3.6.1.4.1.12356.101.4.1.8.0": "15000",
            "1.3.6.1.4.1.12356.101.4.1.9.0": "100000",
            "1.3.6.1.4.1.12356.101.4.1.3.0": "42",
        }
        from backend.snmp.oid_mapper import build_registry
        from backend.snmp.normalizer import NormalizationLayer
        device = NormalizationLayer().normalize(raw, vendor="fortinet", device_type="firewall")
        reg    = build_registry("fortinet", walk=raw)
        resp   = FirewallCollector().collect(device, reg, reg.profile)
        assert resp.supported is True
        assert resp.data["sessions_active"] == 15000
        assert resp.data["sessions_max"]    == 100000
        assert resp.data["session_usage_pct"] == pytest.approx(15.0, abs=0.1)


# ---------------------------------------------------------------------------
# HealthCollector
# ---------------------------------------------------------------------------

class TestHealthCollector:

    def test_reachable_device_up(self):
        raw = {"reachable": True}
        reg, vp = _no_vendor()
        resp = HealthCollector().collect(raw, reg, vp)
        assert resp.supported is True
        assert resp.data["status"] == "UP"
        assert resp.data["reachable"] is True

    def test_unreachable_device_down(self):
        raw = {"reachable": False}
        reg, vp = _no_vendor()
        resp = HealthCollector().collect(raw, reg, vp)
        assert resp.data["status"] == "DOWN"
