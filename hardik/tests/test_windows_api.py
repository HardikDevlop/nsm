from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.api import router
from backend.windows_monitoring.schemas import WindowsCredentialCreate, WindowsCredentialUpdate
from backend.windows_monitoring.winrm import WinRMConnectionDiagnostic


def test_windows_router_contains_required_routes():
    paths = {route.path for route in router.routes}
    assert "/windows/devices/{device_id}/credentials" in paths
    assert "/windows/devices/{device_id}/credentials/{credential_id}" in paths
    assert "/windows/devices/{device_id}/connection-test" in paths
    assert "/windows/devices/{device_id}/metrics/{module}" in paths
    assert "/windows/devices/{device_id}/metrics/{module}/fetch" in paths

def test_metric_modules_are_explicitly_bounded():
    assert api.WINDOW_MODULES == {"system", "cpu", "memory", "disk", "network"}


def test_legacy_system_fetch_queries_and_persists_system_info_only(monkeypatch):
    class FakeOS:
        hostname = "WIN01"
        caption = "Windows Server"
        version = "10.0"

    client = Mock()
    client.operating_system.return_value = [FakeOS()]
    client.processor.side_effect = AssertionError("legacy system fetch must not query CPU")
    client.disks.side_effect = AssertionError("legacy system fetch must not query disk")
    row = SimpleNamespace(
        id=11, device_id=7, collected_at=None, system_info={"hostname": "WIN01", "caption": "Windows Server", "version": "10.0"}, cpu={"saved": True},
        memory={"saved": True}, disks=[{"saved": True}],
    )
    db = fake_db(device(), credential(), row, row)
    db.execute.return_value.scalar_one.return_value = row.id
    monkeypatch.setattr(api, "decrypt_secret", Mock(return_value="password"))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="ca.pem"))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.fetch_system_info(7, db, user())

    client.operating_system.assert_called_once_with()
    client.processor.assert_not_called()
    client.disks.assert_not_called()
    assert result["system_info"]["hostname"] == "WIN01"
    assert result["cpu"] == {"saved": True}
    assert result["memory"] == {"saved": True}
    assert result["disks"] == [{"saved": True}]
    audit.assert_called_once_with(
        db,
        actor=user(),
        action="SYSTEM_FETCH",
        resource_type="windows_device",
        resource_id=7,
        site_id=10,
        outcome="success",
        metadata={"device_id": 7, "module": "system"},
    )


def test_system_fetch_audit_occurs_after_commit_and_failure_is_best_effort(monkeypatch):
    class FakeOS:
        hostname = "WIN01"
        caption = "Windows Server"
        version = "10.0"

    client = Mock()
    client.operating_system.return_value = [FakeOS()]
    row = SimpleNamespace(
        id=11, device_id=7, collected_at=None, system_info={"caption": "Windows Server"},
        cpu={}, memory={}, disks=[],
    )
    db = fake_db(device(), credential(), row, row)
    db.execute.return_value.scalar_one.return_value = row.id
    monkeypatch.setattr(api, "decrypt_secret", Mock(return_value="password"))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="ca.pem"))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    events = []
    db.commit.side_effect = lambda: events.append("commit")
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=lambda *args, **kwargs: events.append("audit")))

    result = api.fetch_system_info(7, db, user())

    assert result["device_id"] == 7
    assert events == ["commit", "audit"]
    db.rollback.assert_not_called()


