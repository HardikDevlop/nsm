from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time

import pytest

from backend.snmp.raw_cache import RawSNMPResultCache
from backend.snmp.client import SNMPClient
from backend.snmp.credentials import SNMPCredentials


def test_same_key_within_ttl_makes_one_request_and_returns_copies():
    cache = RawSNMPResultCache(10)
    calls = 0

    def request():
        nonlocal calls
        calls += 1
        return {"oid": [1]}

    first = cache.execute((115, "identity"), request)
    first["oid"].append(2)
    second = cache.execute((115, "identity"), request)
    assert calls == 1
    assert second == {"oid": [1]}


def test_simultaneous_duplicates_are_single_flight():
    cache = RawSNMPResultCache(10)
    barrier = Barrier(8)
    lock = Lock()
    calls = 0

    def request():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return {"oid": "value"}

    def run():
        barrier.wait()
        return cache.execute((115, "root"), request)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: run(), range(8)))
    assert calls == 1
    assert results == [{"oid": "value"}] * 8


def test_ttl_expiry_performs_new_request():
    cache = RawSNMPResultCache(0.02)
    calls = 0

    def request():
        nonlocal calls
        calls += 1
        return {"call": calls}

    assert cache.execute("key", request) == {"call": 1}
    time.sleep(0.03)
    assert cache.execute("key", request) == {"call": 2}


def test_device_and_credentials_are_isolated_by_key():
    cache = RawSNMPResultCache(10)
    calls = 0

    def request():
        nonlocal calls
        calls += 1
        return {"call": calls}

    cache.execute((115, "v2c", "fingerprint-a"), request)
    cache.execute((116, "v2c", "fingerprint-a"), request)
    cache.execute((115, "v3", "fingerprint-b"), request)
    assert calls == 3


def test_failure_is_not_cached():
    cache = RawSNMPResultCache(10)
    calls = 0

    def request():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("timeout")
        return {"ok": True}

    with pytest.raises(TimeoutError):
        cache.execute("key", request)
    assert cache.execute("key", request) == {"ok": True}
    assert calls == 2


def test_successful_empty_result_is_cached():
    cache = RawSNMPResultCache(10)
    calls = 0

    def request():
        nonlocal calls
        calls += 1
        return {}

    assert cache.execute("key", request) == {}
    assert cache.execute("key", request) == {}
    assert calls == 1


def test_client_cache_key_isolates_device_and_credentials(monkeypatch):
    import backend.snmp.raw_cache as cache_module

    cache = RawSNMPResultCache(10)
    monkeypatch.setattr(cache_module, "get_raw_snmp_cache", lambda *_: cache)
    calls = 0

    def request():
        nonlocal calls
        calls += 1
        return {"call": calls}

    v2_a = SNMPClient(SNMPCredentials(community="public"), device_id=115)
    v2_b = SNMPClient(SNMPCredentials(community="private"), device_id=115)
    v3 = SNMPClient(SNMPCredentials(version="v3", username="user"), device_id=115)
    other_device = SNMPClient(SNMPCredentials(community="public"), device_id=116)

    assert v2_a._cached("10.0.0.1", ("walk", "1.3.6"), request) == {"call": 1}
    assert v2_a._cached("10.0.0.1", ("walk", "1.3.6"), request) == {"call": 1}
    assert v2_b._cached("10.0.0.1", ("walk", "1.3.6"), request) == {"call": 2}
    assert v3._cached("10.0.0.1", ("walk", "1.3.6"), request) == {"call": 3}
    assert other_device._cached("10.0.0.1", ("walk", "1.3.6"), request) == {"call": 4}
    assert calls == 4


def test_performance_proof_duplicate_calls_are_coalesced():
    calls_without_cache = 0
    calls_with_cache = 0

    def physical_without_cache():
        nonlocal calls_without_cache
        calls_without_cache += 1
        return {"1.3.6.1": "value"}

    # BEFORE: independent module jobs each invoke the same physical request.
    physical_without_cache()
    physical_without_cache()

    cache = RawSNMPResultCache(10)

    def physical_with_cache():
        nonlocal calls_with_cache
        calls_with_cache += 1
        return {"1.3.6.1": "value"}

    # AFTER: the same device/operation key reuses the successful raw result.
    cache.execute((115, "identity"), physical_with_cache)
    cache.execute((115, "identity"), physical_with_cache)

    assert calls_without_cache == 2
    assert calls_with_cache == 1
