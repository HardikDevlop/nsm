"""
Tests for CapabilityDiscoveryService.

Validates that capability detection is purely OID-evidence-based.
No vendor name is used.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from backend.snmp.identity.capability import CapabilityDiscoveryService


def _svc() -> CapabilityDiscoveryService:
    return CapabilityDiscoveryService()


class TestCapabilityProbing:

    def test_empty_walk_all_false(self):
        result = _svc().discover(walk={})
        caps = result["capabilities"]
        for cap, val in caps.items():
            assert val is False, f"Expected {cap} to be False but got {val}"

    def test_interfaces_detected(self):
        walk = {"1.3.6.1.2.1.2.2.1.2.1": "eth0"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["interfaces"] is True

    def test_lldp_detected(self):
        walk = {"1.0.8802.1.1.2.1.4.1.1.9.0.1.1": "switch02"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["lldp"] is True

    def test_cdp_detected(self):
        walk = {"1.3.6.1.4.1.9.9.23.1.2.1.1.6.1.1": "router01"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["cdp"] is True

    def test_cpu_via_hrprocessor(self):
        walk = {"1.3.6.1.2.1.25.3.3.1.2.1": "42"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["cpu"] is True

    def test_cpu_via_ucd(self):
        walk = {"1.3.6.1.4.1.2021.11.11.0": "75"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["cpu"] is True

    def test_memory_via_hr_storage(self):
        walk = {"1.3.6.1.2.1.25.2.3.1.2.1": "1.3.6.1.2.1.25.2.1.2"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["memory"] is True

    def test_routing_detected(self):
        walk = {"1.3.6.1.2.1.4.21.1.1.0.0.0.0": "0.0.0.0"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["routing"] is True

    def test_vlan_detected(self):
        walk = {"1.3.6.1.2.1.17.7.1.4.3.1.1.1": "default"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["vlan"] is True

    def test_firewall_fortinet_detected(self):
        walk = {"1.3.6.1.4.1.12356.101.4.1.8.0": "15000"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["firewall"] is True

    def test_firewall_paloalto_detected(self):
        walk = {"1.3.6.1.4.1.25461.2.1.2.4.3.0": "8000"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["firewall"] is True

    def test_wireless_mikrotik(self):
        walk = {"1.3.6.1.4.1.14988.1.1.1.3.1.4.1": "AgniGate-WiFi"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["wireless"] is True

    def test_topology_from_lldp(self):
        walk = {"1.0.8802.1.1.2.1.4.1.1.9.0.1.1": "switch"}
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["lldp"] is True
        assert caps["topology"] is True  # lldp → topology

    def test_topology_false_without_l2l3_sources(self):
        walk = {"1.3.6.1.2.1.2.2.1.2.1": "eth0"}  # only interfaces
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["topology"] is False


class TestCapabilityCollectorOverride:

    def test_collector_supported_true_overrides_empty_walk(self):
        """If collector says supported=True, capability is True even if walk probe misses."""
        walk  = {}  # empty walk (no OID probe would pass)
        col_results = {"cpu": {"supported": True, "data": {"overall_percent": 42}}}
        caps = _svc().discover(walk=walk, collector_results=col_results)["capabilities"]
        assert caps["cpu"] is True

    def test_collector_supported_false_overrides_walk_probe(self):
        """If collector says supported=False, use that even if OID probe passes."""
        walk = {"1.3.6.1.2.1.25.3.3.1.2.1": "42"}  # hrProcessorLoad present
        col_results = {"cpu": {"supported": False, "reason": "test"}}
        caps = _svc().discover(walk=walk, collector_results=col_results)["capabilities"]
        assert caps["cpu"] is False


class TestCapabilityDbKwargs:

    def test_all_columns_mapped(self):
        svc  = _svc()
        caps = {k: True for k in ["system","cpu","memory","storage","interfaces","environment","inventory","vlan","lldp","cdp","routing","arp","mac_table","firewall","vpn","sdwan","wireless","access_point","topology"]}
        kwargs = svc.to_db_kwargs(caps)
        assert kwargs.get("cap_cpu") is True
        assert kwargs.get("cap_firewall") is True
        assert kwargs.get("cap_wireless") is True

    def test_false_when_missing(self):
        svc    = _svc()
        kwargs = svc.to_db_kwargs({})
        assert kwargs.get("cap_cpu") is False


class TestCapabilityRealism:
    """Full-scenario tests simulating real device walk data."""

    def test_linux_server_profile(self):
        """A Linux server typically has: system, cpu, memory, storage, interfaces, routing, arp."""
        walk = {
            "1.3.6.1.2.1.1.1.0":           "Linux server01 5.15.0",
            "1.3.6.1.4.1.2021.11.11.0":    "75",       # ucdCpuIdle
            "1.3.6.1.4.1.2021.4.5.0":      "8192000",  # ucdMemTotalReal
            "1.3.6.1.2.1.25.2.3.1.2.1":    "1.3.6.1.2.1.25.2.1.4",  # hrStorage
            "1.3.6.1.2.1.2.2.1.2.1":       "eth0",     # ifDescr
            "1.3.6.1.2.1.4.21.1.1.0.0.0.0": "0.0.0.0", # ipForwardDest
            "1.3.6.1.2.1.4.22.1.2.1.192.168.1.1": "aabbccddeeff",  # ARP
        }
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["system"]     is True
        assert caps["cpu"]        is True
        assert caps["memory"]     is True
        assert caps["storage"]    is True
        assert caps["interfaces"] is True
        assert caps["routing"]    is True
        assert caps["arp"]        is True
        assert caps["firewall"]   is False  # no firewall OIDs
        assert caps["wireless"]   is False  # no wireless OIDs

    def test_fortinet_firewall_profile(self):
        walk = {
            "1.3.6.1.2.1.1.1.0":            "FortiGate-100F",
            "1.3.6.1.4.1.12356.101.4.1.3.0": "42",     # fortinet cpu
            "1.3.6.1.4.1.12356.101.4.1.8.0": "15000",  # fortinet sessions
            "1.3.6.1.2.1.2.2.1.2.1":        "port1",   # ifDescr
            "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": "switch01",  # lldp
        }
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["interfaces"] is True
        assert caps["lldp"]       is True
        assert caps["firewall"]   is True
        assert caps["topology"]   is True

    def test_cisco_switch_profile(self):
        walk = {
            "1.3.6.1.2.1.1.1.0":           "Cisco IOS Catalyst 3750",
            "1.3.6.1.2.1.25.3.3.1.2.1":    "32",       # hrProcessorLoad
            "1.3.6.1.2.1.2.2.1.2.1":       "GigabitEthernet0/1",
            "1.3.6.1.2.1.17.7.1.4.3.1.1.10": "Management",  # vlan
            "1.3.6.1.2.1.17.4.3.1.2.0.10.20.30.40.50": "1",  # mac table
            "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": "switch02",  # lldp
            "1.3.6.1.4.1.9.9.23.1.2.1.1.6.1.1": "router01", # cdp
        }
        caps = _svc().discover(walk=walk)["capabilities"]
        assert caps["interfaces"] is True
        assert caps["vlan"]       is True
        assert caps["mac_table"]  is True
        assert caps["lldp"]       is True
        assert caps["cdp"]        is True
        assert caps["topology"]   is True
