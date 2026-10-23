from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.main import app
from backend.windows_monitoring.schemas import WindowsHardwareSnapshotRead
from tests.test_windows_api import device, fake_db, user


def credential():
    return SimpleNamespace(id=9, username="admin", domain=None, encrypted_secret="encrypted", connection_host="winhost")


def snapshot(device_id=7):
    return SimpleNamespace(
        device_id=device_id, collected_at=datetime(2026, 10, 17, 12, 0), computer_system={"model": "Server X"},
        system_product={}, baseboard={}, bios={}, processors=[{"name": "CPU A"}],
        memory_modules=[{"capacity_bytes": 1024}], memory_arrays=[],
    )


def hardware_data():
    return {
        "computer_system": {"model": "Server X"}, "system_product": {}, "baseboard": {}, "bios": {},
        "processors": [{"name": "CPU A"}, {"name": "CPU B"}],
        "memory_modules": [{"capacity_bytes": 1024}, {"capacity_bytes": 2048}], "memory_arrays": [],
    }


def test_hardware_routes_are_registered_and_independent():
    paths = {route.path for route in api.router.routes}
    assert "/windows/devices/{device_id}/hardware" in paths
    assert "/windows/devices/{device_id}/hardware/fetch" in paths
    assert "/windows/devices/{device_id}/hardware/sensors/discover" in paths
    assert "/windows/devices/{device_id}/hardware/disks/inventory" in paths
    assert "/windows/devices/{device_id}/hardware/disks/health" in paths


def test_backend_main_effective_routes_include_sensor_discovery():
    routes = {
        (getattr(context.starlette_route or context.original_route, "path", None), frozenset(getattr(context.starlette_route or context.original_route, "methods", None) or ()))
        for included in app.routes
        if hasattr(included, "effective_route_contexts")
        for context in included.effective_route_contexts()
    }
    assert ("/windows/devices/{device_id}/hardware/sensors/discover", frozenset({"GET"})) in routes


def test_sensor_discovery_returns_backend_values_for_authorized_device(monkeypatch):
    sensors = [{"sensor_name": "TZ00", "sensor_type": "thermal_zone", "value": 36.85, "unit": "°C", "source": "native_wmi:root/wmi", "status": "ok", "collected_at": "now"}]
    client = Mock()
    client.native_sensor_discovery.return_value = sensors
    client.librehardwaremonitor_sensors.side_effect = api.CIMError("protocol", "namespace unavailable")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    result = api.discover_hardware_sensors(7, fake_db(device()), user())

    assert result["device_id"] == 7
    assert result["sensors"][0]["sensor_name"] == "TZ00"
    assert result["sensors"][0]["sensor_id"].startswith("sensor-")
    assert result["sensors"][0]["value"] == 36.85
    assert result["providers"][0]["provider"] == "native_wmi"
    assert result["providers"][1]["status"] == "provider_not_installed"
    client.native_sensor_discovery.assert_called_once_with()


