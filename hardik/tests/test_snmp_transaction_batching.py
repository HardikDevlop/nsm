from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services import snmp_polling
from backend.services.snmp_polling import PollJob, PollingScheduler


class _Query:
    def __init__(self, config):
        self.config = config
    def filter(self, *args):
        return self
    def first(self):
        return self.config


class _Session:
    def __init__(self, config, fail_commit=False):
        self.config = config
        self.fail_commit = fail_commit
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0
        self.closed = False
    def query(self, model):
        return _Query(self.config)
    def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")
    def flush(self):
        self.flushes += 1
    def rollback(self):
        self.rollbacks += 1
    def close(self):
        self.closed = True


def _job():
    return PollJob(7, "cpu", "cpu", 60, 99)


def _config():
    return SimpleNamespace(
        id=99, device_id=7, module_name="cpu", interval_seconds=60,
        enabled=True, status="running", error_message=None,
        last_poll_at=None, next_poll_at=None,
    )


def test_normal_success_uses_one_final_commit(monkeypatch):
    initial = _Session(None)
    transaction = _Session(_config())
    sessions = iter([initial])

    class Poller:
        def __init__(self, db):
            self.db = db
        async def poll(self, job, *, commit=True):
            assert commit is False
            self.db.close()
            self.db = transaction
            return {
                "success": True, "supported": True, "duration_ms": 10,
                "_persistence_pending": True,
            }

    monkeypatch.setattr(snmp_polling, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(snmp_polling, "SNMPPoller", Poller)
    result = PollingScheduler._poll_in_worker(_job())
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    assert result["_reschedule"]["config_id"] == 99
    assert transaction.config.status == "running"


def test_commit_failure_rolls_back_and_propagates(monkeypatch):
    initial = _Session(None)
    transaction = _Session(_config(), fail_commit=True)

    class Poller:
        def __init__(self, db):
            self.db = db
        async def poll(self, job, *, commit=True):
            self.db = transaction
            return {"success": True, "_persistence_pending": True}

    monkeypatch.setattr(snmp_polling, "SessionLocal", lambda: initial)
    monkeypatch.setattr(snmp_polling, "SNMPPoller", Poller)
    with pytest.raises(RuntimeError, match="commit failed"):
        PollingScheduler._poll_in_worker(_job())
    assert transaction.commits == 1
    assert transaction.rollbacks == 1


def test_persistence_helper_rolls_back_and_raises(monkeypatch):
    session = _Session(None)
    poller = snmp_polling.SNMPPoller(session)

    async def fail_history(*args, **kwargs):
        raise RuntimeError("history failed")

    monkeypatch.setattr(poller, "_persist_history", fail_history)
    with pytest.raises(RuntimeError, match="history failed"):
        import asyncio
        asyncio.run(poller._persist_results(_job(), {}, True, commit=False))
    assert session.commits == 0
    assert session.rollbacks == 1
