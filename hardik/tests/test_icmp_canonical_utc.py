from datetime import datetime, timezone

from backend.services.device_health import _icmp_age
from backend.services.realtime_monitor import _icmp_db_now, _should_advance_last_seen


def test_new_icmp_db_timestamp_is_naive_utc_boundary_value():
    value = _icmp_db_now()
    assert value.tzinfo is None
    assert abs((datetime.now(timezone.utc).replace(tzinfo=None) - value).total_seconds()) < 2


def test_fresh_naive_utc_last_seen_has_no_artificial_ist_age():
    now = datetime(2026, 9, 17, 12, 38, 9, tzinfo=timezone.utc)
    last_seen = datetime(2026, 9, 17, 12, 38, 6)
    assert _icmp_age(last_seen, now) == 3
    assert _icmp_age(last_seen, now) < 60


def test_old_offline_evidence_remains_old():
    now = datetime(2026, 9, 17, 12, 38, 9, tzinfo=timezone.utc)
    last_seen = datetime(2026, 9, 17, 8, 39, 0)
    assert _icmp_age(last_seen, now) > 3 * 60


def test_older_queued_sample_cannot_regress_last_seen():
    current = datetime(2026, 9, 17, 12, 38, 9)
    older = datetime(2026, 9, 17, 12, 38, 6)
    newer = datetime(2026, 9, 17, 12, 38, 12)
    assert not _should_advance_last_seen(current, older)
    assert _should_advance_last_seen(current, newer)
