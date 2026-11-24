from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.effective_memory_aggregation import build_effective_memory_aggregate


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def outerjoin(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _DB:
    def __init__(self, linux_rows, snmp_rows):
        self.linux_rows = linux_rows
        self.snmp_rows = snmp_rows

    def query(self, *entities):
        return _Query(self.linux_rows if entities[0].__name__ == "LinuxServer" else self.snmp_rows)


def _linux(
    percent,
    timestamp,
    *,
    canonical=None,
    server_id=38,
    ip="192.0.2.40",
):
    details = {"memory": {"canonical": canonical}} if canonical is not None else {}
    return (
        SimpleNamespace(id=server_id, ip_address=ip),
        SimpleNamespace(memory_percent=percent, collected_at=timestamp, details=details),
    )


def _snmp(
    percent,
    timestamp,
    *,
    device_id=294,
    ip="192.0.2.183",
    enabled=True,
    status="running",
    supported=True,
    collection_status="SUCCESS",
    source="normalizer",
    missing_config=False,
    missing_latest=False,
    config_id=0,
):
    device = SimpleNamespace(id=device_id, ip_address=ip)
    latest = None if missing_latest else SimpleNamespace(utilization_percent=percent, polled_at=timestamp)
    config = None if missing_config else SimpleNamespace(
        id=config_id,
        enabled=enabled,
        status=status,
        module_name="memory",
    )
    capabilities = SimpleNamespace(capability_detail={
        "memory": {
            "supported": supported,
            "collection_status": collection_status,
            "data": {"source": source} if source is not None else {},
        }
    })
    return device, latest, config, capabilities


def test_fresh_linux_only_memory_preserves_linux_metadata():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([_linux(42.87, now - timedelta(seconds=30))], []), now=now)

    assert result["average_percent"] == 42.87
    assert result["source"] == "mixed-source-memory"
    assert result["semantic"] == "mixed_source_memory_utilization"
    assert result["devices"][0]["source"] == "linux-legacy-db"


def test_fresh_canonical_linux_memory_is_preferred():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([
        _linux(42, now - timedelta(seconds=30), canonical={
            "status": "ok",
            "usage_percent": 75.5,
            "source": "net-snmp-extend",
            "semantic": "linux_proc_meminfo_memavailable",
        }),
    ], []), now=now)

    assert result["average_percent"] == 75.5
    assert result["devices"][0]["source"] == "net-snmp-extend"
    assert result["devices"][0]["semantic"] == "linux_proc_meminfo_memavailable"


def test_invalid_canonical_linux_memory_falls_back_to_fresh_legacy_value():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([
        _linux(42, now - timedelta(seconds=30), canonical={
            "status": "ok",
            "usage_percent": 101,
            "source": "net-snmp-extend",
        }),
    ], []), now=now)

    assert result["average_percent"] == 42
    assert result["devices"][0]["source"] == "linux-legacy-db"


def test_stale_canonical_does_not_override_newer_valid_row_sample():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([
        _linux(42, now - timedelta(seconds=541), canonical={
            "status": "ok",
            "usage_percent": 75.5,
            "source": "net-snmp-extend",
        }),
    ], []), now=now)

    assert result["average_percent"] is None
    assert result["stale_average_percent"] == 75.5
    assert result["exclusions"]["stale"] == 1


def test_missing_canonical_linux_memory_uses_legacy_fallback():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([
        _linux(0, now - timedelta(seconds=30)),
    ], []), now=now)

    assert result["average_percent"] == 0
    assert result["devices"][0]["source"] == "linux-legacy-db"


def test_naive_linux_ist_timestamp_is_normalized_to_fresh_utc_sample():
    result = build_effective_memory_aggregate(_DB([
        _linux(67.59, datetime(2026, 11, 19, 13, 20, 26), canonical={
            "status": "ok",
            "usage_percent": 34.46317704406462,
            "source": "net-snmp-extend",
            "semantic": "linux_proc_meminfo_memavailable",
        }),
    ], []), now=datetime(2026, 11, 19, 7, 55, 29, tzinfo=timezone.utc))

    assert result["average_percent"] == 34.46317704406462
    assert result["reporting_count"] == 1
    assert result["status"] == "ok"
    assert result["exclusions"]["stale"] == 0


def test_linux_aware_utc_timestamp_has_same_freshness_semantics():
    timestamp = datetime(2026, 11, 19, 7, 50, 26, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([
        _linux(42, timestamp),
    ], []), now=datetime(2026, 11, 19, 7, 55, 29, tzinfo=timezone.utc))

    assert result["average_percent"] == 42
    assert result["reporting_count"] == 1


def test_linux_sample_older_than_540_seconds_remains_stale():
    result = build_effective_memory_aggregate(_DB([
        _linux(42, datetime(2026, 11, 19, 13, 10, 28)),
    ], []), now=datetime(2026, 11, 19, 7, 50, 29, tzinfo=timezone.utc))

    assert result["average_percent"] is None
    assert result["stale_average_percent"] == 42
    assert result["exclusions"]["stale"] == 1


