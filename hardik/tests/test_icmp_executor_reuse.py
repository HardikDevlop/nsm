from backend.services import realtime_monitor as rm


def test_executor_is_constructed_once_and_reused(monkeypatch):
    created = []

    class FakeExecutor:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def shutdown(self, wait=True):
            pass

    monkeypatch.setattr(rm, "ThreadPoolExecutor", FakeExecutor)
    engine = rm.MonitorEngine()
    engine._ensure_loop()
    first = engine._executor
    engine._stop_event.set()
    engine._thread.join(timeout=1)
    engine._thread = None
    engine._ensure_loop()
    assert engine._executor is first
    assert created == [{"max_workers": 20, "thread_name_prefix": "mon-ping"}]
    engine.shutdown()


def test_shutdown_releases_executor_and_allows_clean_restart(monkeypatch):
    engine = rm.MonitorEngine()
    engine._ensure_loop()
    executor = engine._executor
    engine.shutdown()
    assert executor is not None
    assert engine._executor is None
    assert engine._thread is None


def test_ping_contract_remains_one_packet_and_timeout(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = "64 bytes from 127.0.0.1: time=0.12 ms ttl=64"

    monkeypatch.setattr(rm.subprocess, "run", lambda *args, **kwargs: (calls.append((args, kwargs)) or Result()))
    reachable, rtt = rm._ping("127.0.0.1")
    assert reachable is True
    assert rtt == 0.12
    args, kwargs = calls[0]
    assert args[0][:3] == ["ping", "-c", "1"]
    assert kwargs["timeout"] == 3.0
