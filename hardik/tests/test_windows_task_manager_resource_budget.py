import threading
import time

import pytest

from backend.windows_monitoring.resource_budget import TaskManagerResourceBudget
from backend.windows_monitoring.process_snapshot_service import ProcessSnapshotService


def test_invalid_capacity_is_rejected():
    with pytest.raises(ValueError):
        TaskManagerResourceBudget(0)
    with pytest.raises(ValueError):
        TaskManagerResourceBudget(True)


def test_permit_release_is_idempotent():
    budget = TaskManagerResourceBudget(1)
    permit = budget.acquire(timeout=0)
    assert permit is not None
    assert budget.acquire(timeout=0) is None
    permit.release()
    permit.release()
    assert budget.acquire(timeout=0) is not None


def test_third_collection_is_rejected_without_starting_collector():
    budget = TaskManagerResourceBudget(2)
    permits = [budget.acquire(timeout=0), budget.acquire(timeout=0)]
    called = False

    def collector(_device_id):
        nonlocal called
        called = True
        return (), None

    service = ProcessSnapshotService(collector, collection_timeout_seconds=0.05, resource_budget=budget)
    result = service.snapshot(1, force_refresh=True)
    assert result.reason == "concurrency_limit"
    assert called is False
    permits[0].release()
    permits[1].release()
