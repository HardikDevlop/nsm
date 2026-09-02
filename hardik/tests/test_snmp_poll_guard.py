import threading

from backend.services.snmp_poll_guard import poll_guard


def test_same_device_and_module_allows_only_one_active_poll():
    entered = threading.Event()
    release = threading.Event()
    results = []

    def first_poll():
        with poll_guard(7, "interfaces", blocking=False) as acquired:
            results.append(acquired)
            entered.set()
            release.wait(timeout=2)

    worker = threading.Thread(target=first_poll)
    worker.start()
    assert entered.wait(timeout=2)

    with poll_guard(7, "interfaces", blocking=False) as acquired:
        results.append(acquired)

    release.set()
    worker.join(timeout=2)
    assert results == [True, False]


def test_unrelated_device_or_module_is_not_blocked():
    with poll_guard(7, "interfaces", blocking=False) as first:
        assert first is True
        with poll_guard(7, "routing", blocking=False) as other_module:
            assert other_module is True
        with poll_guard(8, "interfaces", blocking=False) as other_device:
            assert other_device is True
