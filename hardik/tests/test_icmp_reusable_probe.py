from backend.services import realtime_monitor as rm


def test_native_probe_avoids_subprocess(monkeypatch):
    monkeypatch.setattr(rm, "_native_icmp_unavailable", False)
    monkeypatch.setattr(rm, "_native_ping", lambda ip, timeout: (True, 1.5))
    monkeypatch.setattr(rm, "_subprocess_ping", lambda *args: (_ for _ in ()).throw(AssertionError()))
    assert rm._ping("127.0.0.1") == (True, 1.5)


def test_native_unavailable_falls_back_and_is_sticky(monkeypatch):
    monkeypatch.setattr(rm, "_native_icmp_unavailable", False)
    monkeypatch.setattr(rm, "_native_ping", lambda *args: (_ for _ in ()).throw(rm._NativeICMPUnavailable()))
    calls = []
    monkeypatch.setattr(rm, "_subprocess_ping", lambda *args: (calls.append(args) or (False, None)))
    assert rm._ping("192.0.2.1") == (False, None)
    assert rm._ping("192.0.2.1") == (False, None)
    assert len(calls) == 2


def test_native_timeout_does_not_switch_engine(monkeypatch):
    monkeypatch.setattr(rm, "_native_icmp_unavailable", False)
    monkeypatch.setattr(rm, "_native_ping", lambda *args: (False, None))
    monkeypatch.setattr(rm, "_subprocess_ping", lambda *args: (_ for _ in ()).throw(AssertionError()))
    assert rm._ping("192.0.2.1") == (False, None)
