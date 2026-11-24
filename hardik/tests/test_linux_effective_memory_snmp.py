from unittest.mock import Mock

import pytest

from backend.linux_monitoring.metrics import (
    LINUX_MEMORY_EXTEND_TOKEN,
    collect_linux_effective_memory_via_extend,
    collect_linux_metrics,
    linux_memory_extend_output_oid,
)
from backend.linux_monitoring.schemas import LinuxServerMetricsCollectRequest
from backend.snmp.credentials import SNMPCredentials


EXPECTED_OID = (
    "1.3.6.1.4.1.8072.1.3.2.3.1.1.16.97.103.110.105.103.97.116.101."
    "76.105.110.117.120.77.101.109"
)


def credentials():
    return SNMPCredentials(
        version="v3",
        username="test-user",
        auth_protocol="sha",
        auth_password="auth-secret",
        security_level="authNoPriv",
    )


def test_builds_verified_ns_extend_output_oid():
    assert LINUX_MEMORY_EXTEND_TOKEN == "agnigateLinuxMem"
    assert linux_memory_extend_output_oid() == EXPECTED_OID


def test_queries_fixed_oid_and_parses_valid_output(monkeypatch):
    client = Mock()
    client.get.return_value = {
        EXPECTED_OID: "version=1 MemTotalKiB=16191488 MemAvailableKiB=9227472"
    }
    monkeypatch.setattr("backend.linux_monitoring.metrics.SNMPClient", lambda *args, **kwargs: client)

    result = collect_linux_effective_memory_via_extend("192.0.2.10", credentials())

    assert result.status == "success"
    assert result.data is not None
    assert result.data.semantic == "linux_proc_meminfo_memavailable"
    client.get.assert_called_once_with("192.0.2.10", (EXPECTED_OID,))


@pytest.mark.parametrize(
    "response, expected_status, expected_code",
    [
        ({EXPECTED_OID: "version=1 MemTotalKiB=1"}, "error", "malformed_output"),
        ({}, "unavailable", "no_such_instance"),
        ({EXPECTED_OID: "No Such Instance currently exists"}, "unavailable", "no_such_instance"),
        ({EXPECTED_OID: 123}, "error", "unsupported_response"),
    ],
)
def test_classifies_invalid_or_unsupported_responses(monkeypatch, response, expected_status, expected_code):
    client = Mock()
    client.get.return_value = response
    monkeypatch.setattr("backend.linux_monitoring.metrics.SNMPClient", lambda *args, **kwargs: client)

    result = collect_linux_effective_memory_via_extend("192.0.2.10", credentials())

    assert (result.status, result.error_code) == (expected_status, expected_code)


@pytest.mark.parametrize(
    "exception, expected_status, expected_code",
    [
        (TimeoutError("operation timed out"), "unavailable", "timeout"),
        (OSError("authorizationError"), "unavailable", "access_denied"),
        (OSError("transport failure auth-secret"), "unavailable", "snmp_error"),
    ],
)
def test_classifies_transport_failures_without_exposing_exception_text(
    monkeypatch, exception, expected_status, expected_code
):
    client = Mock()
    client.get.side_effect = exception
    monkeypatch.setattr("backend.linux_monitoring.metrics.SNMPClient", lambda *args, **kwargs: client)

    result = collect_linux_effective_memory_via_extend("192.0.2.10", credentials())

    assert (result.status, result.error_code) == (expected_status, expected_code)
    assert "auth-secret" not in repr(result)


def test_rejects_invalid_timeout_without_constructing_client(monkeypatch):
    client_factory = Mock()
    monkeypatch.setattr("backend.linux_monitoring.metrics.SNMPClient", client_factory)

    result = collect_linux_effective_memory_via_extend("192.0.2.10", credentials(), 0)

    assert (result.status, result.error_code) == ("error", "invalid_timeout")
    client_factory.assert_not_called()


def _legacy_response(oid: str, value: str):
    return {oid: value}


def _request():
    return LinuxServerMetricsCollectRequest(
        username="test-user",
        auth_protocol="sha",
        auth_password="auth-secret",
        privacy_protocol=None,
        privacy_password=None,
        security_level="authNoPriv",
        timeout_seconds=10,
    )


def test_scheduled_linux_collection_uses_canonical_memory_for_public_metric(monkeypatch):
    from backend.linux_monitoring import metrics

    def fake_get(self, host, oids):
        oid = oids[0]
        if oid == metrics.MEM_TOTAL_REAL:
            return {oid: "1000"}
        if oid == metrics.MEM_AVAIL_REAL:
            return {oid: "500"}
        if oid == metrics.linux_memory_extend_output_oid():
            return {oid: "version=1 MemTotalKiB=1000 MemAvailableKiB=250"}
        return {oid: None}

    monkeypatch.setattr(metrics.SNMPClient, "get", fake_get)
    monkeypatch.setattr(metrics.SNMPClient, "walk", lambda self, host, root: {})

    values = collect_linux_metrics("192.0.2.10", _request())

    assert values["memory_percent"] == 75.0
    canonical = values["details"]["memory"]["canonical"]
    assert canonical["status"] == "ok"
    assert canonical["semantic"] == "linux_proc_meminfo_memavailable"
    assert canonical["usage_percent"] == 75.0
    assert canonical["total_bytes"] == 1000 * 1024
    assert canonical["available_bytes"] == 250 * 1024
    assert canonical["used_bytes"] == 750 * 1024


def test_extend_failure_marks_fresh_canonical_memory_unavailable(monkeypatch):
    from backend.linux_monitoring import metrics

    def fake_get(self, host, oids):
        oid = oids[0]
        if oid == metrics.MEM_TOTAL_REAL:
            return {oid: "1000"}
        if oid == metrics.MEM_AVAIL_REAL:
            return {oid: "500"}
        if oid == metrics.linux_memory_extend_output_oid():
            return {}
        return {oid: None}

    monkeypatch.setattr(metrics.SNMPClient, "get", fake_get)
    monkeypatch.setattr(metrics.SNMPClient, "walk", lambda self, host, root: {})

    values = collect_linux_metrics("192.0.2.10", _request())

    assert values["memory_percent"] == 50.0
    canonical = values["details"]["memory"]["canonical"]
    assert canonical["status"] == "unavailable"
    assert canonical["usage_percent"] is None
    assert canonical["total_bytes"] is None
    assert canonical["error_code"] == "no_such_instance"
