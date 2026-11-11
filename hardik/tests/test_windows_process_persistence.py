from types import SimpleNamespace
from uuid import uuid4

from backend.windows_monitoring import process_persistence


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1

    def add(self, row):
        self.parent = row

    def flush(self):
        return None

    def add_all(self, rows):
        list(rows)


def test_persistence_reuses_snapshot_collection_id(monkeypatch):
    collection_id = uuid4()
    captured = {}

    class Parent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.id = 1

    monkeypatch.setattr(process_persistence, "WindowsProcessSnapshot", Parent)
    db = FakeSession()
    snapshot = SimpleNamespace(collection_id=collection_id, collected_at=None, processes=(), cpu=())

    process_persistence.persist_process_snapshot(db, 361, snapshot)

    assert captured["collection_id"] == collection_id


def test_isolated_persistence_commits_without_request_session(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(process_persistence, "SessionLocal", lambda: session)
    monkeypatch.setattr(process_persistence, "persist_process_snapshot", lambda db, device_id, snapshot: None)

    assert process_persistence.persist_process_snapshot_isolated(361, SimpleNamespace()) is True
    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.closed == 1


def test_isolated_persistence_rolls_back_and_returns_failure(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(process_persistence, "SessionLocal", lambda: session)
    def fail(*_args, **_kwargs):
        raise RuntimeError("db failure")
    monkeypatch.setattr(process_persistence, "persist_process_snapshot", fail)

    assert process_persistence.persist_process_snapshot_isolated(361, SimpleNamespace()) is False
    assert session.commits == 0
    assert session.rollbacks == 1
    assert session.closed == 1
