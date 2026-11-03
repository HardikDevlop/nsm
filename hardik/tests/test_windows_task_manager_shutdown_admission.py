import time

from backend.windows_monitoring.process_snapshot_service import ProcessSnapshotService


def test_process_rejects_admission_after_shutdown_begins():
    process_calls = []
    processes = ProcessSnapshotService(lambda device_id: (process_calls.append(device_id) or ((), None)))
    deadline = time.monotonic() + 1

    processes.begin_shutdown(deadline=deadline)

    process_result = processes.snapshot(1, force_refresh=True)

    assert process_result.reason == "shutting_down"
    assert process_calls == []
