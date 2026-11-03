"""Process-local resource budget for on-demand Task Manager collections."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class TaskManagerPermit:
    """An idempotent permit returned to the collection owner."""

    _budget: "TaskManagerResourceBudget"
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._budget._release()


class TaskManagerResourceBudget:
    """Bounded capacity shared by process and service collection services.

    This budget is intentionally process-local. It does not coordinate separate
    Uvicorn workers or backend instances.
    """

    def __init__(self, capacity: int = 2) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("Task Manager capacity must be a positive integer")
        self.capacity = capacity
        self._semaphore = threading.BoundedSemaphore(capacity)

    def acquire(self, timeout: float | None = None) -> TaskManagerPermit | None:
        acquired = self._semaphore.acquire(timeout=timeout) if timeout is not None else self._semaphore.acquire()
        return TaskManagerPermit(self) if acquired else None

    def _release(self) -> None:
        self._semaphore.release()