def test_system_info_serialization_preserves_extended_os_fields():
    os_data = SimpleNamespace(
        hostname="WIN01", caption="Windows 11 Pro", version="10.0",
        manufacturer="Microsoft Corporation", build_number="26100",
        architecture="64-bit", os_type=18, product_type=1,
        install_date="2024-01-01T06:30:00+00:00",
        last_boot_time="2026-10-17T09:21:44.580916+00:00",
        windows_directory="C:\\Windows", system_directory="C:\\Windows\\System32",
        system_drive="C:", boot_device="\\Device\\HarddiskVolume3",
        locale="en-US", time_zone="330", service_pack="0",
    )

    value = api._system_info_value(os_data)

    assert value["manufacturer"] == "Microsoft Corporation"
    assert value["build_number"] == "26100"
    assert value["architecture"] == "64-bit"
    assert value["install_date"] == "2024-01-01T06:30:00+00:00"
    assert value["last_boot_time"] == "2026-10-17T09:21:44.580916+00:00"
    assert value["windows_directory"] == "C:\\Windows"
    assert value["system_directory"] == "C:\\Windows\\System32"
    assert value["locale"] == "en-US"
    assert value["time_zone"] == "330"
    assert value["uptime_seconds"] is not None


def test_get_system_info_returns_extended_fields_saved_in_snapshot():
    saved = {
        "hostname": "WIN01", "caption": "Windows 11 Pro", "version": "10.0",
        "manufacturer": "Microsoft Corporation", "build_number": "26100",
        "architecture": "64-bit", "install_date": "2024-01-01T06:30:00+00:00",
        "last_boot_time": "2026-10-17T09:21:44.580916+00:00", "uptime_seconds": 10.0,
        "windows_directory": "C:\\Windows", "system_directory": "C:\\Windows\\System32",
        "locale": "en-US", "time_zone": "330",
    }
    row = SimpleNamespace(device_id=7, collected_at="saved-time", system_info=saved,
                           cpu={}, memory={}, disks=[])
    result = api.get_system_info(7, fake_db(device(), row), user())

    assert result["system_info"] == saved
    assert result["system_info"]["manufacturer"] == "Microsoft Corporation"
    assert result["system_info"]["build_number"] == "26100"


def test_system_metric_fetch_persists_extended_os_fields(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="system", collected_at="fresh-time", data={})
    os_data = SimpleNamespace(
        hostname="WIN01", caption="Windows 11 Pro", version="10.0",
        manufacturer="Microsoft Corporation", build_number="26100", architecture="64-bit",
        os_type=18, product_type=1, install_date="2024-01-01T06:30:00+00:00",
        last_boot_time="2026-10-17T09:21:44.580916+00:00", windows_directory="C:\\Windows",
        system_directory="C:\\Windows\\System32", system_drive="C:", boot_device="\\Device\\HarddiskVolume3",
        locale="en-US", time_zone="330", service_pack="0", total_memory_bytes=1, free_memory_bytes=1,
    )
    client = Mock()
    client.operating_system.return_value = [os_data]
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))

    result = api.fetch_metric(7, "system", db, user())

    persisted = api._upsert_metric_snapshot.call_args.args[3]
    assert persisted["manufacturer"] == "Microsoft Corporation"
    assert persisted["build_number"] == "26100"
    assert persisted["architecture"] == "64-bit"
    assert persisted["install_date"] == "2024-01-01T06:30:00+00:00"
    assert result["data"] == {}


@pytest.mark.parametrize("detail", ["Device not found", "Windows credential not found"])
def test_system_fetch_preserves_http_errors_and_rolls_back(monkeypatch, detail):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(side_effect=HTTPException(status_code=404, detail=detail)))

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_info(7, db, user())

    assert exc.value.status_code == 404
    assert exc.value.detail == detail
    db.rollback.assert_called_once()


@pytest.mark.parametrize("module", ["cpu", "memory", "disk", "network"])
def test_metric_fetch_preserves_http_errors_and_rolls_back(monkeypatch, module):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=device()))
    monkeypatch.setattr(api, "_metric_client", Mock(side_effect=HTTPException(status_code=404, detail="Windows credential not found")))

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, module, db, user())

    assert exc.value.status_code == 404
    assert exc.value.detail == "Windows credential not found"
    db.rollback.assert_called_once()


