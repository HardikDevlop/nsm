from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from backend.services.device_health import _icmp_health_evidence
from backend.services.realtime_monitor import _should_advance_last_seen


def _device(attempt, status):
    return SimpleNamespace(last_icmp_attempt_at=attempt, last_icmp_status=status,
                           last_seen=None, status="offline", monitoring_status=True)


def test_fresh_success_is_reachable():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _icmp_health_evidence(_device(datetime(2026, 9, 17, 11, 59, 50), "reachable"), now, 60)[0] == "reachable"


def test_fresh_failure_is_unreachable():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _icmp_health_evidence(_device(datetime(2026, 9, 17, 11, 59, 50), "unreachable"), now, 60)[0] == "unreachable"


def test_old_attempt_is_stale_and_legacy_fallback_remains():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert _icmp_health_evidence(_device(datetime(2026, 9, 17, 8, 0), "unreachable"), now, 60)[0] == "stale"
    legacy = _device(None, None)
    legacy.last_seen = datetime(2026, 9, 17, 11, 59, 50)
    assert _icmp_health_evidence(legacy, now, 60)[0] == "unreachable"


def test_attempt_ordering_prevents_older_sample_regression():
    current = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    older = current - timedelta(seconds=1)
    newer = current + timedelta(seconds=1)
    assert not _should_advance_last_seen(current, older)
    assert _should_advance_last_seen(current, newer)
