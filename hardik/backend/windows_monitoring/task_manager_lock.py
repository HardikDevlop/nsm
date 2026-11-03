"""Worker-owned PostgreSQL advisory lock for Task Manager collection.

The lock owns a dedicated SQLAlchemy connection for the full protected
operation. It does not share request sessions, caches, or CPU baselines across
workers, and it cannot guarantee exclusion after PostgreSQL connection loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from sqlalchemy import text

from backend.database.session import engine


T = TypeVar("T")
ConnectionFactory = Callable[[], object]


@dataclass(frozen=True)
class LockExecutionResult(Generic[T]):
    state: str
    value: T | None = None
    reason: str | None = None


class WorkerOwnedAdvisoryLock:
    """Own one session advisory lock and its dedicated DB connection."""

    PREFIX = "nms.windows.task_manager.processes:"

    def __init__(self, device_id: int, *, namespace: str = PREFIX, connection_factory: ConnectionFactory | None = None) -> None:
        if isinstance(device_id, bool) or not isinstance(device_id, int) or device_id <= 0:
            raise ValueError("device_id must be a positive integer")
        self.device_id = device_id
        if not namespace.endswith(":"):
            raise ValueError("namespace must end with ':'")
        self.lock_key = f"{namespace}{device_id}"
        self._connection_factory = connection_factory or engine.connect
        self._connection = None
        self.state = "connection_error"
        self._held = False

    def acquire(self) -> str:
        if self._held:
            return "acquired"
        try:
            self._connection = self._connection_factory()
            result = self._connection.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": self.lock_key},
            ).scalar_one()
        except Exception:
            self.state = "connection_error"
            self._invalidate_and_close()
            return self.state
        if not result:
            self.state = "busy"
            self._close_without_reuse()
            return self.state
        self._held = True
        self.state = "acquired"
        return self.state

    def release(self) -> str:
        if not self._held:
            self._close_without_reuse()
            return self.state
        try:
            result = self._connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                {"lock_key": self.lock_key},
            ).scalar_one()
            if not result:
                self.state = "release_error"
                self._invalidate_and_close()
                self._held = False
                return self.state
        except Exception:
            self.state = "lock_lost"
            self._held = False
            self._invalidate_and_close()
            return self.state
        self._held = False
        self.state = "acquired"
        self._close_without_reuse()
        return self.state

    def run(self, work: Callable[[], T]) -> LockExecutionResult[T]:
        """Run protected work, always releasing/invalidating after completion."""
        acquired = self.acquire()
        if acquired != "acquired":
            return LockExecutionResult(acquired, reason="lock_not_acquired")
        try:
            value = work()
        except Exception:
            self.release()
            raise
        release_state = self.release()
        if release_state in {"lock_lost", "release_error"}:
            return LockExecutionResult(release_state, value=value, reason="lock_cleanup_failed")
        return LockExecutionResult("acquired", value=value)

    def _close_without_reuse(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                self.state = "release_error"

    def _invalidate_and_close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            invalidate = getattr(connection, "invalidate", None)
            if callable(invalidate):
                invalidate()
        finally:
            try:
                connection.close()
            except Exception:
                pass
