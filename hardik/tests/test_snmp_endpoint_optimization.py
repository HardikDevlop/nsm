from types import SimpleNamespace

import pytest

from backend.api import snmp_device_routes
from backend.services.snmp_poll_guard import poll_guard


class FakeService:
    calls: list[tuple[str, str]] = []

    def __init__(self, credentials):
        self.credentials = credentials

    def collect(self, _host):
        raise AssertionError("domain endpoint must not run full SNMP collection")

    def collect_domain(self, host, domain):
        self.calls.append((host, domain))
        return {
            "collector": domain,
            "supported": True,
            "timestamp": "2026-08-29T10:00:00",
            "missing": [],
            "warnings": [],
            "reason": None,
            "data": {"domain": domain, "rows": [{"id": 1}]},
            "collection_ms": 12.3,
        }


@pytest.mark.parametrize("domain", ["interfaces", "lldp", "routing", "firewall", "wireless"])
def test_domain_live_collect_uses_targeted_path_and_preserves_payload(monkeypatch, domain):
    FakeService.calls = []
    monkeypatch.setattr("backend.snmp.collector.SNMPService", FakeService)

    device = SimpleNamespace(
        id=7,
        ip_address="192.0.2.10",
        hostname="edge-01",
        vendor=SimpleNamespace(vendor_name="Example Vendor"),
        device_type=SimpleNamespace(name="switch"),
    )
    credential = SimpleNamespace(
        snmp_version="v3",
        community_string="public",
        username="monitor",
        auth_protocol=None,
        auth_password=None,
        privacy_protocol=None,
        privacy_password=None,
        security_level="noAuthNoPriv",
    )

    result = snmp_device_routes._live_collect(device, credential, domain=domain)

    assert FakeService.calls == [("192.0.2.10", domain)]
    assert result == {
        "api_version": "2.0",
        "ip": "192.0.2.10",
        "reachable": True,
        "snmp_enabled": True,
        "snmp_version": "v3",
        "vendor": "Example Vendor",
        "device_type": "switch",
        "hostname": "edge-01",
        "collection_ms": 12.3,
        "collectors": {
            domain: {
                "collector": domain,
                "supported": True,
                "timestamp": "2026-08-29T10:00:00",
                "missing": [],
                "warnings": [],
                "reason": None,
                "data": {"domain": domain, "rows": [{"id": 1}]},
                "collection_ms": 12.3,
            }
        },
        "unsupported": [],
    }


def test_live_collect_rejects_duplicate_device_module(monkeypatch):
    monkeypatch.setattr("backend.snmp.collector.SNMPService", FakeService)
    device = SimpleNamespace(
        id=7,
        ip_address="192.0.2.10",
        hostname="edge-01",
        vendor=None,
        device_type=None,
    )
    credential = SimpleNamespace(
        snmp_version="v2c",
        community_string="public",
        username=None,
        auth_protocol=None,
        auth_password=None,
        privacy_protocol=None,
        privacy_password=None,
        security_level=None,
    )
    guard = poll_guard(7, "interfaces", blocking=False)
    assert guard.__enter__() is True
    try:
        with pytest.raises(Exception, match="Poll already in progress"):
            snmp_device_routes._live_collect(device, credential, domain="interfaces")
    finally:
        guard.__exit__(None, None, None)
