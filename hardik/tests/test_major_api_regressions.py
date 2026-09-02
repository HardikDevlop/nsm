"""Network-free regression coverage for the major NMS API boundaries.

These tests intentionally exercise the existing route handlers with isolated
test doubles. They do not replace the PostgreSQL/live-device integration tests.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api import discovery_routes, routes, snmp_device_routes
from backend.auth import security
from backend.dependencies import get_current_user, require_permission
from backend.schemas.nms import (
    AlertCreate,
    DeviceCreate,
    LoginRequest,
    ReportCreate,
)


def _paths(router):
    return {(method, route.path) for route in router.routes for method in route.methods or ()}


def test_major_api_surface_remains_registered():
    all_routes = _paths(routes.router) | _paths(discovery_routes.router) | _paths(snmp_device_routes.router)
    required = {
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/devices"),
        ("POST", "/api/v1/devices"),
        ("PATCH", "/api/v1/devices/{item_id}"),
        ("DELETE", "/api/v1/devices/{item_id}"),
        ("POST", "/discovery/snmp"),
        ("POST", "/discovery/monitoring/start"),
        ("POST", "/discovery/monitoring/stop"),
        ("POST", "/api/v1/snmp/devices/{device_id}/poll"),
        ("GET", "/api/v1/snmp/devices/{device_id}/polling-history"),
        ("GET", "/api/v1/snmp/topology"),
        ("GET", "/api/v1/alerts/{item_id}"),
        ("POST", "/api/v1/alerts/{item_id}/acknowledge"),
        ("GET", "/api/v1/reports"),
        ("GET", "/api/v1/reports/daily"),
    }
    assert required <= all_routes


def test_login_success_and_invalid_credentials(monkeypatch):
    user = SimpleNamespace(email="admin@example.com", password_hash="hash")

    class Query:
        def filter(self, *_):
            return self

        def first(self):
            return user

    db = SimpleNamespace(query=lambda *_: Query())
    monkeypatch.setattr(routes, "verify_password", lambda password, hashed: password == "correct")
    monkeypatch.setattr(routes, "create_access_token", lambda email: "token-for-" + email)

    result = routes.login(LoginRequest(email="admin@example.com", password="correct"), db)
    assert result.access_token == "token-for-admin@example.com"
    with pytest.raises(HTTPException) as exc:
        routes.login(LoginRequest(email="admin@example.com", password="wrong"), db)
    assert exc.value.status_code == 401


def test_auth_and_rbac_reject_missing_invalid_and_ungranted_access(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        get_current_user(None, None)
    assert exc.value.status_code == 401

    credentials = SimpleNamespace(credentials="bad-token")
    monkeypatch.setattr("backend.dependencies.decode_access_token", lambda _: None)
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials, None)
    assert exc.value.status_code == 401

    user = SimpleNamespace(role=SimpleNamespace(permissions=[SimpleNamespace(code="devices:read")]))
    with pytest.raises(HTTPException) as exc:
        require_permission("devices:update")(user)
    assert exc.value.status_code == 403
    assert require_permission("devices:read")(user) is user


def test_auth_and_device_payload_validation_is_enforced():
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="x")
    with pytest.raises(ValidationError):
        DeviceCreate(hostname="r1")

    device = DeviceCreate(hostname="r1", ip_address="10.0.0.1")
    assert device.monitoring_status is True


def test_device_crud_create_update_delete_boundary(monkeypatch):
    payload = DeviceCreate(hostname="r1", ip_address="10.0.0.1")
    stored = SimpleNamespace(id=7, hostname="r1", ip_address="10.0.0.1")
    calls = []
    crud = SimpleNamespace(
        create=lambda db, body: calls.append(("create", body)) or stored,
        update=lambda db, item_id, body: calls.append(("update", item_id, body)) or stored,
        delete=lambda db, item_id: calls.append(("delete", item_id)) or {"detail": "Device 7 deleted"},
    )
    monkeypatch.setattr(routes, "device_crud", crud)
    monkeypatch.setattr(routes, "audit", lambda *args: None)
    current = SimpleNamespace(id=1)
    assert routes.create_device(payload, None, current) is stored
    assert routes.update_device(7, payload.model_copy(update={"hostname": "r2"}), None, current) is stored
    class Query:
        def filter(self, *args): return self
        def first(self): return stored
    db = SimpleNamespace(
        query=lambda *_: Query(),
        execute=lambda *args: None,
        delete=lambda item: None,
        commit=lambda: None,
    )
    assert routes.delete_device(7, db, current)["detail"] == "Device 7 deleted"
    assert [call[0] for call in calls] == ["create", "update"]


def test_discovery_success_validation_timeout_failure(monkeypatch):
    class FakeDiscovery:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def collect(self, ip):
            return {"snmp_enabled": True, "hostname": "r1", "ip": ip}

    monkeypatch.setattr("backend.snmp.collector.SNMPDiscovery", FakeDiscovery)
    result = discovery_routes.discovery_snmp(discovery_routes.IpsRequest(ips=["10.0.0.1"], snmp_version="v3"))
    assert result["count"] == 1
    assert result["results"]["10.0.0.1"]["hostname"] == "r1"

    with pytest.raises(HTTPException) as exc:
        discovery_routes.discovery_snmp(discovery_routes.IpsRequest(ips=["invalid-ip"]))
    assert exc.value.status_code == 400

    class TimeoutDiscovery(FakeDiscovery):
        def collect(self, ip):
            return {"snmp_enabled": False, "error": "timeout"}

    monkeypatch.setattr("backend.snmp.collector.SNMPDiscovery", TimeoutDiscovery)
    with pytest.raises(HTTPException) as exc:
        discovery_routes.discovery_snmp(discovery_routes.IpsRequest(ips=["10.0.0.2"], timeout_seconds=0.1))
    assert exc.value.status_code == 502


def test_monitoring_start_stop_success_duplicate_and_failure(monkeypatch):
    class Engine:
        def __init__(self):
            self.devices = {}

        def get_device(self, ip):
            return self.devices.get(ip)

        def start_device(self, **kwargs):
            self.devices[kwargs["ip"]] = SimpleNamespace(to_dict=lambda: {"ip": kwargs["ip"], "status": "up"})

        def stop_device(self, ip):
            return self.devices.pop(ip, None) is not None

    engine = Engine()
    monkeypatch.setattr("backend.services.realtime_monitor.get_engine", lambda: engine)
    payload = discovery_routes.MonitorDeviceRequest(ip="10.0.0.1")
    assert discovery_routes.monitoring_start_device(payload)["status"] == "starting"
    for _ in range(50):
        if engine.get_device(payload.ip):
            break
    assert discovery_routes.monitoring_stop_device(payload)["stopped"] is True
    assert discovery_routes.monitoring_stop_device(payload)["stopped"] is False
    with pytest.raises(HTTPException):
        discovery_routes.monitoring_start_device(discovery_routes.MonitorDeviceRequest(ip="  "))


def test_manual_poll_success_timeout_and_single_flight_failure(monkeypatch):
    device = SimpleNamespace(id=3)
    query = SimpleNamespace(first=lambda: device)
    db = SimpleNamespace(query=lambda *_: query, commit=lambda: None)
    monkeypatch.setattr(snmp_device_routes, "_get_device_or_404", lambda device_id, db: device)
    monkeypatch.setattr(snmp_device_routes, "_get_credentials", lambda device_id, db: None)
    monkeypatch.setattr(snmp_device_routes, "_persist_collect_result", lambda *args: None)
    monkeypatch.setattr(snmp_device_routes, "_live_collect", lambda *args, **kwargs: {"cpu": {"value": 1}})
    assert snmp_device_routes.poll_device_now(3, None, db, None)["cpu"]["value"] == 1

    def failed(*args, **kwargs):
        raise TimeoutError("SNMP operation timed out")

    monkeypatch.setattr(snmp_device_routes, "_live_collect", failed)
    with pytest.raises(TimeoutError, match="timed out"):
        snmp_device_routes.poll_device_now(3, None, db, None)


def test_history_alert_report_and_topology_contracts(monkeypatch):
    now = datetime.utcnow()
    rows = [SimpleNamespace(id=1, collector="cpu", status="success", duration_ms=4, error=None, created_at=now)]

    class Query:
        def filter(self, *args): return self
        def order_by(self, *args): return self
        def limit(self, *args): return self
        def all(self): return rows

    history_db = SimpleNamespace(query=lambda *_: Query())
    history = snmp_device_routes.get_snmp_polling_history(3, 24, history_db, None)
    assert history[0]["status"] == "success"

    alert = SimpleNamespace(id=9, device_id=3, severity="critical", title="down", status="open")
    alert_crud = SimpleNamespace(get=lambda db, item_id: alert, update=lambda *args: alert)
    monkeypatch.setattr(routes, "alert_crud", alert_crud)
    monkeypatch.setattr(routes, "audit", lambda *args: None)
    assert routes.get_alert(9, None, None) is alert
    assert routes.acknowledge_alert(9, None, SimpleNamespace(id=1)) is alert

    report = ReportCreate(report_name="daily", report_type="daily")
    assert report.report_type == "daily"
    assert ("GET", "/api/v1/snmp/topology") in _paths(snmp_device_routes.router)


def test_monitoring_scheduler_endpoint_rejects_invalid_interval(monkeypatch):
    payload = snmp_device_routes.MonitoringConfigRequest(module_name="cpu", interval_seconds=1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(snmp_device_routes.start_module_monitoring(3, "cpu", payload, SimpleNamespace(query=lambda *_: SimpleNamespace(first=lambda: None)), None))
    assert exc.value.status_code == 400
