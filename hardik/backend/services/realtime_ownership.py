"""Owner/fencing primitive for the Realtime Monitor.

Stage 1 deliberately does not import or activate this component from the
monitor startup path.  It provides only an isolated, fail-closed interface for
the later lifecycle integration.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from backend.cache.redis_cache import _get_client

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class OwnershipStatus:
    state: str
    token: str
    generation: int
    active_work: int
    last_error: str | None = None


class RealtimeMonitorOwnership:
    """Fail-closed Redis lease with local generation and work fencing."""

    def __init__(self, *, client: Any | None = None, key: str = "nms:realtime-monitor:leader", ttl: int = 30, owner_token: str | None = None):
        if ttl <= 0:
            raise ValueError("lease ttl must be positive")
        self.key = key
        self.ttl = ttl
        self.token = owner_token or f"{os.getpid()}:{uuid.uuid4()}"
        self.generation = 0
        self._client = _get_client() if client is None else client
        self._lock = threading.Lock()
        self._active_work = 0
        self._state = "stopped"
        self._last_error: str | None = None

    @property
    def client(self) -> Any | None:
        return self._client

    def acquire(self) -> OwnershipStatus:
        with self._lock:
            if self._client is None:
                return self._fail("redis_unavailable")
            try:
                acquired = bool(self._client.set(self.key, self.token, nx=True, ex=self.ttl))
            except Exception:
                return self._fail("redis_unavailable")
            if not acquired:
                self._state = "owner_unavailable"
                self._last_error = "lease_owned_by_other"
                return self.status()
            self.generation += 1
            self._state = "owned"
            self._last_error = None
            return self.status()

    def renew(self) -> OwnershipStatus:
        with self._lock:
            if self._state != "owned":
                return self.status()
            if self._client is None:
                return self._lose("redis_unavailable")
            try:
                renewed = bool(self._client.eval(_RENEW_SCRIPT, 1, self.key, self.token, str(self.ttl)))
            except Exception:
                return self._lose("redis_unavailable")
            return self.status() if renewed else self._lose("lease_lost")

    def release(self) -> OwnershipStatus:
        with self._lock:
            if self._state != "owned":
                return self.status()
            if self._active_work:
                self._last_error = "active_work_in_flight"
                return self.status()
            if self._client is None:
                return self._lose("redis_unavailable")
            try:
                released = bool(self._client.eval(_RELEASE_SCRIPT, 1, self.key, self.token))
            except Exception:
                return self._lose("redis_unavailable")
            if released:
                self._state = "stopped"
                self._last_error = None
            else:
                return self._lose("lease_lost")
            return self.status()

    def before_poll(self, expected_generation: int | None = None) -> bool:
        """Fence new work; in-flight work must still be cooperatively stopped."""
        with self._lock:
            if self._state != "owned" or self._client is None or (expected_generation is not None and expected_generation != self.generation):
                return False
            try:
                if self._client.get(self.key) != self.token:
                    self._lose("lease_lost")
                    return False
            except Exception:
                self._lose("redis_unavailable")
                return False
            self._active_work += 1
            return True

    def after_poll(self) -> None:
        with self._lock:
            self._active_work = max(0, self._active_work - 1)

    def status(self) -> OwnershipStatus:
        return OwnershipStatus(self._state, self.token, self.generation, self._active_work, self._last_error)

    def _fail(self, error: str) -> OwnershipStatus:
        self._state = "owner_unavailable"
        self._last_error = error
        return self.status()

    def _lose(self, error: str) -> OwnershipStatus:
        self._state = "lease_lost"
        self._last_error = error
        return self.status()
