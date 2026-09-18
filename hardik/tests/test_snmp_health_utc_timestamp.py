from datetime import datetime, timedelta, timezone

from backend.services.device_health import _snmp_age, _snmp_utc_aware


def test_naive_utc_polling_timestamp_is_not_interpreted_as_ist():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _snmp_age(datetime(2026, 9, 17, 11, 59, 50), now) == 10


def test_aware_utc_timestamp_behaves_identically():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _snmp_age(datetime(2026, 9, 17, 11, 59, 50, tzinfo=timezone.utc), now) == 10


def test_aware_non_utc_timestamp_converts_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    value = _snmp_utc_aware(datetime(2026, 9, 17, 17, 29, 50, tzinfo=ist))
    assert value == datetime(2026, 9, 17, 11, 59, 50, tzinfo=timezone.utc)


def test_old_naive_utc_timestamp_remains_stale():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _snmp_age(datetime(2026, 9, 17, 7, 0), now) == 18000