def test_system_failure_audit_happens_after_rollback_with_safe_category(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    connection = api._WindowsConnectionContext(
        device=device(), credential=credential(), host="winhost", username="admin", password="secret",
    )
    client = Mock()
    client.operating_system.side_effect = api.CIMError("transport", "WSMan transport failed")
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    events = []
    db.rollback.side_effect = lambda: events.append("rollback")
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs))))

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_info(7, db, user())

    assert exc.value.status_code == 502
    assert events == ["rollback", ("audit", {
        "actor": user(), "action": "SYSTEM_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "failure",
        "failure_reason": "winrm_connection_failed", "metadata": {"device_id": 7, "module": "system"},
    })]


def test_system_credential_404_is_audited_as_missing_credential(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(side_effect=HTTPException(status_code=404, detail="Windows credential not found")))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_info(7, db, user())

    assert exc.value.status_code == 404
    assert audit.call_args.kwargs["failure_reason"] == "credential_missing"


def test_system_failure_audit_error_does_not_change_sanitized_error(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    connection = api._WindowsConnectionContext(
        device=device(), credential=credential(), host="winhost", username="admin", password="secret",
    )
    client = Mock()
    client.operating_system.side_effect = api.CIMError("authentication", "WSMan authentication failed")
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(return_value=client))
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=RuntimeError("audit database failure")))

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_info(7, db, user())

    assert exc.value.status_code == 502
    assert exc.value.detail == "Windows collection failed during cim: WSMan authentication failed"


def test_fetch_lock_returns_409_for_same_device_and_module():
    db = Mock()
    db.execute.return_value.scalar_one.return_value = False

    with pytest.raises(HTTPException) as exc:
        api._fetch_lock(db, 311, "cpu")

    assert exc.value.status_code == 409
    assert "already in progress" in exc.value.detail


def test_fetch_lock_keys_are_independent_by_device_and_module():
    db = Mock()
    db.execute.return_value.scalar_one.side_effect = [True, True, True]

    api._fetch_lock(db, 311, "cpu")
    api._fetch_lock(db, 311, "memory")
    api._fetch_lock(db, 312, "cpu")

    keys = [call.args[1]["lock_key"] for call in db.execute.call_args_list]
    assert keys == [
        "nms.windows.fetch:311:cpu",
        "nms.windows.fetch:311:memory",
        "nms.windows.fetch:312:cpu",
    ]


def test_metric_fetch_conflict_does_not_start_collection(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = False
    client_factory = Mock()
    monkeypatch.setattr(api, "_metric_client", client_factory)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(311, "cpu", db, user())

    assert exc.value.status_code == 409
    client_factory.assert_not_called()
    db.rollback.assert_not_called()


def test_failed_metric_fetch_rolls_back_without_upserting(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=device()))
    monkeypatch.setattr(api, "record_audit_event", Mock())
    client = Mock()
    client.processor.side_effect = api.CIMError("protocol", "query failed")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    upsert = Mock()
    monkeypatch.setattr(api, "_upsert_metric_snapshot", upsert)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "cpu", db, user())

    assert exc.value.status_code == 502
    db.rollback.assert_called_once()
    upsert.assert_not_called()


def test_cpu_fetch_audits_after_commit_with_device_metadata(monkeypatch):
    authorized_device = device(site_id=10)
    db = fake_db(authorized_device, credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="cpu", collected_at="cpu-time", data={"usage_percent": 12.5})
    client = Mock()
    client.processor_performance.return_value = [SimpleNamespace(name="_Total", usage_percent=12.5, user_percent=None, privileged_percent=None, idle_percent=None, interrupts_per_sec=None, context_switches_per_sec=None)]
    client.system_performance.return_value = []
    client.hardware_processors.return_value = []
    client.computer_system.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))
    events = []
    db.commit.side_effect = lambda: events.append("commit")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.fetch_metric(7, "cpu", db, user())

    assert result["data"] == {"usage_percent": 12.5}
    assert events[0] == "commit"
    assert events[1][0] == "audit"
    assert events[1][1] == {
        "actor": user(), "action": "CPU_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "success",
        "metadata": {"device_id": 7, "module": "cpu"},
    }
    assert audit.call_count == 1


