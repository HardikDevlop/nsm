from datetime import datetime, timedelta, timezone

from backend.services.snmp_polling import _interface_elapsed_seconds


def test_naive_database_utc_and_aware_now_are_safe():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    previous = datetime(2026, 9, 17, 11, 59)  # legacy DB UTC-naive value
    assert _interface_elapsed_seconds(now, previous) == 60


def test_aware_utc_values_are_safe_and_numerically_correct():
    now = datetime(2026, 9, 17, 12, 0, 30, tzinfo=timezone.utc)
    previous = now - timedelta(seconds=30)
    assert _interface_elapsed_seconds(now, previous) == 30


def test_missing_zero_and_negative_elapsed_keep_rate_protection():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _interface_elapsed_seconds(now, None) == 60
    assert _interface_elapsed_seconds(now, now) == 0
    assert _interface_elapsed_seconds(now, now + timedelta(seconds=1)) == -1


def test_no_manual_ist_conversion_is_used():
    import inspect
    from backend.services import snmp_polling

    source = inspect.getsource(snmp_polling._interface_elapsed_seconds)
    assert "+05:30" not in source
    assert "Asia/Kolkata" not in source