def test_sensor_discovery_preserves_missing_device_404(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.discover_hardware_sensors(315, Mock(), user())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Device not found"


def test_sensor_discovery_preserves_unauthorized_device_404(monkeypatch):
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    with pytest.raises(HTTPException) as exc:
        api.discover_hardware_sensors(315, Mock(), user())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Device not found"


def test_backend_main_effective_routes_include_hardware_endpoints():
    routes = {
        (getattr(context.starlette_route or context.original_route, "path", None), frozenset(getattr(context.starlette_route or context.original_route, "methods", None) or ()))
        for included in app.routes
        if hasattr(included, "effective_route_contexts")
        for context in included.effective_route_contexts()
    }

    assert ("/windows/devices/{device_id}/hardware", frozenset({"GET"})) in routes
    assert ("/windows/devices/{device_id}/hardware/fetch", frozenset({"POST"})) in routes


def test_disk_health_matches_only_stable_device_ids_and_normalizes_values(monkeypatch):
    client = Mock()
    client.modern_physical_disks.return_value = [{"DeviceId": "disk0", "FriendlyName": "SSD", "HealthStatus": "Healthy"}]
    client.storage_reliability_counters.return_value = [
        {"DeviceId": "disk0", "Temperature": "0", "Wear": "5"},
        {"DeviceId": "disk1", "Temperature": "bad", "Wear": "-1"},
    ]
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    result = api.discover_disk_health(315, fake_db(device()), user())

    assert result["provider_status"] == {"physical_disk": "ok", "reliability": "ok"}
    assert result["reliability_counters"][0]["association_status"] == "matched"
    assert result["reliability_counters"][0]["metrics"]["temperature"]["value"] == 0
    assert result["reliability_counters"][1]["physical_disk_device_id"] is None
    assert result["reliability_counters"][1]["metrics"]["temperature"]["status"] == "unavailable"


def test_disk_health_reports_unsupported_provider_without_502(monkeypatch):
    client = Mock()
    client.modern_physical_disks.return_value = []
    client.storage_reliability_counters.side_effect = api.CIMError("protocol", "class unavailable")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    result = api.discover_disk_health(315, fake_db(device()), user())

    assert result["provider_status"] == {"physical_disk": "unsupported", "reliability": "unavailable"}
    assert result["physical_disks"] == [] and result["reliability_counters"] == []


def test_get_hardware_without_snapshot_returns_safe_empty_sections(monkeypatch):
    monkeypatch.setattr(api, "get_hardware_snapshot", Mock(return_value=None))

    result = api.get_hardware(7, fake_db(device()), user())

    assert result == {
        "device_id": 7, "collected_at": None, "computer_system": {}, "system_product": {},
        "baseboard": {}, "bios": {}, "processors": [], "memory_modules": [], "memory_arrays": [],
    }


def test_get_hardware_returns_saved_snapshot(monkeypatch):
    saved = snapshot()
    monkeypatch.setattr(api, "get_hardware_snapshot", Mock(return_value=saved))

    result = api.get_hardware(7, fake_db(device()), user())

    assert result["device_id"] == 7
    assert result["processors"] == [{"name": "CPU A"}]
    assert result["memory_modules"] == [{"capacity_bytes": 1024}]


def test_get_hardware_normalizes_legacy_list_shaped_singletons_for_response_validation(monkeypatch):
    saved = snapshot()
    saved.computer_system = [{"model": "Legacy Server"}]
    saved.system_product = []
    saved.baseboard = [None]
    saved.bios = [{"manufacturer": "Firmware Co"}]
    monkeypatch.setattr(api, "get_hardware_snapshot", Mock(return_value=saved))

    result = api.get_hardware(7, fake_db(device()), user())
    validated = WindowsHardwareSnapshotRead.model_validate(result)

    assert validated.computer_system == {"model": "Legacy Server"}
    assert validated.system_product == {}
    assert validated.baseboard == {}
    assert validated.bios == {"manufacturer": "Firmware Co"}


def test_successful_hardware_fetch_collects_persists_and_commits(monkeypatch):
    authorized_device = device()
    db = fake_db(authorized_device, authorized_device, credential())
    current_user = user()
    client = Mock(hostname="winhost")
    client.hardware_information.return_value = hardware_data()
    saved = snapshot()
    metric_client = Mock(return_value=(client, credential()))
    monkeypatch.setattr(api, "_metric_client", metric_client)
    monkeypatch.setattr(api, "upsert_hardware_snapshot", Mock(return_value=saved))
    monkeypatch.setattr(api, "_audit", Mock())

    result = api.fetch_hardware(7, db, current_user)

    client.hardware_information.assert_called_once_with()
    metric_client.assert_called_once_with(db, 7, current_user, device=authorized_device)
    api.upsert_hardware_snapshot.assert_called_once_with(db, 7, hardware_data())
    db.commit.assert_called_once()
    assert len(result["processors"]) == 1


def test_hardware_snapshot_commits_before_success_audit(monkeypatch):
    db = fake_db(device(), device(), credential())
    client = Mock(hostname="winhost")
    client.hardware_information.return_value = hardware_data()
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "upsert_hardware_snapshot", Mock(return_value=snapshot()))
    events = []
    db.commit.side_effect = lambda: events.append("commit")
    monkeypatch.setattr(api, "_audit", Mock(side_effect=lambda *args: events.append("audit")))

    api.fetch_hardware(7, db, user())

    assert events == ["commit", "audit"]


def test_hardware_audit_failure_does_not_change_successful_response(monkeypatch):
    db = fake_db(device(), device(), credential())
    client = Mock(hostname="winhost")
    client.hardware_information.return_value = hardware_data()
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "upsert_hardware_snapshot", Mock(return_value=snapshot()))
    monkeypatch.setattr(api, "_audit", Mock(side_effect=RuntimeError("audit database unavailable")))

    result = api.fetch_hardware(7, db, user())

    assert result["device_id"] == 7
    assert result["processors"] == [{"name": "CPU A"}]
    db.rollback.assert_not_called()


