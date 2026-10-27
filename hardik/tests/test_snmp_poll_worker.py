import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace

from backend.services import snmp_polling


def test_poll_worker_keeps_blocking_persistence_off_loop_and_closes_sessions(monkeypatch):
    sessions = []
    main_thread = threading.get_ident()
    entered = threading.Event()

    class Session:
        def __init__(self):
            self.closed = False
            self.thread = threading.get_ident()
            sessions.append(self)

        def query(self, *args):
            return self

        def filter(self, *args):
            return self

        def first(self):
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

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
            # Keep the mocked persistence interval bounded while ensuring
            # this blocking work remains on the worker thread.
            time.sleep(0.05)
            return {'success': True}

    monkeypatch.setattr(snmp_polling, 'SessionLocal', Session)
    monkeypatch.setattr(snmp_polling, 'SNMPPoller', Poller)

    async def check():
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-poll-worker") as executor:
            work = loop.run_in_executor(
                executor,
                snmp_polling.PollingScheduler._poll_in_worker,
                SimpleNamespace(config_id=0),
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            # The event loop serviced the readiness loop while worker
            # persistence was blocked, proving the operation did not run on
            # the API loop. The context manager explicitly joins the worker.
            assert await asyncio.wait_for(work, timeout=2) == {
                'success': True,
                '_reschedule': None,
            }
    asyncio.run(check())
    # _poll_in_worker owns the initial session, the poller's replacement
    # session, and the transaction session used for scheduler metadata.
    assert len(sessions) == 3 and all(s.closed for s in sessions)


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
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-db-worker")

    async def test_to_thread(func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, func, *args)

    monkeypatch.setattr(snmp_polling.asyncio, "to_thread", test_to_thread)
    try:
        async def check():
            return await asyncio.wait_for(scheduler.get_device_jobs(1), timeout=2)

        assert asyncio.run(check()) == []
    finally:
        executor.shutdown(wait=True)
    assert closed == [True]
