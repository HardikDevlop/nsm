from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.linux_monitoring import scheduler, service
from backend.linux_monitoring.metrics import LinuxMetricCollectionError


class _Query:
    def __init__(self, value):
        self.value = value

    def filter_by(self, **_kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _DB:
    def __init__(self, config=None, previous=None):
        self.config = config
        self.previous = previous
        self.commits = 0
        self.added = []

    def query(self, entity, *args):
        name = getattr(entity, "__name__", "")
        if name == "LinuxServerMonitoringConfig":
            return _Query(self.config)
        return _Query(self.previous)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def refresh(self, _value):
        return None


def _session(db):
    @contextmanager
    def context():
        yield db
    return context


def test_scheduler_success_updates_run_and_success_timestamps(monkeypatch):
    collected_at = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
    run_at = datetime(2026, 11, 19, 10, 0, 1, tzinfo=timezone.utc)
    config = SimpleNamespace(
        last_success_at=None,
        last_run_at=None,
        monitoring_status="running",
        last_error="old error",
    )
    sample = SimpleNamespace(collected_at=collected_at)
    db = _DB(config=config)
    monkeypatch.setattr(scheduler, "SessionLocal", _session(db))
    monkeypatch.setattr(scheduler, "linux_now", lambda: run_at)
    monkeypatch.setattr(scheduler.service, "collect_metrics", lambda *_args: (sample, None))
    monkeypatch.setattr(scheduler, "evaluate_sample", lambda *_args: None)

    assert scheduler.LinuxMonitoringScheduler._collect_once(7, object()) is True
    assert config.last_run_at == run_at
    assert config.last_success_at == collected_at
    assert config.monitoring_status == "running"
    assert config.last_error is None
    assert db.commits == 1


def test_scheduler_failure_updates_run_but_does_not_replace_newer_success(monkeypatch):
    newer_success = datetime(2026, 11, 19, 10, 0, 5, tzinfo=timezone.utc)
    failed_attempt_started = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
    run_at = datetime(2026, 11, 19, 10, 0, 6, tzinfo=timezone.utc)
    config = SimpleNamespace(
        last_success_at=newer_success,
        last_run_at=None,
        monitoring_status="running",
        last_error=None,
    )
    db = _DB(config=config)
    monkeypatch.setattr(scheduler, "SessionLocal", _session(db))
    clock = iter((failed_attempt_started, run_at, run_at))
    monkeypatch.setattr(scheduler, "linux_now", lambda: next(clock))
    error = LinuxMetricCollectionError("timeout", "SNMP collection timed out")
    monkeypatch.setattr(scheduler.service, "collect_metrics", lambda *_args: (None, error))

    assert scheduler.LinuxMonitoringScheduler._collect_once(7, object()) is False
    assert config.last_run_at == run_at
    assert config.last_success_at == newer_success
    assert config.monitoring_status == "running"
    assert config.last_error is None

    scheduler.LinuxMonitoringScheduler._record_failure(7, "late scheduler exception", failed_attempt_started)
    assert config.last_success_at == newer_success
    assert config.monitoring_status == "running"
    assert config.last_error is None


def test_service_failure_persists_unavailable_canonical_sample_without_mutating_current(monkeypatch):
    server = SimpleNamespace(id=7, ip_address="192.0.2.7", last_error=None)
    db = _DB(previous=None)
    monkeypatch.setattr(service, "get_server", lambda *_args: server)
    monkeypatch.setattr(service, "SessionLocal", _session(db), raising=False)
    monkeypatch.setattr(
        service,
        "collect_linux_metrics",
        lambda *_args: (_ for _ in ()).throw(LinuxMetricCollectionError("timeout", "SNMP timeout")),
    )

    failed, error = service.collect_metrics(db, 7, object())

    assert error.code == "timeout"
    assert failed.collection_status == "error"
    assert failed.details["memory"]["canonical"]["status"] == "unavailable"
    assert db.added == [failed]
    assert db.commits == 1


def test_scheduler_interval_is_three_minutes():
    assert scheduler.LINUX_POLL_INTERVAL_SECONDS == 180
