from unittest.mock import Mock

import pytest

from backend.snmp.collectors.memory import MemoryCollector
from backend.snmp.memory_resolver import (
    CanonicalMemoryResolution,
    linux_memory_extension_eligible,
    resolve_canonical_linux_memory,
)
from backend.snmp.credentials import SNMPCredentials
from backend.linux_monitoring.metrics import (
    LinuxEffectiveMemoryResult,
    linux_memory_extend_output_oid,
)
from backend.snmp.collectors.base import CollectorResponse
from backend.snmp import collector as collector_module
from backend.snmp.collector import SNMPService


def credentials():
    return SNMPCredentials(
        version="v3",
        username="test-user",
        auth_protocol="sha",
        auth_password="auth-secret",
        security_level="authNoPriv",
    )


def test_linux_eligibility_requires_server_and_linux_identity():
    assert linux_memory_extension_eligible(device_type="server", sys_descr="Linux net-snmp")
    assert not linux_memory_extension_eligible(device_type="server", sys_descr="Cisco IOS")


@pytest.mark.parametrize(
    "device_type, sys_descr",
    [
        ("hypervisor", "Proxmox VE Linux net-snmp"),
        ("nas", "TrueNAS SCALE based on Debian GNU/Linux"),
        ("router", "Embedded Linux router with NET-SNMP"),
        ("switch", "Linux network switch / net-snmp"),
        ("unknown", "GNU/Linux 6.1 with net-snmp agent"),
    ],
)
def test_linux_identity_is_eligible_across_device_classifications(device_type, sys_descr):
    assert linux_memory_extension_eligible(device_type=device_type, sys_descr=sys_descr)


@pytest.mark.parametrize("sys_descr", ["NET-SNMP agent", "LiNuX 5.15", "GNU/Linux Ubuntu"])
def test_linux_identity_matching_is_case_insensitive_and_realistic(sys_descr):
    assert linux_memory_extension_eligible(device_type="unknown", sys_descr=sys_descr)


@pytest.mark.parametrize(
    "device_type, sys_descr",
    [
        ("server", "Windows Server 2022"),
        ("router", "Cisco IOS-XE"),
        ("hypervisor", "VMware ESXi"),
        ("nas", "Synology DSM"),
        ("switch", "Cisco Catalyst switch"),
    ],
)
def test_non_linux_identity_is_ineligible(device_type, sys_descr):
    assert not linux_memory_extension_eligible(device_type=device_type, sys_descr=sys_descr)


def test_valid_extension_has_exact_canonical_arithmetic(monkeypatch):
    oid = linux_memory_extend_output_oid()
    client = Mock()
    client.get.return_value = {
        oid: "version=1 MemTotalKiB=16191484 MemAvailableKiB=10428512"
    }
    monkeypatch.setattr("backend.snmp.memory_resolver.SNMPClient", lambda *a, **k: client)

    result = resolve_canonical_linux_memory(
        "192.168.100.40", credentials(), device_type="server", sys_descr="Linux net-snmp"
    )

    assert result.status == "canonical"
    assert result.data is not None
    assert result.data.total_bytes == 16191484 * 1024
    assert result.data.available_bytes == 10428512 * 1024
    assert result.data.used_bytes == (16191484 - 10428512) * 1024
    assert result.data.utilization_percent == pytest.approx(
        (5762972 / 16191484) * 100
    )


@pytest.mark.parametrize("failure", ["missing", "timeout"])
def test_extension_failure_is_nonfatal(monkeypatch, failure):
    oid = linux_memory_extend_output_oid()
    client = Mock()
    if failure == "timeout":
        client.get.side_effect = TimeoutError("timed out")
    else:
        client.get.return_value = {}
    monkeypatch.setattr("backend.snmp.memory_resolver.SNMPClient", lambda *a, **k: client)

    result = resolve_canonical_linux_memory(
        "192.168.100.40", credentials(), device_type="server", sys_descr="Linux"
    )
    assert result.status == "unavailable"
    assert result.error_code == ("timeout" if failure == "timeout" else "no_such_instance")


def test_non_linux_never_queries_extension(monkeypatch):
    client = Mock()
    monkeypatch.setattr("backend.snmp.memory_resolver.SNMPClient", lambda *a, **k: client)

    result = resolve_canonical_linux_memory(
        "192.0.2.1", credentials(), device_type="router", sys_descr="Cisco IOS"
    )

    assert result.status == "ineligible"
    client.assert_not_called()


