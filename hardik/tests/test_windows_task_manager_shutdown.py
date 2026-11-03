import threading
import time

from backend.windows_monitoring.process_snapshot_service import ProcessSnapshotService


def test_timed_out_process_worker_remains_tracked_and_permit_is_retained():
    started = threading.Event()
    finish = threading.Event()

    def collector(_device_id):
        started.set()
        finish.wait(2)
        return (), None

    service = ProcessSnapshotService(collector, collection_timeout_seconds=0.05)
    result = service.snapshot(1, force_refresh=True)
    assert result.reason == "collection_timeout"
    assert len(service._active_futures) == 1
    assert started.is_set()
    finish.set()
    deadline = time.monotonic() + 1
    while service._active_futures and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not service._active_futures


def test_shutdown_reports_pending_worker_after_bounded_deadline():
    finish = threading.Event()

    def collector(_device_id):
        finish.wait(2)
        return (), None

    service = ProcessSnapshotService(collector, collection_timeout_seconds=1)
    request = threading.Thread(target=lambda: service.snapshot(1, force_refresh=True))
    request.start()
    time.sleep(0.05)
    result = service.shutdown(grace_seconds=0.01)
    assert result["state"] == "stopped"
    assert result["pending"] == 1
    finish.set()
    request.join(2)


def test_repeated_shutdown_is_safe():
    service = ProcessSnapshotService(lambda _device_id: ((), None))
    first = service.shutdown(grace_seconds=0)
    second = service.shutdown(grace_seconds=0)
    assert first["state"] == second["state"] == "stopped"
