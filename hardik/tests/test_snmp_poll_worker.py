import asyncio
import threading
from types import SimpleNamespace

from backend.services import snmp_polling


def test_poll_worker_keeps_blocking_persistence_off_loop_and_closes_sessions(monkeypatch):
    sessions = []
    main_thread = threading.get_ident()
    entered = threading.Event()
    release = threading.Event()

    class Session:
        def __init__(self):
            self.closed = False
            self.thread = threading.get_ident()
            sessions.append(self)
        def close(self):
            assert self.thread == threading.get_ident()
            self.closed = True

    class Poller:
        def __init__(self, db):
            self.db = db
        async def poll(self, job):
            assert threading.get_ident() != main_thread
            self.db.close()
            self.db = Session()
            entered.set()
            assert release.wait(2)
            return {'success': True}

    monkeypatch.setattr(snmp_polling, 'SessionLocal', Session)
    monkeypatch.setattr(snmp_polling, 'SNMPPoller', Poller)

    async def check():
        work = asyncio.create_task(asyncio.to_thread(snmp_polling.PollingScheduler._poll_in_worker, SimpleNamespace()))
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set()
        # The event loop can service another task while poll persistence blocks.
        release.set()
        assert await work == {'success': True}
    asyncio.run(check())
    assert len(sessions) == 2 and all(s.closed for s in sessions)


def test_start_returns_without_waiting_for_notification(monkeypatch):
    from fastapi import BackgroundTasks
    from backend.api import snmp_device_routes as routes

    async def get_scheduler():
        async def add_job(device_id, module, interval):
            return SimpleNamespace(device_id=device_id, module_name=module, enabled=True, interval_seconds=interval, status='running')
        return SimpleNamespace(add_job=add_job)

    monkeypatch.setattr(snmp_polling, 'get_polling_scheduler', get_scheduler)
    calls = []
    monkeypatch.setattr(routes, '_notify_monitoring_started', lambda *args: calls.append(args))
    background = BackgroundTasks()
    db = SimpleNamespace(query=lambda *_: SimpleNamespace(filter=lambda *_: SimpleNamespace(first=lambda: None)))
    response = asyncio.run(routes.start_module_monitoring(
        device_id=1, module='interfaces',
        payload=routes.MonitoringConfigRequest(module_name='interfaces', interval_seconds=60),
        background_tasks=background, db=db, _=None,
    ))
    assert response['status'] == 'running'
    assert not calls
    assert len(background.tasks) == 1


def test_monitoring_status_database_queries_run_off_api_loop(monkeypatch):
    main_thread = threading.get_ident()
    closed = []
    class Session:
        def __init__(self):
            assert threading.get_ident() != main_thread
        def query(self, *args):
            return self
        def filter(self, *args):
            return self
        def all(self):
            return []
        def close(self):
            closed.append(True)
    monkeypatch.setattr(snmp_polling, 'SessionLocal', Session)
    scheduler = snmp_polling.PollingScheduler()
    assert asyncio.run(scheduler.get_device_jobs(1)) == []
    assert closed == [True]
