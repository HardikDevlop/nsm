import asyncio
from types import SimpleNamespace

from backend import main


class FakeLease:
    ttl = 1

    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.renew_calls = 0

    def acquire(self):
        return next(self.outcomes, False)

    def renew(self):
        self.renew_calls += 1
        return True

    def release(self):
        return None


def test_supervisor_reacquires_and_starts_singleton_once(monkeypatch):
    calls = []

    async def fake_get_scheduler():
        calls.append("start")
        return object()

    async def fake_shutdown():
        calls.append("stop")

    monkeypatch.setattr(main, "get_polling_scheduler", fake_get_scheduler)
    monkeypatch.setattr(main, "shutdown_polling_scheduler", fake_shutdown)
    app = SimpleNamespace(
        state=SimpleNamespace(
            scheduler_lease=FakeLease([False, True]),
            scheduler_lease_owned=False,
            snmp_polling=None,
        )
    )

    async def run():
        task = asyncio.create_task(main._supervise_scheduler_lease(app))
        await asyncio.sleep(1.2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert calls == ["start"]
    assert app.state.scheduler_lease_owned is True


def test_lease_loss_clears_ownership_and_stops_scheduler(monkeypatch):
    calls = []

    async def fake_shutdown():
        calls.append("stop")

    monkeypatch.setattr(main, "shutdown_polling_scheduler", fake_shutdown)
    lease = FakeLease([])
    lease.renew = lambda: False
    app = SimpleNamespace(
        state=SimpleNamespace(
            scheduler_lease=lease,
            scheduler_lease_owned=True,
            snmp_polling=object(),
        )
    )

    async def run():
        task = asyncio.create_task(main._supervise_scheduler_lease(app))
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert calls == ["stop"]
    assert app.state.scheduler_lease_owned is False
    assert app.state.snmp_polling is None
