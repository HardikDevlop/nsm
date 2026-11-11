from concurrent.futures import ThreadPoolExecutor
import threading
import time
from uuid import UUID

from backend.windows_monitoring.cim import WindowsProcessResult
from backend.windows_monitoring.process_snapshot_service import ProcessSnapshotService
from backend.windows_monitoring.task_manager_lock import LockExecutionResult


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def row(cpu, pid=1):
    return WindowsProcessResult("worker.exe", pid, 1, 1, None, creation_time="created", cpu_time_seconds=cpu)


def test_first_and_second_collection_calculate_cpu():
    clock = Clock()
    samples = iter([([row(10)], 2), ([row(12)], 2)])
    service = ProcessSnapshotService(lambda _: next(samples), clock=clock, refresh_cooldown_seconds=0)
    first = service.snapshot(1, force_refresh=True)
    clock.advance(2)
    second = service.snapshot(1, force_refresh=True)
    assert first.status == "ok" and first.cpu[0].status == "warming_up"
    assert second.cpu[0].cpu_percent == 50


def test_collection_id_is_created_once_per_collection_and_preserved_in_cache():
    clock = Clock()
    calls = []
    service = ProcessSnapshotService(lambda _: (calls.append(1) or ([row(1)], 1)), clock=clock)

    first = service.snapshot(1)
    cached = service.snapshot(1)

    assert isinstance(first.collection_id, UUID)
    assert cached.collection_id == first.collection_id
    assert len(calls) == 1

    clock.advance(11)
    second = service.snapshot(1, force_refresh=True)
    assert isinstance(second.collection_id, UUID)
    assert second.collection_id != first.collection_id


def test_cache_hit_and_expiry():
    clock = Clock()
    calls = []
    service = ProcessSnapshotService(lambda device: (calls.append(device) or ([row(1)], 1)), clock=clock)
    service.snapshot(1)
    service.snapshot(1)
    assert calls == [1]
    clock.advance(11)
    service.snapshot(1, force_refresh=True)
    assert calls == [1, 1]


def test_refresh_cooldown_returns_explicit_stale_state():
    clock = Clock()
    service = ProcessSnapshotService(lambda _: ([row(1)], 1), clock=clock, ttl_seconds=1, refresh_cooldown_seconds=5)
    service.snapshot(1, force_refresh=True)
    clock.advance(2)
    result = service.snapshot(1)
    assert result.status == "stale"
    assert result.reason == "refresh_cooldown"


def test_duplicate_concurrent_requests_collect_once():
    calls = []

    def collector(_):
        calls.append(1)
        time.sleep(0.05)
        return [row(1)], 1

    service = ProcessSnapshotService(collector, refresh_cooldown_seconds=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.snapshot(1), (1, 2)))
    assert len(calls) == 1
    assert all(result.status == "ok" for result in results)


def test_device_isolation_and_cache_eviction():
    clock = Clock()
    calls = []
    service = ProcessSnapshotService(lambda device: (calls.append(device) or ([row(device, device)], 1)), clock=clock, max_entries=2, refresh_cooldown_seconds=0)
    service.snapshot(1)
    service.snapshot(2)
    service.snapshot(3)
    service.snapshot(1, force_refresh=True)
    assert calls == [1, 2, 3, 1]


def test_collection_timeout_returns_error_without_stale_data():
    service = ProcessSnapshotService(lambda _: (time.sleep(0.1) or ([row(1)], 1)), collection_timeout_seconds=0.01)
    result = service.snapshot(1)
    assert result.status == "error"
    assert result.reason == "collection_timeout"


def test_collection_failure_returns_explicit_error():
    service = ProcessSnapshotService(lambda _: (_ for _ in ()).throw(RuntimeError("collector failed")))
    result = service.snapshot(1)
    assert result.status == "error"
    assert result.reason == "collection_failed"


def test_invalid_logical_processor_count_is_reported_by_cpu_utility():
    clock = Clock()
    samples = iter([([row(10)], 0), ([row(11)], 0)])
    service = ProcessSnapshotService(lambda _: next(samples), clock=clock, refresh_cooldown_seconds=0)
    service.snapshot(1, force_refresh=True)
    clock.advance(2)
    result = service.snapshot(1, force_refresh=True)
    assert result.cpu[0].status == "unavailable"
    assert result.cpu[0].reason == "invalid_logical_processor_count"


