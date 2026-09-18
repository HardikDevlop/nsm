from datetime import datetime, timezone

from backend.api.snmp_device_routes import _interface_api_elapsed
from backend.snmp.statistics_engine import interface_rate_mbps


def test_increasing_counter_calculates_rate():
    assert interface_rate_mbps(1_000_000, 0, 1) == 8.0


def test_equal_counter_is_genuine_zero():
    assert interface_rate_mbps(10, 10, 1) == 0.0


def test_decrease_is_discontinuity_not_wrap():
    assert interface_rate_mbps(3, 10, 1) is None


def test_discontinuity_baseline_then_next_sample_recovers():
    assert interface_rate_mbps(100, 200, 1) is None
    assert interface_rate_mbps(25_000_100, 100, 2) == 100.0


def test_missing_previous_and_invalid_elapsed_are_unavailable():
    assert interface_rate_mbps(10, None, 1) is None
    assert interface_rate_mbps(10, 0, 0) is None
    assert interface_rate_mbps(10, 0, -1) is None


def test_known_speed_rejects_impossible_rate_but_keeps_valid_rate():
    assert interface_rate_mbps(2_000_000_000, 0, 1, 1_000_000_000) is None
    assert interface_rate_mbps(125_000_000, 0, 1, 1_000_000_000) == 1000.0


def test_api_elapsed_normalizes_naive_utc_and_aware_utc():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    previous = datetime(2026, 9, 17, 11, 59)
    assert _interface_api_elapsed(now, previous) == 60


def test_no_manual_ist_conversion_in_rate_helper():
    import inspect
    from backend.snmp import statistics_engine
    from backend.api import snmp_device_routes

    assert "+05:30" not in inspect.getsource(statistics_engine.interface_rate_mbps)
    assert "Asia/Kolkata" not in inspect.getsource(snmp_device_routes._interface_api_elapsed)
