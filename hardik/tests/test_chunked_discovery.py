import threading
import time
from pathlib import Path
from fastapi import BackgroundTasks

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.services import chunked_discovery
from backend.api import discovery_routes
from backend.database.session import Base
import backend.models  # noqa: F401


def _job(job_id="large-subnet"):
    return chunked_discovery.ScanJob(
        job_id=job_id,
        network_range="192.0.2.0/24",
        site_id=None,
        chunk_size=100,
    )


def test_large_subnet_is_deduplicated_chunked_and_bounded(monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_enrich(ip, modules, ports, timeout_ms):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.005)
        with lock:
            active -= 1
        return {"ip": ip}

    monkeypatch.setattr(chunked_discovery, "_ping", lambda ip, timeout_ms: True)
    monkeypatch.setattr(chunked_discovery, "_enrich_host", fake_enrich)
    monkeypatch.setattr(chunked_discovery, "_lookup_mac", lambda ip: None)
    monkeypatch.setattr("vendor_map.lookup_vendor", lambda mac: "Example")

    ips = [f"192.0.2.{index}" for index in range(1, 61)]
    ips.insert(30, ips[0])
    job = _job()
    chunked_discovery._execute_chunked_scan(
        job, ips, [], 10, "public", True, False, False, ["ip_discovery"]
    )

    assert job.status == "completed"
    assert job.total_ips == 60
    assert job.chunks_total == 3
    assert job.chunks_completed == 3
    assert job.ips_scanned == 60
    assert len(job.discovered) == 60
    assert len({device["ip_address"] for device in job.discovered}) == 60
    assert job.chunk_size == 25
    assert peak <= 8


def test_chunked_scan_cancellation_stops_before_work(monkeypatch):
    job = _job("cancel-before-start")
    job.cancel()
    called = []
    monkeypatch.setattr(chunked_discovery, "_ping", lambda ip, timeout_ms: called.append(ip) or True)

    chunked_discovery._execute_chunked_scan(
        job, ["192.0.2.1", "192.0.2.2"], [], 10, "public", True, False, False, None
    )

    assert job.status == "cancelled"
    assert job.discovered == []
    assert called == []


def test_discovery_support_modules_are_resolved_from_project_root():
    project_root = Path(discovery_routes.__file__).resolve().parents[2]
    assert str(project_root) in discovery_routes.sys.path
    from network_range import NetworkRange

    assert NetworkRange("127.0.0.1/32", max_hosts=1).expand() == ["127.0.0.1"]


def test_add_discovered_devices_persists_new_device(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr("backend.database.session.SessionLocal", session_factory)

    payload = discovery_routes.AddDevicesRequest(
        devices=[{"ip_address": "192.0.2.10", "hostname": "test-device", "status": "online"}],
        discovery_source="icmp",
    )
    result = discovery_routes.add_discovered_devices(payload, BackgroundTasks())

    assert result["added_count"] == 1
    assert result["skipped_count"] == 0
    with session_factory() as db:
        assert db.query(backend.models.Device).filter_by(ip_address="192.0.2.10").count() == 1


def test_add_discovered_devices_keeps_inventory_when_info_alert_fails(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr("backend.database.session.SessionLocal", session_factory)
    monkeypatch.setattr(
        "backend.services.alerting.create_device_added_alert",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("optional alert failed")),
    )

    payload = discovery_routes.AddDevicesRequest(
        devices=[{"ip_address": "192.0.2.11", "hostname": "test-device-2", "status": "online"}],
        discovery_source="icmp",
    )
    result = discovery_routes.add_discovered_devices(payload, BackgroundTasks())

    assert result["added_count"] == 1
    with session_factory() as db:
        assert db.query(backend.models.Device).filter_by(ip_address="192.0.2.11").count() == 1


def test_bulk_add_defers_device_added_notifications(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr("backend.database.session.SessionLocal", session_factory)

    notification_flags = []

    def fake_create_alert(*args, **kwargs):
        notification_flags.append(kwargs.get("notify"))
        return None

    monkeypatch.setattr("backend.services.alerting.create_device_added_alert", fake_create_alert)

    class BackgroundTasks:
        def __init__(self):
            self.tasks = []

        def add_task(self, function, *args, **kwargs):
            self.tasks.append((function, args, kwargs))

    tasks = BackgroundTasks()
    payload = discovery_routes.AddDevicesRequest(
        devices=[
            {"ip_address": "192.0.2.20", "hostname": "device-20", "status": "online"},
            {"ip_address": "192.0.2.21", "hostname": "device-21", "status": "online"},
        ],
        discovery_source="icmp",
    )

    result = discovery_routes.add_discovered_devices(payload, tasks)

    assert result["added_count"] == 2
    assert notification_flags == [False, False]
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0][0].__name__ == "_send_device_added_notifications"
