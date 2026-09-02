import asyncio
import inspect
from backend.services.ha_scheduler import SchedulerLease

from backend.api import snmp_device_routes
from backend.services import snmp_polling


class _FakeScheduler:
    instances = []

    def __init__(self, worker_count):
        self.worker_count = worker_count
        self.started = 0
        self.stopped = 0
        self.__class__.instances.append(self)

    async def start(self):
        self.started += 1

    async def stop(self):
        self.stopped += 1


def test_scheduler_restart_is_singleton_and_reloads_after_shutdown(monkeypatch):
    monkeypatch.setattr(snmp_polling, "PollingScheduler", _FakeScheduler)
    original = snmp_polling._scheduler
    _FakeScheduler.instances = []
    snmp_polling._scheduler = None

    async def exercise():
        first, second = await asyncio.gather(
            snmp_polling.get_polling_scheduler(),
            snmp_polling.get_polling_scheduler(),
        )
        assert first is second
        assert len(_FakeScheduler.instances) == 1
        assert first.started == 1

        await snmp_polling.shutdown_polling_scheduler()
        assert first.stopped == 1

        restarted = await snmp_polling.get_polling_scheduler()
        assert restarted is not first
        assert len(_FakeScheduler.instances) == 2
        assert restarted.started == 1
        await snmp_polling.shutdown_polling_scheduler()

    try:
        asyncio.run(exercise())
    finally:
        snmp_polling._scheduler = original


def test_monitoring_crud_handlers_are_application_managed_coroutines():
    for handler in (
        snmp_device_routes.get_device_monitoring_configs,
        snmp_device_routes.start_module_monitoring,
        snmp_device_routes.stop_module_monitoring,
        snmp_device_routes.update_module_monitoring,
        snmp_device_routes.get_module_monitoring_status,
    ):
        assert inspect.iscoroutinefunction(handler)

def test_scheduler_lease_fails_closed_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr('backend.services.ha_scheduler._get_client', lambda: None)
    monkeypatch.setattr('backend.services.ha_scheduler.get_settings', lambda: type('S', (), {'environment':'production'})())
    assert SchedulerLease().acquire() is False
