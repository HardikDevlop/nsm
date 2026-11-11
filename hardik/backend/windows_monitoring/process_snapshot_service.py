"""Process-local, bounded process snapshot orchestration.

This module deliberately has no FastAPI or database dependency. Callers must
authorize the device and enforce RBAC/site isolation before invoking it.
Locks and cache state are process-local; future multi-worker API integration
must add shared coordination (for example Redis) if cross-worker coalescing is
required.
"""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
import logging
from typing import Callable, Iterable
from uuid import UUID, uuid4

from .cim import WindowsProcessResult
from .process_cpu import ProcessCPUResult, calculate_process_cpu
from .task_manager_lock import LockExecutionResult, WorkerOwnedAdvisoryLock
from .resource_budget import TaskManagerPermit, TaskManagerResourceBudget


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessSnapshot:
    device_id: int
    processes: tuple[WindowsProcessResult, ...]
    cpu: tuple[ProcessCPUResult, ...]
    collected_monotonic_seconds: float
    age_seconds: float
    status: str
    reason: str | None = None
    collected_at: str | None = None
    collection_id: UUID | None = None


@dataclass(frozen=True)
class _Baseline:
    processes: tuple[WindowsProcessResult, ...]
    collected_monotonic_seconds: float
    logical_processor_count: int | None


@dataclass(frozen=True)
class _Cached:
    processes: tuple[WindowsProcessResult, ...]
    cpu: tuple[ProcessCPUResult, ...]
    collected_monotonic_seconds: float
    collected_at: str
    collection_id: UUID


Collector = Callable[[int], tuple[Iterable[WindowsProcessResult], int | None]]
LockFactory = Callable[[int], WorkerOwnedAdvisoryLock]


class ProcessSnapshotLockError(Exception):
    def __init__(self, state: str) -> None:
        super().__init__(state)
        self.state = state


