from __future__ import annotations

import pytest

from backend.snmp import collector as collector_module
from backend.snmp.client import SNMPClient
from backend.snmp.collector import SNMPService
from backend.snmp.credentials import SNMPCredentials


def test_production_client_receives_device_id():
    service = SNMPService(SNMPCredentials(), device_id=115)
    assert isinstance(service.client, SNMPClient)
    assert service.client.device_id == 115


def test_legacy_factory_without_device_id_still_works(monkeypatch):
    received = []

    def legacy_factory(credentials, timeout=None, retries=None, operation_timeout=None):
        received.append((credentials, timeout, retries, operation_timeout))
        return object()

    monkeypatch.setattr(collector_module, "SNMPClient", legacy_factory)
    service = SNMPService(SNMPCredentials(), device_id=115)
    assert service.client is not None
    assert len(received) == 1


def test_factory_supporting_device_id_receives_it(monkeypatch):
    received = []

    def current_factory(
        credentials, timeout=None, retries=None, operation_timeout=None, device_id=None
    ):
        received.append(device_id)
        return object()

    monkeypatch.setattr(collector_module, "SNMPClient", current_factory)
    SNMPService(SNMPCredentials(), device_id=115)
    assert received == [115]


def test_constructor_type_error_is_not_silently_retried(monkeypatch):
    calls = 0

    def broken_factory(
        credentials, timeout=None, retries=None, operation_timeout=None, device_id=None
    ):
        nonlocal calls
        calls += 1
        raise TypeError("constructor implementation bug")

    monkeypatch.setattr(collector_module, "SNMPClient", broken_factory)
    with pytest.raises(TypeError, match="constructor implementation bug"):
        SNMPService(SNMPCredentials(), device_id=115)
    assert calls == 1
