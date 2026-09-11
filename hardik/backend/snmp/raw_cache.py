"""Short-lived, process-local cache and single-flight for raw SNMP results."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
from threading import Event, Lock
import time
from typing import Callable, Hashable

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    value: dict
    expires_at: float


@dataclass
class _Flight:
    done: Event
    value: dict | None = None
    error: BaseException | None = None


class RawSNMPResultCache:
    """Thread-safe TTL cache that coalesces identical in-flight requests."""

    def __init__(self, ttl_seconds: float, max_entries: int = 2048) -> None:
        self.ttl_seconds = max(0.0, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._lock = Lock()
        self._entries: dict[Hashable, _CacheEntry] = {}
        self._flights: dict[Hashable, _Flight] = {}

    def _purge_expired_locked(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
            logger.debug("SNMP_CACHE_EXPIRED")

    def execute(self, key: Hashable, request: Callable[[], dict]) -> dict:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._entries.get(key)
            if entry is not None:
                logger.debug("SNMP_CACHE_HIT")
                return deepcopy(entry.value)

            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight(done=Event())
                self._flights[key] = flight
                owner = True
                logger.debug("SNMP_CACHE_MISS")
            else:
                owner = False
                logger.debug("SNMP_SINGLEFLIGHT_WAIT")

        if not owner:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            if flight.value is None:
                raise RuntimeError("SNMP single-flight completed without a result")
            return deepcopy(flight.value)

        try:
            logger.debug("SNMP_NETWORK_REQUEST")
            value = request()
            if not isinstance(value, dict):
                raise TypeError("Raw SNMP result must be a dictionary")
            safe_value = deepcopy(value)
            with self._lock:
                flight.value = safe_value
                if self.ttl_seconds > 0:
                    if len(self._entries) >= self.max_entries:
                        oldest = min(self._entries, key=lambda item: self._entries[item].expires_at)
                        self._entries.pop(oldest, None)
                    self._entries[key] = _CacheEntry(
                        value=safe_value,
                        expires_at=time.monotonic() + self.ttl_seconds,
                    )
            return deepcopy(safe_value)
        except BaseException as exc:
            with self._lock:
                flight.error = exc
            raise
        finally:
            with self._lock:
                self._flights.pop(key, None)
                flight.done.set()


_cache: RawSNMPResultCache | None = None
_cache_lock = Lock()


def get_raw_snmp_cache(ttl_seconds: float, max_entries: int) -> RawSNMPResultCache:
    global _cache
    with _cache_lock:
        if (
            _cache is None
            or _cache.ttl_seconds != max(0.0, ttl_seconds)
            or _cache.max_entries != max(1, max_entries)
        ):
            _cache = RawSNMPResultCache(ttl_seconds, max_entries)
        return _cache