def test_expired_snapshot_is_not_returned_as_fresh():
    clock = Clock()
    service = ProcessSnapshotService(lambda _: ([row(1)], 1), clock=clock, refresh_cooldown_seconds=0)
    service.snapshot(1)
    clock.advance(11)
    result = service.snapshot(1, force_refresh=True)
    assert result.status == "ok"
    assert result.age_seconds == 0


def test_service_has_no_database_dependency():
    service = ProcessSnapshotService(lambda _: ([], 1))
    assert not hasattr(service, "db")


class FakeWorkerLock:
    def __init__(self, events, state="acquired"):
        self.events = events
        self.state = state

    def run(self, work):
        self.events.append("lock_acquired")
        if self.state != "acquired":
            return LockExecutionResult(self.state, reason="test")
        try:
            value = work()
            return LockExecutionResult("acquired", value=value)
        finally:
            self.events.append("lock_released")


def test_worker_lock_is_acquired_before_and_released_after_collection():
    events = []

    def collector(_):
        events.append("collection")
        return [row(1)], 1

    service = ProcessSnapshotService(
        collector,
        lock_factory=lambda _: FakeWorkerLock(events),
    )
    result = service.snapshot(1)
    assert result.status == "ok"
    assert events == ["lock_acquired", "collection", "lock_released"]


def test_lock_conflict_prevents_collection_and_publishing():
    calls = []
    service = ProcessSnapshotService(
        lambda _: (calls.append(1) or ([row(1)], 1)),
        lock_factory=lambda _: FakeWorkerLock([], "busy"),
    )
    result = service.snapshot(1)
    assert result.status == "error"
    assert result.reason == "busy"
    assert calls == []


def test_worker_exception_releases_lock():
    events = []

    def collector(_):
        events.append("collection")
        raise RuntimeError("collector failure")

    service = ProcessSnapshotService(collector, lock_factory=lambda _: FakeWorkerLock(events))
    result = service.snapshot(1)
    assert result.reason == "collection_failed"
    assert events == ["lock_acquired", "collection", "lock_released"]


def test_lock_connection_error_prevents_collection():
    calls = []
    service = ProcessSnapshotService(
        lambda _: (calls.append(1) or ([row(1)], 1)),
        lock_factory=lambda _: FakeWorkerLock([], "connection_error"),
    )
    result = service.snapshot(1)
    assert result.reason == "connection_error"
    assert calls == []


def test_lock_loss_does_not_publish_fresh_snapshot():
    service = ProcessSnapshotService(
        lambda _: ([row(1)], 1),
        lock_factory=lambda _: FakeWorkerLock([], "lock_lost"),
    )
    result = service.snapshot(1)
    assert result.status == "error"
    assert result.reason == "lock_lost"
    assert result.processes == ()


def test_release_error_does_not_publish_fresh_snapshot():
    class ReleaseErrorLock(FakeWorkerLock):
        def run(self, work):
            self.events.append("lock_acquired")
            value = work()
            self.events.append("lock_released")
            return LockExecutionResult("release_error", value=value)

    service = ProcessSnapshotService(
        lambda _: ([row(1)], 1),
        lock_factory=lambda _: ReleaseErrorLock([]),
    )
    result = service.snapshot(1)
    assert result.status == "error"
    assert result.reason == "release_error"
    assert result.processes == ()


def test_timeout_keeps_worker_lock_until_collection_finishes():
    started = threading.Event()
    finish = threading.Event()
    events = []

    def collector(_):
        started.set()
        finish.wait(timeout=2)
        events.append("collection_finished")
        return [row(1)], 1

    service = ProcessSnapshotService(
        collector,
        collection_timeout_seconds=0.01,
        lock_factory=lambda _: FakeWorkerLock(events),
    )
    result = service.snapshot(1)
    assert result.reason == "collection_timeout"
    assert events == ["lock_acquired"]
    finish.set()
    assert started.wait(timeout=1)
    for _ in range(100):
        if events == ["lock_acquired", "collection_finished", "lock_released"]:
            break
        time.sleep(0.01)
    assert events == ["lock_acquired", "collection_finished", "lock_released"]


def test_different_devices_use_independent_lock_instances():
    seen = []
    service = ProcessSnapshotService(
        lambda device: ([row(device, device)], 1),
        lock_factory=lambda device: seen.append(device) or FakeWorkerLock([]),
    )
    service.snapshot(1)
    service.snapshot(2)
    assert seen == [1, 2]