def test_cpu_audit_failure_does_not_change_successful_response(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="cpu", collected_at="cpu-time", data={"usage_percent": 12.5})
    client = Mock()
    client.processor_performance.return_value = [SimpleNamespace(name="_Total", usage_percent=12.5, user_percent=None, privileged_percent=None, idle_percent=None, interrupts_per_sec=None, context_switches_per_sec=None)]
    client.system_performance.return_value = []
    client.hardware_processors.return_value = []
    client.computer_system.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=RuntimeError("audit unavailable")))

    result = api.fetch_metric(7, "cpu", db, user())

    assert result["module"] == "cpu"
    assert result["data"] == {"usage_percent": 12.5}
    db.rollback.assert_not_called()


def test_cpu_failure_audit_happens_after_rollback_with_safe_category(monkeypatch):
    authorized_device = device(site_id=10)
    db = fake_db(authorized_device, credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock()
    client.processor_performance.side_effect = api.CIMError("transport", "WSMan transport failed")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    events = []
    db.rollback.side_effect = lambda: events.append("rollback")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "cpu", db, user())

    assert exc.value.status_code == 502
    assert events == ["rollback", ("audit", {
        "actor": user(), "action": "CPU_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "failure",
        "failure_reason": "winrm_connection_failed", "metadata": {"device_id": 7, "module": "cpu"},
    })]


def test_cpu_credential_failure_audit_preserves_404(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    authorized_device = device(site_id=10)
    monkeypatch.setattr(api, "_device", Mock(return_value=authorized_device))
    monkeypatch.setattr(api, "_metric_client", Mock(side_effect=HTTPException(status_code=404, detail="Windows credential not found")))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "cpu", db, user())

    assert exc.value.status_code == 404
    assert audit.call_args.kwargs["failure_reason"] == "credential_missing"


def test_cpu_authorization_failure_skips_device_failure_audit(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "cpu", db, user())

    assert exc.value.status_code == 404
    audit.assert_not_called()


def test_memory_failure_audit_happens_after_rollback_with_safe_category(monkeypatch):
    authorized_device = device(site_id=10)
    db = fake_db(authorized_device, credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock()
    client.operating_system.side_effect = api.CIMError("transport", "WSMan transport failed")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    events = []
    db.rollback.side_effect = lambda: events.append("rollback")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "memory", db, user())

    assert exc.value.status_code == 502
    assert events == ["rollback", ("audit", {
        "actor": user(), "action": "MEMORY_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "failure",
        "failure_reason": "winrm_connection_failed", "metadata": {"device_id": 7, "module": "memory"},
    })]


def test_memory_credential_failure_audit_preserves_404(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=device(site_id=10)))
    monkeypatch.setattr(api, "_metric_client", Mock(side_effect=HTTPException(status_code=404, detail="Windows credential not found")))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "memory", db, user())

    assert exc.value.status_code == 404
    assert audit.call_args.kwargs["action"] == "MEMORY_FETCH"
    assert audit.call_args.kwargs["failure_reason"] == "credential_missing"


def test_disk_failure_audit_happens_after_rollback_with_safe_category(monkeypatch):
    authorized_device = device(site_id=10)
    db = fake_db(authorized_device, credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock()
    client.disks.side_effect = api.CIMError("transport", "WSMan transport failed")
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    events = []
    db.rollback.side_effect = lambda: events.append("rollback")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "disk", db, user())

    assert exc.value.status_code == 502
    assert events == ["rollback", ("audit", {
        "actor": user(), "action": "DISK_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "failure",
        "failure_reason": "winrm_connection_failed", "metadata": {"device_id": 7, "module": "disk"},
    })]


