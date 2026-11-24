from __future__ import annotations

import threading

from backend.services.realtime_ownership import RealtimeMonitorOwnership
from backend.services.realtime_monitor import MonitorEngine


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()

    def set(self, key, value, nx=False, ex=None):
        with self.lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    def get(self, key):
        with self.lock:
            return self.values.get(key)

    def eval(self, script, count, key, token, ttl=None):
        with self.lock:
            if self.values.get(key) != token:
                return 0
            if "expire" in script:
                return 1
            del self.values[key]
            return 1


def test_acquisition_and_owner_only_release():
    redis = FakeRedis()
    owner = RealtimeMonitorOwnership(client=redis, owner_token="owner-a")
    other = RealtimeMonitorOwnership(client=redis, owner_token="owner-b")
    assert owner.acquire().state == "owned"
    assert other.acquire().state == "owner_unavailable"
    assert other.release().state == "owner_unavailable"
    assert owner.release().state == "stopped"


def test_renewal_and_expired_or_lost_lease_fence_new_work():
    redis = FakeRedis()
    owner = RealtimeMonitorOwnership(client=redis, owner_token="owner-a")
    assert owner.acquire().state == "owned"
    assert owner.renew().state == "owned"
    redis.values[owner.key] = "different-owner"
    assert owner.renew().state == "lease_lost"
    assert owner.before_poll() is False


def test_active_work_blocks_release_until_completed():
    redis = FakeRedis()
    owner = RealtimeMonitorOwnership(client=redis, owner_token="owner-a")
    owner.acquire()
    assert owner.before_poll() is True
    assert owner.release().last_error == "active_work_in_flight"
    owner.after_poll()
    assert owner.release().state == "stopped"


def test_redis_unavailable_fails_closed():
    owner = RealtimeMonitorOwnership(client=None, owner_token="owner-a")
    assert owner.acquire().state == "owner_unavailable"
    assert owner.before_poll() is False


def test_concurrent_acquisition_has_one_owner():
    redis = FakeRedis()
    owners = [RealtimeMonitorOwnership(client=redis, owner_token=f"owner-{i}") for i in range(8)]
    results = []
    threads = [threading.Thread(target=lambda item=item: results.append(item.acquire().state), args=()) for item in owners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("owned") == 1
    assert results.count("owner_unavailable") == 7


def test_generation_changes_only_after_new_acquisition():
    redis = FakeRedis()
    owner = RealtimeMonitorOwnership(client=redis, owner_token="owner-a")
    assert owner.status().generation == 0
    assert owner.acquire().generation == 1
    assert owner.acquire().generation == 1


def test_stale_generation_is_rejected_before_poll():
    redis = FakeRedis()
    owner = RealtimeMonitorOwnership(client=redis, owner_token="owner-a")
    assert owner.acquire().generation == 1
    assert owner.before_poll(expected_generation=0) is False
    assert owner.before_poll(expected_generation=1) is True
    owner.after_poll()


def test_owned_poll_fencing_has_no_alert_or_notification_dependencies():
    """The ownership primitive is transport-only and cannot invoke alert code."""
    redis = FakeRedis()
    owner = RealtimeMonitorOwnership(client=redis, owner_token="owner-a")
    owner.acquire()
    assert owner.before_poll(expected_generation=1) is True
    assert owner.status().active_work == 1
    owner.after_poll()
    assert owner.status().active_work == 0


def test_engine_owned_start_is_idempotent_and_stop_is_runtime_only():
    redis = FakeRedis()
    ownership = RealtimeMonitorOwnership(client=redis, owner_token="owner-engine")
    engine = MonitorEngine(ownership=ownership)
    try:
        first = engine.start_owned([])
        second = engine.start_owned([])
        assert first["state"] == "running"
        assert second["idempotent"] is True
        assert second["generation"] == first["generation"]
        stopped = engine.stop_owned(timeout=2)
        assert stopped["state"] == "stopped"
        assert ownership.status().state == "stopped"
    finally:
        if engine._metric_batch_thread.is_alive():
            engine.shutdown()


def test_engine_restart_requires_verified_stop():
    redis = FakeRedis()
    ownership = RealtimeMonitorOwnership(client=redis, owner_token="owner-restart")
    engine = MonitorEngine(ownership=ownership)
    try:
        assert engine.start_owned([])["state"] == "running"
        assert engine.restart_owned([], timeout=2)["state"] == "running"
        assert engine.stop_owned(timeout=2)["state"] == "stopped"
    finally:
        if engine._metric_batch_thread.is_alive():
            engine.shutdown()


def test_incomplete_stop_blocks_restart():
    redis = FakeRedis()
    ownership = RealtimeMonitorOwnership(client=redis, owner_token="owner-blocked")
    engine = MonitorEngine(ownership=ownership)
    try:
        engine._lifecycle_state = "incomplete_stop"
        result = engine.restart_owned([])
        assert result["state"] == "incomplete_stop"
    finally:
        if engine._metric_batch_thread.is_alive():
            engine.shutdown()
