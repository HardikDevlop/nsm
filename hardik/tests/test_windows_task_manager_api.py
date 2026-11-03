from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.windows_monitoring import api


ROUTES = {
    "processes": ("/windows/devices/{device_id}/processes", "devices:read", api.get_process_snapshot),
    "processes_fetch": ("/windows/devices/{device_id}/processes/fetch", "devices:update", api.fetch_process_snapshot),
}


def test_all_task_manager_routes_are_registered_with_expected_rbac():
    routes = {route.path: route for route in api.router.routes}
    for path, permission, _ in ROUTES.values():
        assert path in routes
        dependency_node = next(node for node in routes[path].dependant.dependencies if node.call.__name__ == "checker")
        dependency = dependency_node.call
        assert any(cell.cell_contents == permission for cell in (dependency.__closure__ or ()))
        assert dependency_node.dependencies[0].call.__name__ == "get_current_user"


@pytest.mark.parametrize("name", ROUTES)
def test_authorized_device_returns_sanitized_501_without_collection(name, monkeypatch):
    _path, _permission, handler = ROUTES[name]
    device = SimpleNamespace(id=7, site_id=10)
    monkeypatch.setattr(api, "_windows_device", Mock(return_value=device))
    monkeypatch.setattr(api, "WindowsCIMClient", Mock(side_effect=AssertionError("CIM must not be invoked")))
    monkeypatch.setattr(api, "_resolve_windows_connection", Mock(side_effect=AssertionError("credentials must not be resolved")))

    if name == "processes":
        result = handler(7, Mock(), SimpleNamespace(), 50, 0)
        assert result["status"] == "no_snapshot"
    else:
        snapshot = SimpleNamespace(device_id=7, processes=(), cpu=(), status="error", reason="busy", collected_at=None, age_seconds=0)
        monkeypatch.setattr(api, "_metric_client", Mock(return_value=(Mock(), SimpleNamespace(id=9))))
        monkeypatch.setattr(api.process_snapshot_service, "snapshot", Mock(return_value=snapshot))
        result = handler(7, Mock(), SimpleNamespace(), 50, 0)
        assert result["status"] == "busy"
    api._windows_device.assert_called_once()


@pytest.mark.parametrize("name", ROUTES)
def test_missing_or_unauthorized_or_non_windows_device_is_rejected_before_placeholder(name, monkeypatch):
    _path, _permission, handler = ROUTES[name]
    for detail in ("Device not found", "Device not found"):
        monkeypatch.setattr(api, "_windows_device", Mock(side_effect=HTTPException(status_code=404, detail=detail)))
        with pytest.raises(HTTPException) as exc:
            handler(99, Mock(), SimpleNamespace())
        assert exc.value.status_code == 404
        assert exc.value.detail == "Device not found"


@pytest.mark.parametrize("name", ROUTES)
def test_authorization_precedes_any_future_cache_or_collector_access(name, monkeypatch):
    _path, _permission, handler = ROUTES[name]
    cache_access = Mock(side_effect=AssertionError("cache must not be accessed"))
    collector = Mock(side_effect=AssertionError("collector must not be invoked"))
    credentials = Mock(side_effect=AssertionError("credentials must not be resolved"))
    monkeypatch.setattr(api, "_windows_device", Mock(side_effect=HTTPException(status_code=404, detail="Device not found")))

    with pytest.raises(HTTPException) as exc:
        handler(99, Mock(), SimpleNamespace())

    assert exc.value.status_code == 404
    cache_access.assert_not_called()
    collector.assert_not_called()
    credentials.assert_not_called()