def test_disk_credential_failure_audit_preserves_404(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=device(site_id=10)))
    monkeypatch.setattr(api, "_metric_client", Mock(side_effect=HTTPException(status_code=404, detail="Windows credential not found")))
    audit = Mock()
    monkeypatch.setattr(api, "record_audit_event", audit)

    with pytest.raises(HTTPException) as exc:
        api.fetch_metric(7, "disk", db, user())

    assert exc.value.status_code == 404
    assert audit.call_args.kwargs["action"] == "DISK_FETCH"
    assert audit.call_args.kwargs["failure_reason"] == "credential_missing"


def test_memory_fetch_audits_after_commit_with_device_metadata(monkeypatch):
    authorized_device = device(site_id=10)
    db = fake_db(authorized_device, credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="memory", collected_at="memory-time", data={"usage_percent": 50.0})
    client = Mock()
    client.operating_system.return_value = [SimpleNamespace(total_memory_bytes=200, free_memory_bytes=100)]
    client.memory_performance.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))
    events = []
    db.commit.side_effect = lambda: events.append("commit")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.fetch_metric(7, "memory", db, user())

    assert result["data"] == {"usage_percent": 50.0}
    assert events[0] == "commit"
    assert events[1][1] == {
        "actor": user(), "action": "MEMORY_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "success",
        "metadata": {"device_id": 7, "module": "memory"},
    }
    assert audit.call_count == 1


def test_memory_audit_failure_does_not_change_successful_response(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="memory", collected_at="memory-time", data={"usage_percent": 50.0})
    client = Mock()
    client.operating_system.return_value = [SimpleNamespace(total_memory_bytes=200, free_memory_bytes=100)]
    client.memory_performance.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=RuntimeError("audit unavailable")))

    result = api.fetch_metric(7, "memory", db, user())

    assert result["module"] == "memory"
    assert result["data"] == {"usage_percent": 50.0}
    db.rollback.assert_not_called()


def test_memory_basic_collection_succeeds_when_optional_counters_fail(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    client = Mock()
    client.operating_system.return_value = [SimpleNamespace(total_memory_bytes=1000, free_memory_bytes=250)]
    client.memory_performance.side_effect = api.CIMError("protocol", "memory performance class unavailable")
    saved = SimpleNamespace(device_id=7, module="memory", collected_at="memory-time", data={})
    upsert = Mock(return_value=saved)
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", upsert)
    monkeypatch.setattr(api, "record_audit_event", Mock())

    result = api.fetch_metric(7, "memory", db, user())

    value = upsert.call_args.args[3]
    assert result["module"] == "memory"
    assert value["total_bytes"] == 1000
    assert value["free_bytes"] == 250
    assert value["usage_percent"] == 75.0
    assert value["counters"]["available_mbytes"]["value"] is None
    assert value["counters"]["available_mbytes"]["status"] == "unavailable"


def test_disk_fetch_audits_after_commit_with_device_metadata(monkeypatch):
    authorized_device = device(site_id=10)
    db = fake_db(authorized_device, credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="disk", collected_at="disk-time", data=[{"device_id": "C:"}])
    client = Mock()
    client.disks.return_value = [SimpleNamespace(device_id="C:", volume_name="Windows", size_bytes=100, free_bytes=40)]
    client.disk_performance.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))
    events = []
    db.commit.side_effect = lambda: events.append("commit")
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.fetch_metric(7, "disk", db, user())

    assert result["data"] == [{"device_id": "C:"}]
    assert events[0] == "commit"
    assert events[1][1] == {
        "actor": user(), "action": "DISK_FETCH", "resource_type": "windows_device",
        "resource_id": 7, "site_id": 10, "outcome": "success",
        "metadata": {"device_id": 7, "module": "disk"},
    }
    assert audit.call_count == 1


def test_disk_audit_failure_does_not_change_successful_response(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="disk", collected_at="disk-time", data=[])
    client = Mock()
    client.disks.return_value = []
    client.disk_performance.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=RuntimeError("audit unavailable")))

    result = api.fetch_metric(7, "disk", db, user())

    assert result["module"] == "disk"
    assert result["data"] == []
    db.rollback.assert_not_called()


