from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.cim import CIMError
from tests.test_windows_api import device, fake_db, user


def credential():
    return SimpleNamespace(id=9, username="admin", connection_host="winhost")


def inventory(errors=None):
    return {
        "controllers": [], "hubs": [], "devices": [], "errors": errors or {},
    }


def test_usb_route_is_read_only_and_returns_normalized_inventory(monkeypatch):
    client = Mock()
    client.usb_inventory.return_value = inventory()
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    result = api.get_usb_inventory(7, fake_db(device()), user())

    assert result["device_id"] == 7
    assert result["status"] == "empty"
    assert result["usb"]["collection_errors"] == []
    client.usb_inventory.assert_called_once_with()
    client.run_command.assert_not_called()


def test_usb_route_returns_partial_query_errors(monkeypatch):
    client = Mock()
    client.usb_inventory.return_value = inventory({"Win32_USBHub": "timeout"})
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    result = api.get_usb_inventory(7, fake_db(device()), user())

    assert result["status"] == "partial"
    assert result["usb"]["collection_errors"] == [{"source": "Win32_USBHub", "status": "collection_failed", "error": "timeout"}]


def test_usb_route_rejects_unauthorized_or_missing_device(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.get_usb_inventory(7, fake_db(device()), user())
    assert exc.value.status_code == 404


def test_usb_route_maps_collector_failure_without_leaking_details(monkeypatch):
    client = Mock()
    client.usb_inventory.side_effect = CIMError("timeout", "secret credential detail")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    with pytest.raises(HTTPException) as exc:
        api.get_usb_inventory(7, fake_db(device()), user())
    assert exc.value.status_code == 502
    assert exc.value.detail == "Windows USB inventory failed: timeout"
    assert "secret" not in exc.value.detail


def test_usb_route_is_registered_under_windows_prefix():
    route = next(route for route in api.router.routes if route.path == "/windows/devices/{device_id}/usb")
    assert route.methods == {"GET"}
