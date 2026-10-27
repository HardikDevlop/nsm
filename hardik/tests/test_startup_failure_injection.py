from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import asyncio
from functools import wraps
import sys
import types

import pytest

# This suite never parses multipart requests. Keep collection isolated when a
# test-only environment lacks the optional parser package.
if "multipart" not in sys.modules:
    try:
        import multipart  # noqa: F401
    except ModuleNotFoundError:
        multipart = types.ModuleType("multipart")
        multipart.__version__ = "mock"
        multipart.multipart = types.ModuleType("multipart.multipart")
        multipart.multipart.parse_options_header = lambda value: (value, {})
        sys.modules["multipart"] = multipart
        sys.modules["multipart.multipart"] = multipart.multipart

from backend import main


def async_test(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapper


class FakeLease:
    def __init__(self, owned=True, acquire_error=None):
        self.owned = owned
        self.acquire_error = acquire_error
        self.ttl = 30
        self.release = Mock()

    def acquire(self):
        if self.acquire_error:
            raise self.acquire_error
        return self.owned

    def renew(self):
        return True


class FakeResource:
    def __init__(self, *, start_error=None, restore_error=None):
        self.start_error = start_error
        self.restore_error = restore_error
        self.start = AsyncMock(side_effect=start_error)
        self.stop = AsyncMock()
        self.shutdown = AsyncMock()
        self.restore_enabled_servers = AsyncMock(side_effect=restore_error)


class FakeSessionManager:
    def __init__(self, db):
        self.db = db

    def list_active_sessions(self):
        return []

    def reconcile_stale_sessions_on_startup(self):
        return 0

    def disconnect_session(self, *_args, **_kwargs):
        pass


def _install_mocks(monkeypatch, *, flow=False, syslog=False, lease=None,
                   scheduler_error=None, linux_error=None, icmp_error=None):
    app = SimpleNamespace(state=SimpleNamespace())
    main.settings = SimpleNamespace(
        flow_enabled=flow,
        flow_bind_host="127.0.0.1",
        flow_ipfix_port=2055,
        flow_sflow_port=6343,
        syslog_enabled=syslog,
        syslog_bind_host="127.0.0.1",
        syslog_udp_port=5514,
        syslog_tcp_port=6514,
        syslog_enable_udp=True,
        syslog_enable_tcp=True,
    )

    async def direct_to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", direct_to_thread)
    monkeypatch.setattr(main.Base.metadata, "create_all", Mock())
    monkeypatch.setattr(main, "run_migrations", Mock())
    db_context = Mock()
    db_context.__enter__ = Mock(return_value=Mock())
    db_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(main, "SessionLocal", Mock(return_value=db_context))
    monkeypatch.setattr(main, "seed_rbac", Mock())
    monkeypatch.setattr(main, "seed_ouis_and_products", Mock())
    monkeypatch.setattr(main, "reconcile_cmdb", Mock())

    flow_ingest_resource = FakeResource()
    flow_receiver_resource = FakeResource()
    syslog_resource = FakeResource(start_error=RuntimeError("syslog failure") if syslog else None)
    monkeypatch.setattr(main, "FlowIngestService", Mock(return_value=flow_ingest_resource))
    monkeypatch.setattr(main, "FlowReceiver", Mock(return_value=flow_receiver_resource))
    monkeypatch.setattr(main, "SyslogIngestionService", Mock(return_value=syslog_resource))

    lease = lease or FakeLease()
    monkeypatch.setattr(main, "SchedulerLease", Mock(return_value=lease))
    scheduler = object()

    async def get_scheduler():
        if scheduler_error:
            raise scheduler_error
        return scheduler

    monkeypatch.setattr(main, "get_polling_scheduler", get_scheduler)
    monkeypatch.setattr(main, "shutdown_polling_scheduler", AsyncMock())
    monkeypatch.setattr(main, "set_report_scheduler", Mock())
    monkeypatch.setattr(main, "restore_report_schedules", Mock())
    monkeypatch.setattr(main, "register_daily_report_job", Mock())
    monkeypatch.setattr(main, "_supervise_scheduler_lease", AsyncMock())

    linux_resource = FakeResource(restore_error=linux_error)
    monkeypatch.setattr(main, "LinuxMonitoringScheduler", Mock(return_value=linux_resource))

    def restore_enabled_devices():
        if icmp_error:
            raise icmp_error

    engine = SimpleNamespace(
        restore_enabled_devices=restore_enabled_devices,
        shutdown=lambda: None,
    )
    monkeypatch.setattr(main, "get_engine", Mock(return_value=engine))
    monkeypatch.setattr(main, "shutdown_snmp_workers", Mock())
    monkeypatch.setattr(main, "SessionManager", FakeSessionManager)
    return app, flow_ingest_resource, syslog_resource, linux_resource, lease


@async_test
async def test_flow_initialization_failure_cleans_flow_resources(monkeypatch):
    app, flow, _syslog, _linux, _lease = _install_mocks(monkeypatch, flow=True)
    flow.start.side_effect = RuntimeError("flow failure")
    with pytest.raises(RuntimeError, match="flow failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    flow.stop.assert_awaited_once()


@async_test
async def test_flow_receiver_initialization_failure_cleans_ingest_and_receiver(monkeypatch):
    app, flow, _syslog, _linux, _lease = _install_mocks(monkeypatch, flow=True)
    receiver = main.FlowReceiver.return_value
    receiver.start.side_effect = RuntimeError("flow receiver failure")
    with pytest.raises(RuntimeError, match="flow receiver failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    flow.stop.assert_awaited_once()
    receiver.stop.assert_awaited_once()


@async_test
async def test_syslog_failure_is_safe_and_stopped_on_shutdown(monkeypatch):
    app, _flow, syslog, _linux, _lease = _install_mocks(
        monkeypatch, syslog=True, scheduler_error=RuntimeError("later startup failure")
    )
    with pytest.raises(RuntimeError, match="later startup failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    syslog.stop.assert_awaited_once()


@async_test
async def test_unowned_lease_failure_does_not_release_lease(monkeypatch):
    lease = FakeLease(owned=False, acquire_error=RuntimeError("lease failure"))
    app, _flow, _syslog, _linux, _lease = _install_mocks(monkeypatch, lease=lease)
    with pytest.raises(RuntimeError, match="lease failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    lease.release.assert_not_called()


@async_test
async def test_snmp_scheduler_failure_releases_owned_lease_once(monkeypatch):
    lease = FakeLease(owned=True)
    app, _flow, _syslog, _linux, _lease = _install_mocks(monkeypatch, lease=lease, scheduler_error=RuntimeError("snmp failure"))
    with pytest.raises(RuntimeError, match="snmp failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    lease.release.assert_called_once()
    main.shutdown_polling_scheduler.assert_awaited_once()


@async_test
async def test_linux_restoration_failure_cleans_scheduler_and_lease(monkeypatch):
    lease = FakeLease(owned=True)
    app, _flow, _syslog, linux, _lease = _install_mocks(monkeypatch, lease=lease, linux_error=RuntimeError("linux failure"))
    with pytest.raises(RuntimeError, match="linux failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    linux.shutdown.assert_awaited_once()
    lease.release.assert_called_once()
    main.shutdown_polling_scheduler.assert_awaited_once()


@async_test
async def test_icmp_restoration_failure_cleans_scheduler_and_lease(monkeypatch):
    lease = FakeLease(owned=True)
    app, _flow, _syslog, linux, _lease = _install_mocks(monkeypatch, lease=lease, icmp_error=RuntimeError("icmp failure"))
    with pytest.raises(RuntimeError, match="icmp failure"):
        async with main.lifespan(app):
            pytest.fail("startup unexpectedly yielded")
    linux.shutdown.assert_awaited_once()
    lease.release.assert_called_once()
    main.shutdown_polling_scheduler.assert_awaited_once()


@async_test
async def test_successful_startup_shutdown_preserves_normal_cleanup(monkeypatch):
    app, flow, syslog, linux, lease = _install_mocks(monkeypatch, flow=True, syslog=False)
    async with main.lifespan(app):
        assert app.state.snmp_polling is not None
    flow.stop.assert_awaited_once()
    linux.shutdown.assert_awaited_once()
    lease.release.assert_called_once()
