"""Process-local single-flight guards for SNMP polls."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Condition, Lock
from typing import Iterator

_state_lock = Condition(Lock())
_active_polls: set[tuple[int, str]] = set()


def _conflicts(device_id: int, module: str) -> bool:
    if module == "__full__":
        return any(active_device == device_id for active_device, _ in _active_polls)
    return (
        (device_id, "__full__") in _active_polls
        or (device_id, module) in _active_polls
    )


@contextmanager
def poll_guard(device_id: int, module: str, *, blocking: bool = True) -> Iterator[bool]:
    """Acquire the device/module guard and report whether it was acquired."""
    key = (device_id, module)
    with _state_lock:
        while _conflicts(device_id, module):
            if not blocking:
                yield False
                return
            _state_lock.wait()
        _active_polls.add(key)
    try:
        yield True
    finally:
        with _state_lock:
            _active_polls.discard(key)
            _state_lock.notify_all()