@pytest.mark.parametrize(
    "device_type, sys_descr",
    [
        ("server", "Windows Server 2022"),
        ("router", "Cisco IOS-XE"),
        ("hypervisor", "VMware ESXi"),
        ("nas", "Synology DSM"),
    ],
)
def test_non_linux_classifications_do_not_query_extension(monkeypatch, device_type, sys_descr):
    client_factory = Mock()
    monkeypatch.setattr("backend.snmp.memory_resolver.SNMPClient", client_factory)

    result = resolve_canonical_linux_memory(
        "192.0.2.1", credentials(), device_type=device_type, sys_descr=sys_descr
    )

    assert result.status == "ineligible"
    client_factory.assert_not_called()


def test_malformed_extension_is_rejected(monkeypatch):
    oid = linux_memory_extend_output_oid()
    client = Mock()
    client.get.return_value = {oid: "version=1 MemTotalKiB=1000"}
    monkeypatch.setattr("backend.snmp.memory_resolver.SNMPClient", lambda *a, **k: client)

    result = resolve_canonical_linux_memory(
        "192.0.2.1", credentials(), device_type="server", sys_descr="Ubuntu net-snmp"
    )
    assert result.status == "invalid"
    assert result.error_code == "malformed_output"


def test_memory_collector_uses_override_once_and_preserves_fallback():
    canonical = CanonicalMemoryResolution(
        eligible=True,
        status="canonical",
        data=LinuxEffectiveMemoryResult(
            version=1,
            total_kib=1000,
            available_kib=250,
            total_bytes=1000 * 1024,
            available_bytes=250 * 1024,
            used_bytes=750 * 1024,
            utilization_percent=75.0,
        ),
    )
    raw = {
        "1.3.6.1.4.1.2021.4.5.0": "1000",
        "1.3.6.1.4.1.2021.4.6.0": "500",
    }
    result = MemoryCollector().collect(raw, None, None, canonical_memory=canonical)
    assert result.data["used_bytes"] == 750 * 1024
    assert result.data["free_bytes"] == 250 * 1024
    assert result.data["utilization_percent"] == 75.0
    assert result.data["source"] == "net-snmp-extend"


def test_memory_collector_preserves_precomputed_canonical_utilization():
    canonical = CanonicalMemoryResolution(
        eligible=True,
        status="canonical",
        data=LinuxEffectiveMemoryResult(
            version=1,
            total_kib=1000,
            available_kib=250,
            total_bytes=1000 * 1024,
            available_bytes=250 * 1024,
            used_bytes=750 * 1024,
            utilization_percent=73.125,
        ),
    )
    result = MemoryCollector().collect({}, None, None, canonical_memory=canonical)
    assert result.data["utilization_percent"] == 73.125


def test_invalid_extension_keeps_legacy_memory_fallback():
    fallback = CanonicalMemoryResolution(
        eligible=True, status="invalid", error_code="malformed_output"
    )
    raw = {
        "1.3.6.1.4.1.2021.4.5.0": "1000",
        "1.3.6.1.4.1.2021.4.6.0": "500",
    }
    result = MemoryCollector().collect(raw, None, None, canonical_memory=fallback)
    assert result.data["used_bytes"] == 500 * 1024
    assert result.data["utilization_percent"] == 50.0
    assert "canonical_memory_unavailable:malformed_output" in result.warnings


def test_full_and_memory_domain_collection_share_resolver(monkeypatch):
    identity = {
        "1.3.6.1.2.1.1.1.0": "Linux net-snmp",
        "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.8072",
    }
    client = Mock()
    client.operation_timeout = 3.0
    client.get.return_value = identity
    service = SNMPService(credentials(), device_id=1)
    service.client = client
    monkeypatch.setattr(service, "_walk_roots", lambda host, roots: {})
    resolution = CanonicalMemoryResolution(eligible=True, status="unavailable", error_code="timeout")
    resolver = Mock(return_value=resolution)
    monkeypatch.setattr(collector_module, "resolve_canonical_linux_memory", resolver)

    class FakeMemoryCollector:
        name = "memory"

        def collect(self, device, registry, profile, canonical_memory=None):
            assert canonical_memory is resolution
            return CollectorResponse.ok("memory", {"total_bytes": 1, "used_bytes": 1})

    monkeypatch.setattr(collector_module, "_COLLECTORS", [FakeMemoryCollector()])
    monkeypatch.setattr(collector_module, "build_registry", lambda **kwargs: Mock(profile=Mock()))

    service.collect("192.0.2.1")
    service.collect_domain("192.0.2.1", "memory")

    assert resolver.call_count == 2