def test_post_hardware_fetch_normalizes_actual_list_shaped_cim_output(monkeypatch):
    db = fake_db(device(), device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock(hostname="winhost")
    client.hardware_information.return_value = {
        "computer_system": [{"model": "Server X"}], "system_product": [{"name": "Product X"}],
        "baseboard": [{"product": "Board X"}], "bios": [{"manufacturer": "Firmware Co"}],
        "processors": [{"name": "CPU A"}, {"name": "CPU B"}],
        "memory_modules": [{"capacity_bytes": 1024}, {"capacity_bytes": 2048}], "memory_arrays": [],
    }
    saved = SimpleNamespace(device_id=7, collected_at=datetime(2026, 10, 17, 12, 0), **client.hardware_information.return_value)
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "upsert_hardware_snapshot", Mock(return_value=saved))
    monkeypatch.setattr(api, "_audit", Mock())

    result = api.fetch_hardware(7, db, user())
    validated = WindowsHardwareSnapshotRead.model_validate(result)

    assert validated.computer_system == {"model": "Server X"}
    assert validated.system_product == {"name": "Product X"}
    assert len(validated.processors) == 2
    assert len(validated.memory_modules) == 2


def test_hardware_fetch_lock_conflict_does_not_collect(monkeypatch):
    db = fake_db(device(), device(), credential())
    db.execute.return_value.scalar_one.return_value = False
    client_factory = Mock()
    monkeypatch.setattr(api, "_metric_client", client_factory)

    with pytest.raises(HTTPException) as exc:
        api.fetch_hardware(7, db, user())

    assert exc.value.status_code == 409
    client_factory.assert_not_called()


def test_hardware_fetch_without_credentials_returns_not_found(monkeypatch):
    db = fake_db(device(), device(), None)
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_metric_client", Mock(side_effect=HTTPException(status_code=404, detail="Windows credential not found")))

    with pytest.raises(HTTPException) as exc:
        api.fetch_hardware(7, db, user())

    assert exc.value.status_code == 404
    db.rollback.assert_called_once()


def test_hardware_fetch_rejects_site_reassignment_after_lock(monkeypatch):
    initial = device(site_id=10)
    reassigned = device(site_id=55)
    db = fake_db(initial, reassigned, credential())
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    metric_client = Mock()
    monkeypatch.setattr(api, "_metric_client", metric_client)
    scoped_user = SimpleNamespace(id=2, role=SimpleNamespace(role_name="Viewer", is_system_role=False, authority_level=10), sites=[SimpleNamespace(id=10)])

    with pytest.raises(HTTPException) as exc:
        api.fetch_hardware(7, db, scoped_user)

    assert exc.value.status_code == 404
    metric_client.assert_not_called()


def test_hardware_fetch_rejects_deletion_after_lock(monkeypatch):
    db = fake_db(device(), None, credential())
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    metric_client = Mock()
    monkeypatch.setattr(api, "_metric_client", metric_client)

    with pytest.raises(HTTPException) as exc:
        api.fetch_hardware(7, db, user())

    assert exc.value.status_code == 404
    metric_client.assert_not_called()


def test_hardware_audit_uses_revalidated_device(monkeypatch):
    initial = device(site_id=10)
    current = device(site_id=20)
    db = fake_db(initial, current, credential())
    client = Mock(hostname="winhost")
    client.hardware_information.return_value = hardware_data()
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "upsert_hardware_snapshot", Mock(return_value=snapshot()))
    audit = Mock()
    monkeypatch.setattr(api, "_audit", audit)

    api.fetch_hardware(7, db, user())

    assert audit.call_args.args[3] is current


def test_hardware_fetch_cim_failure_rolls_back_and_does_not_upsert(monkeypatch):
    db = fake_db(device(), device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock(hostname="winhost")
    client.hardware_information.side_effect = api.CIMError("protocol", "query failed")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    upsert = Mock()
    monkeypatch.setattr(api, "upsert_hardware_snapshot", upsert)

    with pytest.raises(HTTPException) as exc:
        api.fetch_hardware(7, db, user())

    assert exc.value.status_code == 502
    db.rollback.assert_called_once()
    upsert.assert_not_called()


def test_hardware_fetch_database_failure_rolls_back_and_hides_sensitive_identifiers(monkeypatch):
    db = fake_db(device(), device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock(hostname="winhost")
    client.hardware_information.return_value = hardware_data()
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "upsert_hardware_snapshot", Mock(side_effect=RuntimeError("db failed")))

    with pytest.raises(HTTPException) as exc:
        api.fetch_hardware(7, db, user())

    assert exc.value.status_code == 502
    assert "db failed" not in str(exc.value.detail)
    db.rollback.assert_called_once()
    assert all("uuid" not in str(value).lower() for value in hardware_data().values())
