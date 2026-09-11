from __future__ import annotations

from types import SimpleNamespace
import time

import pytest

from backend.services import alerting, snmp_polling
from backend.services.alerting import NotificationIntent
from backend.services.snmp_polling import PollJob, PollingScheduler


class _Query:
    def __init__(self, value):
        self.value = value
    def filter(self, *args):
        return self
    def first(self):
        return self.value


class _Session:
    def __init__(self, config=None, events=None, fail_commit=False):
        self.config = config
        self.events = events if events is not None else []
        self.fail_commit = fail_commit
        self.rollbacks = 0
    def query(self, model):
        return _Query(self.config)
    def commit(self):
        self.events.append("poll_commit" if self.config is not None else "delivery_commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")
    def rollback(self):
        self.rollbacks += 1
    def close(self):
        pass


def _config():
    return SimpleNamespace(
        id=99, device_id=7, module_name="cpu", interval_seconds=60,
        enabled=True, status="running", error_message=None,
        last_poll_at=None, next_poll_at=None,
    )


def _intent():
    return NotificationIntent(1, 2, "High CPU", "Value 90%", "warning", "open", "ops@example.com")


def _job():
    return PollJob(7, "cpu", "cpu", 60, 99)


def test_poll_commits_before_delivery_and_payload_is_detached(monkeypatch):
    events = []
    initial = _Session(events=events)
    transaction = _Session(_config(), events)
    delivery = _Session(events=events)
    sessions = iter([initial, delivery])

    class Poller:
        def __init__(self, db):
            self.db = db
        async def poll(self, job, *, commit=True):
            self.db = transaction
            return {
                "success": True,
                "_persistence_pending": True,
                "_notification_intents": [_intent()],
            }

    def deliver(db, intents):
        time.sleep(0.03)
        events.append(("deliver", intents[0]))

    monkeypatch.setattr(snmp_polling, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(snmp_polling, "SNMPPoller", Poller)
    monkeypatch.setattr(alerting, "deliver_notification_intents", deliver)
    PollingScheduler._poll_in_worker(_job())
    assert events[0] == "poll_commit"
    assert events[1][0] == "deliver"
    assert events[1][1].title == "High CPU"
    assert events[2] == "delivery_commit"


def test_transaction_failure_prevents_delivery(monkeypatch):
    events = []
    initial = _Session(events=events)
    transaction = _Session(_config(), events, fail_commit=True)

    class Poller:
        def __init__(self, db):
            self.db = db
        async def poll(self, job, *, commit=True):
            self.db = transaction
            return {"success": True, "_persistence_pending": True, "_notification_intents": [_intent()]}

    monkeypatch.setattr(snmp_polling, "SessionLocal", lambda: initial)
    monkeypatch.setattr(snmp_polling, "SNMPPoller", Poller)
    monkeypatch.setattr(alerting, "deliver_notification_intents", lambda *_: events.append("deliver"))
    with pytest.raises(RuntimeError, match="commit failed"):
        PollingScheduler._poll_in_worker(_job())
    assert "deliver" not in events
    assert transaction.rollbacks == 1


def test_delivery_failure_does_not_rollback_committed_poll(monkeypatch):
    events = []
    initial = _Session(events=events)
    transaction = _Session(_config(), events)
    delivery = _Session(events=events)
    sessions = iter([initial, delivery])

    class Poller:
        def __init__(self, db):
            self.db = db
        async def poll(self, job, *, commit=True):
            self.db = transaction
            return {"success": True, "_persistence_pending": True, "_notification_intents": [_intent()]}

    monkeypatch.setattr(snmp_polling, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(snmp_polling, "SNMPPoller", Poller)
    monkeypatch.setattr(
        alerting, "deliver_notification_intents",
        lambda *_: (_ for _ in ()).throw(RuntimeError("smtp failed")),
    )
    result = PollingScheduler._poll_in_worker(_job())
    assert result["success"] is True
    assert events == ["poll_commit"]
    assert transaction.rollbacks == 0
    assert delivery.rollbacks == 1