def test_linux_future_ist_sample_is_rejected():
    result = build_effective_memory_aggregate(_DB([
        _linux(42, datetime(2026, 11, 19, 13, 21, 0)),
    ], []), now=datetime(2026, 11, 19, 7, 20, 29, tzinfo=timezone.utc))

    assert result["average_percent"] is None
    assert result["exclusions"]["stale"] == 1


def test_fresh_snmp_normalizer_memory_is_accepted():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [_snmp(70.4, now - timedelta(seconds=30))]), now=now)

    assert result["average_percent"] == 70.4
    assert result["reporting_count"] == 1
    assert result["devices"][0]["source"] == "normalizer"


def test_linux_and_snmp_values_are_equal_weighted():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB(
        [_linux(40, now - timedelta(seconds=10))],
        [_snmp(70, now - timedelta(seconds=20))],
    ), now=now)

    assert result["average_percent"] == 55
    assert result["reporting_count"] == 2


def test_duplicate_ip_prefers_linux():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB(
        [_linux(40, now - timedelta(seconds=10), ip="192.0.2.40")],
        [_snmp(70, now - timedelta(seconds=20), ip="192.0.2.40")],
    ), now=now)

    assert result["average_percent"] == 40
    assert result["reporting_count"] == 1
    assert result["exclusions"]["duplicate"] == 1


def test_stale_linux_allows_fresh_snmp_fallback():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB(
        [_linux(40, now - timedelta(seconds=541))],
        [_snmp(70, now - timedelta(seconds=20), ip="192.0.2.40")],
    ), now=now)

    assert result["average_percent"] == 70
    assert result["exclusions"]["stale"] == 1


def test_duplicate_snmp_ips_choose_newest_valid_sample():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [
        _snmp(60, now - timedelta(seconds=40), device_id=1),
        _snmp(80, now - timedelta(seconds=10), device_id=2),
    ]), now=now)

    assert result["average_percent"] == 80
    assert result["exclusions"]["duplicate"] == 1


def test_snmp_config_capability_and_status_are_required():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [
        _snmp(10, now, device_id=1, enabled=False),
        _snmp(20, now, device_id=2, supported=False),
        _snmp(30, now, device_id=3, collection_status="FAILED"),
        _snmp(40, now, device_id=4, status="stopped"),
    ]), now=now)

    assert result["average_percent"] is None
    assert result["exclusions"]["snmp_unsupported"] == 4


def test_invalid_future_stale_and_zero_values_are_handled():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [
        _snmp(0, now, device_id=1),
        _snmp(101, now, device_id=2),
        _snmp(float("nan"), now, device_id=3),
        _snmp(20, now + timedelta(seconds=1), device_id=4),
        _snmp(30, now - timedelta(seconds=541), device_id=5),
    ]), now=now)

    assert result["average_percent"] == 0
    assert result["reporting_count"] == 1
    assert result["exclusions"]["snmp_invalid"] == 2
    assert result["exclusions"]["snmp_stale"] == 2


def test_naive_utc_timestamp_and_exact_boundary_are_fresh():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [
        _snmp(25, datetime(2026, 11, 13, 11, 51, 0), device_id=1),
    ]), now=datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))

    assert result["average_percent"] == 25


def test_missing_source_or_no_readings_returns_no_data():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    missing_source = _snmp(25, now, source=None)
    result = build_effective_memory_aggregate(_DB([], [missing_source]), now=now)

    assert result["average_percent"] is None
    assert result["status"] == "no_data"
    assert result["exclusions"]["snmp_unsupported"] == 1


def test_missing_snmp_configuration_is_classified():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [
        _snmp(25, now, device_id=1, missing_config=True),
    ]), now=now)

    assert result["average_percent"] is None
    assert result["exclusions"]["snmp_missing_config"] == 1
    assert result["excluded_count"] == 1


def test_missing_latest_memory_is_classified_as_unavailable():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB([], [
        _snmp(25, now, device_id=1, missing_latest=True),
    ]), now=now)

    assert result["average_percent"] is None
    assert result["exclusions"]["snmp_missing_latest"] == 1
    assert result["excluded_count"] == 1


def test_multiple_memory_configs_are_classified_once_and_running_config_wins():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    stopped = _snmp(75, now, device_id=1, status="stopped", config_id=1)
    running = _snmp(75, now, device_id=1, status="running", config_id=2)
    result = build_effective_memory_aggregate(_DB([], [stopped, running]), now=now)

    assert result["average_percent"] == 75
    assert result["reporting_count"] == 1
    assert result["eligible_count"] == 1
    assert result["excluded_count"] == 0


def test_count_fields_reconcile_after_deduplication_and_exclusions():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    result = build_effective_memory_aggregate(_DB(
        [_linux(40, now)],
        [
            _snmp(70, now, ip="192.0.2.40"),
            _snmp(80, now, device_id=2, ip="192.0.2.81"),
            _snmp(90, now, device_id=3, ip="192.0.2.82", missing_config=True),
        ],
    ), now=now)

    assert result["eligible_count"] == 3
    assert result["reporting_count"] == 2
    assert result["exclusions"]["duplicate"] == 1
    assert result["exclusions"]["snmp_missing_config"] == 1
    assert result["excluded_count"] == 2
