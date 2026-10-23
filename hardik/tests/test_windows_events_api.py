from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api
from backend.windows_monitoring.events import SystemEvent, SystemEventCollection, SystemEventError


def user():
    return SimpleNamespace(role=SimpleNamespace(role_name="Super Admin", is_system_role=True, authority_level=100))


def test_system_event_routes_require_read_and_update_permissions():
    routes = {route.path: route for route in api.router.routes}
    assert "/windows/devices/{device_id}/events/system" in {route.path for route in api.router.routes}
    assert "/windows/devices/{device_id}/events/system/fetch" in {route.path for route in api.router.routes}
    for path in ("/windows/devices/{device_id}/events/system", "/windows/devices/{device_id}/events/system/fetch"):
        assert routes[path].dependant.dependencies


def test_system_event_get_is_bounded_and_reads_persistence(monkeypatch):
    row = SimpleNamespace(id=1, device_id=314, channel="System", record_id=42, time_created="t", event_id=7036, provider="SCM", level="Information", machine_name="WIN01", message="redacted", user_id=None, collected_at="c")
    db = Mock()
    monkeypatch.setattr(api, "_device", Mock())
    reader = Mock(return_value=[row])
    monkeypatch.setattr(api, "list_system_events", reader)

    result = api.get_system_events(314, event_ids=[7036], level="Information", offset=10, limit=25, db=db, user=user())

    reader.assert_called_once_with(db, 314, start_time=None, end_time=None, event_ids=[7036], level="Information", offset=10, limit=25)
    assert result["items"][0]["record_id"] == 42
    assert result["items"][0]["message"] == "redacted"


def test_system_event_post_collects_once_and_persists_result(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    connection = api._WindowsConnectionContext(
        device=SimpleNamespace(id=314, site_id=1),
        credential=SimpleNamespace(id=9),
        host="winhost",
        username="DOMAIN\\admin",
        password="secret-not-logged",
    )
    collection = SystemEventCollection((SystemEvent(42, "2026-10-17T12:00:00+00:00", 7036, "SCM", "Information", "WIN01", "message", None),), 1, False, "collected")
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    resolver = Mock(return_value=connection)
    monkeypatch.setattr(api, "_resolve_windows_connection", resolver)
    adapter_factory = Mock()
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", adapter_factory)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="ca.pem"))
    collector = Mock(return_value=collection)
    events = []
    saver = Mock(side_effect=lambda *args, **kwargs: events.append("commit") or 1)
    monkeypatch.setattr(api, "collect_system_events", collector)
    monkeypatch.setattr(api, "save_system_events", saver)
    audit = Mock(side_effect=lambda *args, **kwargs: events.append(("audit", kwargs)))
    monkeypatch.setattr(api, "record_audit_event", audit)

    result = api.fetch_system_events(314, event_ids=[], max_records=100, db=db, user=user())

    collector.assert_called_once()
    saver.assert_called_once()
    resolver.assert_called_once()
    adapter_factory.assert_called_once_with(
        "winhost", "DOMAIN\\admin", "secret-not-logged",
        port=5986, ca_trust_path="ca.pem", connect_timeout=10, operation_timeout=20,
    )
    assert result == {"device_id": 314, "channel": "System", "fetched_count": 1, "inserted_count": 1, "truncated": False, "collected_at": "collected"}
    assert events[0] == "commit"
    assert events[1][1] == {
        "actor": user(), "action": "EVENTS_FETCH", "resource_type": "windows_device",
        "resource_id": 314, "site_id": 1, "outcome": "success",
        "metadata": {"device_id": 314, "module": "events"},
    }
    assert audit.call_count == 1


def test_system_event_audit_failure_does_not_change_successful_response(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True
    connection = api._WindowsConnectionContext(
        device=SimpleNamespace(id=314, site_id=1), credential=SimpleNamespace(id=9),
        host="winhost", username="admin", password="secret-not-logged",
    )
    collection = SystemEventCollection((), 0, False, "collected")
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=connection))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock())
    monkeypatch.setattr(api, "collect_system_events", Mock(return_value=collection))
    monkeypatch.setattr(api, "save_system_events", Mock(return_value=0))
    monkeypatch.setattr(api, "record_audit_event", Mock(side_effect=RuntimeError("audit unavailable")))

    result = api.fetch_system_events(314, event_ids=[], max_records=100, db=db, user=user())

    assert result["fetched_count"] == 0
    assert result["inserted_count"] == 0
    db.rollback.assert_not_called()


def test_system_event_post_duplicate_fetch_returns_409_before_collection(monkeypatch):
    db = Mock()
    monkeypatch.setattr(api, "_fetch_lock", Mock(side_effect=HTTPException(status_code=409, detail="already in progress")))
    collector = Mock()
    monkeypatch.setattr(api, "collect_system_events", collector)

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_events(314, event_ids=[], max_records=100, db=db, user=user())

    assert exc.value.status_code == 409
    collector.assert_not_called()


def test_system_event_post_collection_failure_rolls_back(monkeypatch):
    db = Mock()
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=api._WindowsConnectionContext(
        device=SimpleNamespace(id=314, site_id=1), credential=SimpleNamespace(id=9),
        host="h", username="u", password="p",
    )))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock())
    monkeypatch.setattr(api, "collect_system_events", Mock(side_effect=SystemEventError("permission", "denied")))

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_events(314, event_ids=[], max_records=100, db=db, user=user())

    assert exc.value.status_code == 502
    db.rollback.assert_called_once()


@pytest.mark.parametrize("detail", ["Windows credential not found", "Stored Windows credential is unavailable"])
def test_system_event_post_preserves_credential_http_errors(monkeypatch, detail):
    db = Mock()
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    resolver = Mock(side_effect=HTTPException(status_code=404, detail=detail))
    monkeypatch.setattr(api, "_resolve_windows_connection", resolver)
    adapter = Mock()
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", adapter)
    collector = Mock()
    monkeypatch.setattr(api, "collect_system_events", collector)

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_events(314, event_ids=[], max_records=100, db=db, user=user())

    assert exc.value.status_code == 404
    assert exc.value.detail == detail
    adapter.assert_not_called()
    collector.assert_not_called()
    db.rollback.assert_called_once()


def test_system_event_post_does_not_construct_cim_client(monkeypatch):
    db = Mock()
    monkeypatch.setattr(api, "_fetch_lock", Mock())
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(return_value=api._WindowsConnectionContext(
        device=SimpleNamespace(id=314, site_id=1), credential=SimpleNamespace(id=9),
        host="h", username="u", password="p",
    )))
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(windows_ca_trust_path="ca"))
    monkeypatch.setattr(api, "WinRMHTTPSAdapter", Mock())
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(side_effect=AssertionError("CIM client must not be constructed")))
    monkeypatch.setattr(api, "collect_system_events", Mock(side_effect=SystemEventError("permission", "denied")))

    with pytest.raises(HTTPException) as exc:
        api.fetch_system_events(314, event_ids=[], max_records=100, db=db, user=user())

    assert exc.value.status_code == 502


def test_system_event_post_rejects_invalid_time_range_before_lock():
    db = Mock()
    lock = Mock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(api, "_fetch_lock", lock)
    try:
        with pytest.raises(HTTPException) as exc:
            api.fetch_system_events(314, start_time=datetime(2026, 1, 2, tzinfo=timezone.utc), end_time=datetime(2026, 1, 1, tzinfo=timezone.utc), db=db, user=user())
        assert exc.value.status_code == 400
        lock.assert_not_called()
    finally:
        monkeypatch.undo()
