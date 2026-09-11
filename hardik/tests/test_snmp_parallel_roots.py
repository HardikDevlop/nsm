from __future__ import annotations

from threading import Barrier, Lock
import time

from backend.config.settings import get_settings
from backend.snmp.collector import SNMPService
from backend.snmp.credentials import SNMPCredentials


class _WalkClient:
    def __init__(self, delay=0.03, failing=None):
        self.delay = delay
        self.failing = failing or set()
        self.lock = Lock()
        self.active = 0
        self.max_active = 0

    def walk(self, host, root):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            if root in self.failing:
                raise TimeoutError(root)
            return {f"{root}.1": root}
        finally:
            with self.lock:
                self.active -= 1


def _service(client):
    service = SNMPService(SNMPCredentials())
    service.client = client
    return service


def test_independent_roots_overlap_and_limit_is_respected(monkeypatch):
    monkeypatch.setattr(get_settings(), "snmp_root_concurrency", 2)
    client = _WalkClient()
    roots = {str(i): f"1.3.6.{i}" for i in range(5)}
    result = _service(client)._walk_roots("192.0.2.1", roots)
    assert client.max_active == 2
    assert list(result) == [f"1.3.6.{i}.1" for i in range(5)]


def test_identity_dependency_remains_before_domain_roots(monkeypatch):
    events = []

    class Client(_WalkClient):
        def get(self, host, oids):
            events.append("identity")
            return {}
        def walk(self, host, root):
            assert events == ["identity"]
            events.append("root")
            return {}

    service = _service(Client(delay=0))
    service.collect_domain("192.0.2.1", "cpu")
    assert events == ["identity", "root"]


def test_timeout_keeps_successful_siblings_and_waits_for_cleanup(monkeypatch):
    monkeypatch.setattr(get_settings(), "snmp_root_concurrency", 3)
    client = _WalkClient(failing={"1.3.6.2"})
    roots = {"a": "1.3.6.1", "b": "1.3.6.2", "c": "1.3.6.3"}
    result = _service(client)._walk_roots("192.0.2.1", roots)
    assert result == {"1.3.6.1.1": "1.3.6.1", "1.3.6.3.1": "1.3.6.3"}
    assert client.active == 0


def test_parallel_execution_is_faster_than_serial_instrumentation(monkeypatch):
    roots = {str(i): f"1.3.6.{i}" for i in range(3)}
    monkeypatch.setattr(get_settings(), "snmp_root_concurrency", 1)
    started = time.perf_counter()
    _service(_WalkClient(delay=0.04))._walk_roots("192.0.2.1", roots)
    serial = time.perf_counter() - started

    monkeypatch.setattr(get_settings(), "snmp_root_concurrency", 3)
    started = time.perf_counter()
    _service(_WalkClient(delay=0.04))._walk_roots("192.0.2.1", roots)
    parallel = time.perf_counter() - started
    assert parallel < serial * 0.7


def test_poll_deadline_budget_is_passed_to_later_roots(monkeypatch):
    monkeypatch.setattr(get_settings(), "snmp_root_concurrency", 1)
    budgets = []

    class DeadlineClient:
        operation_timeout = 0.2
        def walk(self, host, root, operation_timeout=None):
            budgets.append(operation_timeout)
            time.sleep(0.02)
            return {root: root}

    result = _service(DeadlineClient())._walk_roots(
        "192.0.2.1", {"a": "1", "b": "2", "c": "3"}
    )
    assert result == {"1": "1", "2": "2", "3": "3"}
    assert budgets[0] <= 0.2
    assert budgets[0] > budgets[1] > budgets[2] > 0
