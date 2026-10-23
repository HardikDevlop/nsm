from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.cim import CIMError, NetworkInterfaceResult


def user():
    return SimpleNamespace(role=SimpleNamespace(role_name="Super Admin", is_system_role=True, authority_level=100))


def network_result():
    return NetworkInterfaceResult(
        12, "Ethernet 0", "Intel Ethernet", "AA-BB-CC-DD-EE-FF",
        ("192.168.100.154",), ("fe80::1%12",), "Up", 1_000_000_000, 1234, 5678,
    )


def test_network_get_reads_saved_snapshot_without_collection(monkeypatch):
    row = SimpleNamespace(device_id=314, module="network", collected_at="network-time", data=[{"interface_index": 12}])
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr(api, "_device", Mock())
    client = Mock()
    monkeypatch.setattr(api, "WindowsCIMClient", client)

    result = api.get_metric(314, "network", db, user())

    assert result == {"device_id": 314, "module": "network", "collected_at": "network-time", "data": [{"interface_index": 12}]}
    client.assert_not_called()


def test_network_fetch_calls_only_network_collector_and_persists(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    authorized_device = SimpleNamespace(id=314, site_id=10)
    monkeypatch.setattr(api, "_device", Mock(return_value=authorized_device))
    client = Mock()
    client.network_interfaces.return_value = [network_result()]
    client.operating_system.side_effect = AssertionError("network fetch must not query operating system")
    client.processor.side_effect = AssertionError("network fetch must not query CPU")
    client.disks.side_effect = AssertionError("network fetch must not query disk")
    credential = SimpleNamespace(id=9, connection_host="winhost")
    saved = SimpleNamespace(device_id=314, module="network", collected_at="network-time", data=[{"interface_index": 12}])
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential)))
    persistence = Mock(return_value=saved)
    monkeypatch.setattr(api, "upsert_network_snapshot", persistence)
    events = []
    db.commit.side_effect = lambda: events.append("commit")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.fetch_metric(314, "network", db, user())

    client.network_interfaces.assert_called_once_with()
    persistence.assert_called_once_with(db, 314, client.network_interfaces.return_value)
    assert result["module"] == "network"
    assert result["data"] == [{"interface_index": 12}]
    assert events[0] == "commit"
    assert events[1][1] == {
        "actor": user(), "action": "NETWORK_FETCH", "resource_type": "windows_device",
        "resource_id": 314, "site_id": 10, "outcome": "success",
        "metadata": {"device_id": 314, "module": "network"},
    }
    assert audit.call_count == 1


def test_network_audit_failure_does_not_change_successful_response(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=SimpleNamespace(id=314, site_id=10)))
    client = Mock()
    client.network_interfaces.return_value = []
    saved = SimpleNamespace(device_id=314, module="network", collected_at="network-time", data=[])
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, SimpleNamespace(id=9, connection_host="winhost"))))
    monkeypatch.setattr(api, "upsert_network_snapshot", Mock(return_value=saved))
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=RuntimeError("audit unavailable")))

    result = api.fetch_metric(314, "network", db, user())

    assert result["module"] == "network"
    assert result["data"] == []
    db.rollback.assert_not_called()


def test_network_fetch_failure_rolls_back_and_preserves_persistence(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=SimpleNamespace(id=314, site_id=10)))
    client = Mock()
    client.network_interfaces.side_effect = CIMError("transport", "WSMan transport failed")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, SimpleNamespace(id=9, connection_host="winhost"))))
    persistence = Mock()
    monkeypatch.setattr(api, "upsert_network_snapshot", persistence)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(314, "network", db, user())

    assert exc.value.status_code == 502
    assert "WSMan transport failed" in exc.value.detail
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    persistence.assert_not_called()


def test_network_duplicate_fetch_returns_409_before_credential_or_collection(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = False
    client_factory = Mock()
    monkeypatch.setattr(api, "_metric_client", client_factory)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(314, "network", db, user())

    assert exc.value.status_code == 409
    client_factory.assert_not_called()
    db.rollback.assert_not_called()


def test_network_routes_retain_read_and_update_rbac():
    routes = {route.path: route for route in api.router.routes}
    assert "/windows/devices/{device_id}/metrics/{module}" in routes
    assert "/windows/devices/{device_id}/metrics/{module}/fetch" in routes
    for path in routes:
        if "metrics" in path:
            assert routes[path].dependant.dependencies