def test_disk_capacity_response_preserves_legacy_fields_with_performance(monkeypatch):
    db = fake_db(device(), credential())
    db.execute.return_value.scalar_one.return_value = True
    saved = SimpleNamespace(device_id=7, module="disk", collected_at="disk-time", data=[])
    client = Mock()
    client.disks.return_value = [SimpleNamespace(device_id="C:", volume_name="Windows", size_bytes=100, free_bytes=40)]
    perf = SimpleNamespace(instance="0 C:", read_iops=0, write_iops=2, total_iops=2, read_bytes_per_sec=0, write_bytes_per_sec=4096, total_bytes_per_sec=4096, read_latency_ms=1, write_latency_ms=2, average_latency_ms=1.5, average_queue_length=0, current_queue_length=0, split_io_per_sec=0, percent_disk_time=4)
    client.disk_performance.side_effect = [[perf], []]
    upsert = Mock(return_value=saved)
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))
    monkeypatch.setattr(api, "_upsert_metric_snapshot", upsert)
    monkeypatch.setattr(api, "record_audit_event", Mock())

    api.fetch_metric(7, "disk", db, user())

    value = upsert.call_args.args[3]
    assert value[0]["device_id"] == "C:"
    assert value[0]["free_bytes"] == 40
    assert value[0]["performance"]["logical"][0]["metrics"]["read_iops"]["value"] == 0