class ProcessSnapshotService:
    """Bounded on-demand process collection with separate CPU baselines."""

    def __init__(
        self,
        collector: Collector,
        *,
        ttl_seconds: float = 10.0,
        refresh_cooldown_seconds: float = 2.0,
        collection_timeout_seconds: float = 10.0,
        max_entries: int = 100,
        max_concurrent_collections: int = 4,
        clock: Callable[[], float] = time.monotonic,
        lock_factory: LockFactory | None = None,
        resource_budget: TaskManagerResourceBudget | None = None,
    ) -> None:
        if not 1 <= ttl_seconds <= 300:
            raise ValueError("ttl_seconds must be between 1 and 300")
        if refresh_cooldown_seconds < 0 or refresh_cooldown_seconds > 300:
            raise ValueError("refresh cooldown must be between 0 and 300")
        if collection_timeout_seconds <= 0 or max_entries <= 0 or max_concurrent_collections <= 0:
            raise ValueError("service bounds must be positive")
        self._collector = collector
        self._ttl = ttl_seconds
        self._cooldown = refresh_cooldown_seconds
        self._timeout = collection_timeout_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock_factory = lock_factory
        self._cache: OrderedDict[int, _Cached] = OrderedDict()
        self._baselines: OrderedDict[int, _Baseline] = OrderedDict()
        self._last_attempt: dict[int, float] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._state_lock = threading.RLock()
        self._resource_budget = resource_budget or TaskManagerResourceBudget(max_concurrent_collections)
        self._lifecycle = "running"
        self._active_futures: set[object] = set()
        self._shutdown_deadline: float | None = None

    def snapshot(self, device_id: int, *, force_refresh: bool = False, collector: Collector | None = None, collection_id: UUID | None = None) -> ProcessSnapshot:
        now = self._clock()
        with self._state_lock:
            cached = self._cache.get(device_id)
            if cached is not None and now - cached.collected_monotonic_seconds <= self._ttl and not force_refresh:
                self._cache.move_to_end(device_id)
                return self._response(device_id, cached, now, "ok")
            if not force_refresh and device_id in self._last_attempt and now - self._last_attempt[device_id] < self._cooldown:
                return self._stale_or_empty(device_id, cached, now, "refresh_cooldown")
            if self._lifecycle != "running":
                return self._stale_or_empty(device_id, cached, now, "shutting_down")
            lock = self._locks.setdefault(device_id, threading.Lock())

        if not lock.acquire(timeout=self._timeout):
            return self._stale_or_empty(device_id, cached, now, "collection_in_progress")
        try:
            now = self._clock()
            with self._state_lock:
                if self._lifecycle != "running":
                    return self._stale_or_empty(device_id, cached, now, "shutting_down")
                cached = self._cache.get(device_id)
                if cached is not None and now - cached.collected_monotonic_seconds <= self._ttl and not force_refresh:
                    return self._response(device_id, cached, now, "ok")
                self._last_attempt[device_id] = now
            permit = self._resource_budget.acquire(timeout=self._timeout)
            if permit is None:
                return self._stale_or_empty(device_id, cached, now, "concurrency_limit")
            collection_id = collection_id or uuid4()
            try:
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(self._collect, device_id, collector or self._collector)
            except Exception:
                permit.release()
                raise
            with self._state_lock:
                self._active_futures.add(future)
            future.add_done_callback(self._worker_done)
            # The permit is released only when the actual worker exits. This
            # remains true when the request-side wait times out.
            future.add_done_callback(lambda _: permit.release())
            try:
                processes, logical_processors = future.result(timeout=self._timeout)
            except FutureTimeout:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                return self._stale_or_empty(device_id, cached, self._clock(), "collection_timeout")
            except ProcessSnapshotLockError as exc:
                logger.warning(
                    "windows_task_manager_collection_failed device_id=%s stage=advisory_lock "
                    "exception_type=%s classification=%s",
                    device_id, type(exc).__name__, exc.state,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                return self._stale_or_empty(device_id, cached, self._clock(), exc.state)
            except Exception as exc:
                logger.warning(
                    "windows_task_manager_collection_failed device_id=%s stage=collector "
                    "exception_type=%s classification=collection_failed",
                    device_id, type(exc).__name__,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                return self._stale_or_empty(device_id, cached, self._clock(), "collection_failed")
            else:
                executor.shutdown(wait=True, cancel_futures=True)
            collected = self._clock()
            process_rows = tuple(processes)
            with self._state_lock:
                baseline = self._baselines.get(device_id)
                if baseline is None:
                    cpu = tuple(ProcessCPUResult(row.process_id, None, "warming_up", "first_sample") for row in process_rows if row.process_id is not None)
                else:
                    cpu = tuple(calculate_process_cpu(
                        baseline.processes,
                        process_rows,
                        previous_monotonic_seconds=baseline.collected_monotonic_seconds,
                        current_monotonic_seconds=collected,
                        logical_processor_count=logical_processors,
                    ))
                self._baselines[device_id] = _Baseline(process_rows, collected, logical_processors)
                self._baselines.move_to_end(device_id)
                entry = _Cached(process_rows, cpu, collected, datetime.now(timezone.utc).isoformat(), collection_id)
                self._cache[device_id] = entry
                self._cache.move_to_end(device_id)
                self._evict()
            return self._response(device_id, entry, collected, "ok")
        finally:
            lock.release()

    def cached(self, device_id: int) -> ProcessSnapshot:
        """Read only this worker's cache; never invokes a collector."""
        now = self._clock()
        with self._state_lock:
            cached = self._cache.get(device_id)
            if cached is None:
                return ProcessSnapshot(device_id, (), (), now, 0.0, "no_snapshot", "no_cached_snapshot")
            self._cache.move_to_end(device_id)
            status = "ok" if now - cached.collected_monotonic_seconds <= self._ttl else "stale"
            return self._response(device_id, cached, now, status)

    def _worker_done(self, future) -> None:
        with self._state_lock:
            self._active_futures.discard(future)

    def begin_shutdown(self, *, deadline: float | None = None, grace_seconds: float = 5.0) -> None:
        """Stop admitting collections without waiting for active workers."""
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        end = deadline if deadline is not None else time.monotonic() + grace_seconds
        with self._state_lock:
            if self._lifecycle == "running":
                self._lifecycle = "shutting_down"
                self._shutdown_deadline = end

    def shutdown(self, *, grace_seconds: float = 5.0, deadline: float | None = None) -> dict[str, object]:
        """Stop admission and drain active workers until one bounded deadline."""
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        end = deadline if deadline is not None else time.monotonic() + grace_seconds
        self.begin_shutdown(deadline=end)
        with self._state_lock:
            if self._shutdown_deadline is not None:
                end = min(end, self._shutdown_deadline)
            futures = tuple(self._active_futures)
        for future in futures:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            try:
                future.result(timeout=remaining)
            except Exception:
                pass
        with self._state_lock:
            pending = len(self._active_futures)
            completed = len(futures) - pending if pending <= len(futures) else 0
            self._lifecycle = "stopped"
        return {"state": "stopped", "completed": completed, "pending": pending}

    def _collect(self, device_id: int, collector: Collector) -> tuple[Iterable[WindowsProcessResult], int | None]:
        """Run the collector in the same worker that owns the advisory lock."""
        if self._lock_factory is None:
            logger.info(
                "windows_task_manager_collector_started device_id=%s stage=collector "
                "lock=not_configured",
                device_id,
            )
            return collector(device_id)
        worker_lock = self._lock_factory(device_id)
        logger.info(
            "windows_task_manager_collector_started device_id=%s stage=advisory_lock "
            "lock=acquisition_started",
            device_id,
        )
        def protected_collection():
            logger.info(
                "windows_task_manager_collector_started device_id=%s stage=collector "
                "lock=acquired",
                device_id,
            )
            return collector(device_id)
        result: LockExecutionResult[tuple[Iterable[WindowsProcessResult], int | None]] = worker_lock.run(
            protected_collection
        )
        if result.state != "acquired":
            logger.warning(
                "windows_task_manager_collection_failed device_id=%s stage=advisory_lock "
                "exception_type=LockExecutionResult classification=%s",
                device_id, result.state,
            )
            raise ProcessSnapshotLockError(result.state)
        if result.value is None:
            raise ProcessSnapshotLockError("lock_lost")
        return result.value


    def _evict(self) -> None:
        while len(self._cache) > self._max_entries:
            device_id, _ = self._cache.popitem(last=False)
            self._baselines.pop(device_id, None)
            self._last_attempt.pop(device_id, None)

    def _response(self, device_id: int, cached: _Cached, now: float, status: str, reason: str | None = None) -> ProcessSnapshot:
        return ProcessSnapshot(device_id, cached.processes, cached.cpu, cached.collected_monotonic_seconds, max(0.0, now - cached.collected_monotonic_seconds), status, reason, cached.collected_at, cached.collection_id)

    def _stale_or_empty(self, device_id: int, cached: _Cached | None, now: float, reason: str) -> ProcessSnapshot:
        if cached is None:
            return ProcessSnapshot(device_id, (), (), now, 0.0, "error", reason)
        return self._response(device_id, cached, now, "stale", reason)
