from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.windows_monitoring import api
from backend.windows_monitoring.process_snapshot_service import ProcessSnapshot


def _snapshot(collection_id, device_id=1):
    return ProcessSnapshot(
        device_id=device_id,
        processes=(SimpleNamespace(process_id=10, session_id=1, creation_time="created"),),
        cpu=(),
        collected_monotonic_seconds=0.0,
        age_seconds=0.0,
        status="ok",
        collection_id=collection_id,
    )


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = ()

    def filter(self, *expressions):
        self.filters = expressions
        for expression in expressions:
            key = getattr(getattr(expression, "left", None), "key", None)
            value = getattr(getattr(expression, "right", None), "value", None)
            operator = getattr(getattr(expression, "operator", None), "__name__", "")
            if key == "collection_id":
                self.rows = [row for row in self.rows if row.collection_id == value]
            elif key == "device_id":
                self.rows = [row for row in self.rows if row.device_id == value]
            elif key == "expires_at" and operator == "gt":
                self.rows = [row for row in self.rows if row.expires_at > value]
        return self

    def order_by(self, *_expressions):
        return self

    def limit(self, _count):
        return self

    def all(self):
        return self.rows


class Database:
    def __init__(self, rows):
        self.query_result = Query(rows)

    def query(self, _model):
        return self.query_result


def _submission(collection_id, device_id=1, *, expires_at=None):
    return SimpleNamespace(
        collection_id=collection_id,
        device_id=device_id,
        expires_at=expires_at or datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=30),
        collected_at=datetime.now(timezone.utc),
        evidence={"collection_id": str(collection_id)},
    )


def _classification(processes, evidence, *, now):
    del evidence, now
    return tuple(SimpleNamespace(**vars(process), classification="app") for process in processes)


def test_exact_collection_and_device_are_required(monkeypatch):
    collection_id = uuid4()
    db = Database([_submission(collection_id)])
    monkeypatch.setattr(api, "classify_visible_processes", _classification)

    result = api._apply_helper_evidence(db, _snapshot(collection_id))

    assert result.processes[0].classification == "app"
    assert any(getattr(expression.left, "key", None) == "collection_id" for expression in db.query_result.filters)
    assert any(getattr(expression.left, "key", None) == "device_id" for expression in db.query_result.filters)


@pytest.mark.parametrize(
    "snapshot_id, rows, device_id",
    [
        (uuid4(), [], 1),
        (uuid4(), [_submission(uuid4())], 1),
        (uuid4(), [_submission(uuid4(), device_id=2)], 1),
        (uuid4(), [_submission(uuid4(), expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1))], 1),
    ],
)
def test_missing_mismatched_cross_device_expired_or_absent_evidence_does_not_classify(
    monkeypatch, snapshot_id, rows, device_id
):
    db = Database(rows)
    called = []
    monkeypatch.setattr(api, "classify_visible_processes", lambda *args, **kwargs: called.append(1) or args[0])

    result = api._apply_helper_evidence(db, _snapshot(snapshot_id, device_id=device_id))

    assert getattr(result.processes[0], "classification", None) is None
    assert called == []


def test_snapshot_without_collection_id_skips_lookup_and_preserves_processes(monkeypatch):
    snapshot = _snapshot(None)
    called = []

    class NoQuery:
        def query(self, _model):
            called.append(1)
            raise AssertionError("helper evidence lookup should not run")

    result = api._apply_helper_evidence(NoQuery(), snapshot)

    assert result is snapshot
    assert called == []


def test_multiple_matching_rows_do_not_change_no_fallback_behavior(monkeypatch):
    collection_id = uuid4()
    db = Database([_submission(collection_id), _submission(collection_id)])
    calls = []
    monkeypatch.setattr(api, "classify_visible_processes", lambda processes, *_args, **_kwargs: calls.append(1) or processes)

    result = api._apply_helper_evidence(db, _snapshot(collection_id))

    assert getattr(result.processes[0], "classification", None) is None
    assert len(calls) == 2