def test_metric_persistence_upsert_keeps_module_specific_timestamp_and_data(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(api, "_device", Mock(return_value=device()))
    monkeypatch.setattr(api, "record_audit_event", Mock())
    saved = SimpleNamespace(device_id=7, module="cpu", collected_at="cpu-time", data={"usage_percent": 12.5})
    monkeypatch.setattr(api, "_metric_client", Mock())
    monkeypatch.setattr(api, "_upsert_metric_snapshot", Mock(return_value=saved))

    class FakeCPU:
        name = "_Total"
        percent_processor_time = 12.5

    client = Mock()
    client.processor_performance.return_value = [SimpleNamespace(name="_Total", usage_percent=12.5, user_percent=None, privileged_percent=None, idle_percent=None, interrupts_per_sec=None, context_switches_per_sec=None)]
    client.system_performance.return_value = []
    client.hardware_processors.return_value = []
    client.computer_system.return_value = []
    monkeypatch.setattr(api, "_metric_client", Mock(return_value=(client, credential())))

    result = api.fetch_metric(7, "cpu", db, user())

    assert result["module"] == "cpu"
    assert result["collected_at"] == "cpu-time"
    assert result["data"] == {"usage_percent": 12.5}
    db.commit.assert_called_once()


def test_windows_routes_use_existing_permission_dependencies():
    assert all(route.dependant.dependencies for route in router.routes)
    assert all(any(dep.call.__name__ == "checker" for dep in route.dependant.dependencies) for route in router.routes)


class Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args):
        return self

    def populate_existing(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value


def fake_db(*values):
    db = Mock()
    db.query.side_effect = [Query(value) for value in values]
    return db


def device(site_id=10, device_id=7):
    return SimpleNamespace(id=device_id, site_id=site_id, hostname="winhost", ip_address="10.0.0.7", deleted_at=None)


def user():
    return SimpleNamespace(id=1, role=SimpleNamespace(role_name="Super Admin", is_system_role=True, authority_level=100))


def credential(credential_id=3, device_id=7):
    from datetime import datetime
    now = datetime.now()
    return SimpleNamespace(id=credential_id, device_id=device_id, auth_method="password", username="admin",
                           connection_host="winhost", 
                           domain=None, enabled=True, is_verified=False, last_verified_at=None,
                           created_at=now, updated_at=now, encrypted_secret="ciphertext")


def test_resolve_windows_connection_accepts_enabled_credential(monkeypatch):
    row = credential()
    db = fake_db(device(), row)
    decrypt = Mock(return_value="decrypted-secret")
    monkeypatch.setattr(api, "decrypt_secret", decrypt)

    result = api._resolve_windows_connection(db, 7, user())

    assert result.device.id == 7
    assert result.credential is row
    assert result.host == "winhost"
    assert result.username == "admin"
    assert result.password == "decrypted-secret"
    decrypt.assert_called_once_with("ciphertext")


def test_resolve_windows_connection_rejects_disabled_credential():
    row = credential()
    row.enabled = False
    class DisabledCredentialQuery(Query):
        def first(self):
            return self.value if self.value.enabled else None
    with pytest.raises(HTTPException) as exc:
        db = Mock()
        db.query.side_effect = [Query(device()), DisabledCredentialQuery(row)]
        api._resolve_windows_connection(db, 7, user())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Windows credential not found"


def test_resolve_windows_connection_rejects_missing_credential():
    with pytest.raises(HTTPException) as exc:
        api._resolve_windows_connection(fake_db(device(), None), 7, user())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Windows credential not found"


def test_resolve_windows_connection_does_not_select_other_device_credential():
    row = credential(device_id=99)

    class CredentialQuery(Query):
        def filter(self, *args):
            return self

        def first(self):
            return self.value if self.value.device_id == 7 else None

    db = Mock()
    db.query.side_effect = [Query(device()), CredentialQuery(row)]
    with pytest.raises(HTTPException) as exc:
        api._resolve_windows_connection(db, 7, user())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Windows credential not found"


def test_resolve_windows_connection_rejects_unauthorized_site(monkeypatch):
    monkeypatch.setattr(api, "can_access_site", Mock(return_value=False))
    with pytest.raises(HTTPException) as exc:
        api._resolve_windows_connection(fake_db(device(site_id=55)), 7, user())
    assert exc.value.status_code == 404
    assert exc.value.detail == "Device not found"


def test_resolve_windows_connection_builds_username_and_prefers_connection_host(monkeypatch):
    row = credential()
    row.domain = "DESKTOP-ENI0R6E"
    row.connection_host = "configured-host"
    monkeypatch.setattr(api, "decrypt_secret", Mock(return_value="secret-value"))

    result = api._resolve_windows_connection(fake_db(device(), row), 7, user())

    assert result.username == r"DESKTOP-ENI0R6E\admin"
    assert result.host == "configured-host"
    assert "secret-value" not in str(result.device)


@pytest.mark.parametrize("hostname,ip_address,expected", [("winhost", "10.0.0.7", "winhost"), ("", "10.0.0.7", "10.0.0.7")])
def test_resolve_windows_connection_falls_back_to_device_host(monkeypatch, hostname, ip_address, expected):
    row = credential()
    row.connection_host = None
    current = device()
    current.hostname = hostname
    current.ip_address = ip_address
    monkeypatch.setattr(api, "decrypt_secret", Mock(return_value="secret-value"))

    result = api._resolve_windows_connection(fake_db(current, row), 7, user())

    assert result.host == expected


def test_resolve_windows_connection_is_device_specific(monkeypatch):
    first = credential(credential_id=3, device_id=7)
    second = credential(credential_id=4, device_id=8)
    first.connection_host = "host-7"
    second.connection_host = "host-8"
    monkeypatch.setattr(api, "decrypt_secret", lambda value: f"plain-{value}")

    first_result = api._resolve_windows_connection(fake_db(device(device_id=7), first), 7, user())
    second_result = api._resolve_windows_connection(fake_db(device(device_id=8), second), 8, user())

    assert (first_result.credential.id, first_result.host) == (3, "host-7")
    assert (second_result.credential.id, second_result.host) == (4, "host-8")


def test_metric_client_passes_decrypted_secret_and_ca_path(monkeypatch, caplog):
    row = credential()
    monkeypatch.setattr(api, "decrypt_secret", Mock(return_value="secret-value"))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="/trusted/ca.pem"))
    client_factory = Mock(return_value="client")
    monkeypatch.setattr(api, "WindowsCIMClient", client_factory)

    client, resolved = api._metric_client(fake_db(device(), row), 7, user())

    assert client == "client"
    assert resolved is row
    client_factory.assert_called_once_with("winhost", "admin", "secret-value", trusted_ca_path="/trusted/ca.pem")
    assert "secret-value" not in "".join(record.getMessage() for record in caplog.records)


