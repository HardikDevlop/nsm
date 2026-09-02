import asyncio
import time

import pytest

from backend.snmp import client as client_module
from backend.snmp.client import SNMPClient, _run_in_thread
from backend.snmp.collector import SNMPService
from backend.snmp.credentials import SNMPCredentials


class _EmptyAgent:
    def __init__(self, credentials):
        self.credentials = credentials
        self.get_calls = []
        self.walk_calls = []

    def get(self, host, oids):
        self.get_calls.append((host, tuple(oids)))
        return {
            "1.3.6.1.2.1.1.1.0": "test device",
            "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9",
            "1.3.6.1.2.1.1.5.0": "test-device",
        }

    def walk(self, host, root):
        self.walk_calls.append((host, root))
        return {}


@pytest.mark.parametrize(
    "credentials",
    [
        SNMPCredentials(version="v2c", community="public"),
        SNMPCredentials(version="v3", username="monitor", auth_protocol="SHA", auth_password="auth"),
    ],
)
def test_snmp_credentials_and_retry_timeout_configuration(credentials):
    client = SNMPClient(credentials, timeout=0.25, retries=3, operation_timeout=1.0)
    assert client.credentials is credentials
    assert client.timeout == 0.25
    assert client.retries == 3
    assert client.operation_timeout == 1.0


def test_snmp_v2c_and_v3_auth_objects_are_constructed_without_network():
    v2c = SNMPClient(SNMPCredentials(version="v2c", community="public"))
    v3 = SNMPClient(SNMPCredentials(version="v3", username="monitor", auth_protocol="SHA", auth_password="auth"))
    assert v2c._make_auth().__class__.__name__ == "CommunityData"
    assert v3._make_auth().__class__.__name__ == "UsmUserData"


def test_snmp_operation_timeout_is_clear_and_bounded():
    async def slow_operation():
        await asyncio.sleep(0.2)

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="SNMP operation timed out"):
        _run_in_thread(slow_operation(), 0.03)
    assert time.monotonic() - started < 0.2


@pytest.mark.parametrize(
    "domain",
    ["cpu", "memory", "storage", "interfaces", "vlan", "lldp", "routing", "arp", "mac_table"],
)
def test_all_snmp_domains_use_real_domain_dispatch_without_network(monkeypatch, domain):
    agents = []

    def make_agent(credentials, timeout=None, retries=None, operation_timeout=None):
        agent = _EmptyAgent(credentials)
        agents.append(agent)
        return agent

    monkeypatch.setattr("backend.snmp.collector.SNMPClient", make_agent)
    service = SNMPService(SNMPCredentials(version="v2c", community="public"))

    result = service.collect_domain("192.0.2.10", domain)

    assert result["collector"] == domain
    assert result["supported"] is False
    assert agents[0].get_calls


def test_unsupported_domain_returns_stable_unsupported_response():
    service = SNMPService(SNMPCredentials(version="v2c", community="public"))
    result = service.collect_domain("192.0.2.10", "not-a-domain")
    assert result == {"supported": False, "reason": "Unknown domain: 'not-a-domain'"}


def test_full_poll_runs_full_collection_orchestration_without_network(monkeypatch):
    agents = []

    def make_agent(credentials, timeout=None, retries=None, operation_timeout=None):
        agent = _EmptyAgent(credentials)
        agents.append(agent)
        return agent

    monkeypatch.setattr("backend.snmp.collector.SNMPClient", make_agent)
    service = SNMPService(SNMPCredentials(version="v3", username="monitor"))

    result = service.collect("192.0.2.10")

    assert result["reachable"] is True
    assert result["snmp_version"] == "v3"
    assert "system" in result["collectors"]
    assert "interfaces" in result["collectors"]
    assert result["unsupported"]
    assert len(agents[0].walk_calls) > 1