def test_list_response_excludes_plaintext_and_ciphertext(monkeypatch):
    row = credential()
    db = fake_db(device(), [row])
    result = api.list_credentials(7, db, user())
    assert result == [row]
    assert not hasattr(result[0], "secret")
    assert "plaintext-password" not in str(result)
    sanitized = api.WindowsCredentialRead.model_validate(row).model_dump()
    assert "encrypted_secret" not in sanitized


def test_cross_device_credential_is_denied():
    db = fake_db(None)
    with pytest.raises(HTTPException) as exc:
        api._credential(db, 7, 99)
    assert exc.value.status_code == 404


def test_site_scope_denies_non_super_admin():
    scoped_user = SimpleNamespace(id=2, role=SimpleNamespace(role_name="Viewer", is_system_role=False, authority_level=10), sites=[])
    with pytest.raises(HTTPException) as exc:
        api._device(fake_db(device(site_id=10)), 7, scoped_user)
    assert exc.value.status_code == 404


def test_create_commits_and_never_returns_secret(monkeypatch):
    row = credential()
    db = fake_db(device(), None)
    service = Mock()
    service.create.return_value = api.WindowsCredentialRead.model_validate(row)
    monkeypatch.setattr(api, "service", service)
    monkeypatch.setattr(api, "_audit", Mock())
    result = api.create_credential(7, WindowsCredentialCreate(device_id=7, username="admin", secret="plaintext-password"), db, user())
    db.commit.assert_called_once()
    assert "plaintext-password" not in result.model_dump_json()
    assert "encrypted_secret" not in result.model_dump_json()


def test_duplicate_create_returns_conflict_without_calling_encryption_service(monkeypatch):
    db = fake_db(device(), credential())
    service = Mock()
    monkeypatch.setattr(api, "service", service)
    with pytest.raises(HTTPException) as exc:
        api.create_credential(7, WindowsCredentialCreate(device_id=7, username="admin", secret="plaintext-password"), db, user())
    assert exc.value.status_code == 409
    service.create.assert_not_called()
    db.commit.assert_not_called()


def test_failed_create_rolls_back_and_hides_exception(monkeypatch):
    db = fake_db(device(), None)
    service = Mock()
    service.create.side_effect = RuntimeError("plaintext-password")
    monkeypatch.setattr(api, "service", service)
    with pytest.raises(HTTPException) as exc:
        api.create_credential(7, WindowsCredentialCreate(device_id=7, username="admin", secret="plaintext-password"), db, user())
    db.rollback.assert_called_once()
    assert exc.value.status_code == 500
    assert "plaintext-password" not in str(exc.value.detail)


def test_connection_test_records_success_without_secret(monkeypatch):
    row = credential()
    db = fake_db(device(), row)
    monkeypatch.setattr(api.service, "test_connection", Mock(return_value=WinRMConnectionDiagnostic(True, "success", "ok")))
    monkeypatch.setattr(api, "_audit", Mock())
    result = api.test_connection(7, db, user())
    assert result["ok"] is True
    assert "ciphertext" not in str(result)
    db.commit.assert_called_once()


def test_connection_test_failure_is_sanitized_and_not_read_only():
    route = next(route for route in router.routes if route.path.endswith("connection-test"))
    checker = next(dep.call for dep in route.dependant.dependencies if dep.call.__name__ == "checker")
    assert any(cell.cell_contents == "devices:update" for cell in checker.__closure__)
