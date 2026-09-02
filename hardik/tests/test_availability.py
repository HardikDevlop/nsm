from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.availability_routes import AvailabilityPayload, router, view
from backend.database.session import Base
from backend.models import AvailabilityOutage, AvailabilityReport, Device, DeviceMetric, DeviceStatusHistory
from backend.services.availability import calculate_availability
from backend.services.availability import build_intervals, merge_windows, normalize_time
def test_availability_payload_supports_all_entity_dimensions():
    assert AvailabilityPayload(entity_type="business_service", entity_id=1, start="2026-01-01T00:00:00", end="2026-01-01T01:00:00", sla_target=99.9).sla_target == 99.9
def test_availability_report_preserves_planned_unplanned_and_reasons():
    assert {"planned_downtime_seconds", "unplanned_downtime_seconds", "downtime_reasons"}.issubset(AvailabilityReport.__table__.columns.keys())
def test_availability_routes_support_generation_and_history():
    assert {"/api/v1/availability/reports", "/api/v1/availability/reports/export.csv"}.issubset({r.path for r in router.routes})


def event(identifier, timestamp, state, reason=None):
    return SimpleNamespace(id=identifier, timestamp=timestamp, new_status=state, change_reason=reason)


def test_missing_history_is_unknown_not_uptime():
    start = datetime(2026, 1, 1); intervals, outages, pre_creation = build_intervals([], start, start + timedelta(hours=1))
    assert [(row.state, row.end - row.start) for row in intervals] == [("unknown", timedelta(hours=1))]
    assert outages == [] and pre_creation == 0


def test_online_offline_recovery_and_ongoing_outage():
    start = datetime(2026, 1, 1)
    intervals, outages, _ = build_intervals([event(1, start, "online"), event(2, start + timedelta(minutes=10), "offline"), event(3, start + timedelta(minutes=20), "online")], start, start + timedelta(hours=1), freshness_seconds=3600)
    assert [(row.state, int((row.end - row.start).total_seconds())) for row in intervals] == [("online", 600), ("offline", 600), ("online", 2400)]
    assert outages[0].start == start + timedelta(minutes=10) and outages[0].end == start + timedelta(minutes=20)


def test_unknown_does_not_close_offline_outage():
    start = datetime(2026, 1, 1)
    intervals, outages, _ = build_intervals([event(1, start, "offline"), event(2, start + timedelta(minutes=10), "unknown")], start, start + timedelta(minutes=30), freshness_seconds=3600)
    assert [row.state for row in intervals] == ["offline", "unknown"]
    assert outages[0].ongoing is False and outages[0].end == start + timedelta(minutes=10)


def test_duplicate_and_same_timestamp_transitions_are_deterministic():
    start = datetime(2026, 1, 1)
    intervals, _, _ = build_intervals([event(2, start + timedelta(minutes=5), "online"), event(1, start + timedelta(minutes=5), "online"), event(3, start + timedelta(minutes=10), "offline")], start, start + timedelta(minutes=20), freshness_seconds=3600)
    assert [(row.state, row.start.minute, row.end.minute) for row in intervals] == [("unknown", 0, 5), ("online", 5, 10), ("offline", 10, 20)]


def test_device_created_mid_period_is_not_scored_before_creation():
    start = datetime(2026, 1, 1); created = start + timedelta(minutes=30)
    intervals, _, pre_creation = build_intervals([event(1, created, "online")], start, start + timedelta(hours=1), created)
    assert pre_creation == 1800 and intervals[0].start == created


def test_timezone_normalization_and_maintenance_union():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert normalize_time(aware).tzinfo is None
    start = datetime(2026, 1, 1); end = start + timedelta(hours=1)
    assert merge_windows([(start, start + timedelta(minutes=40)), (start + timedelta(minutes=20), end)], start, end) == [(start, end)]


def test_report_persistence_is_idempotent_and_outages_keep_report_fk():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    start = datetime(2026, 1, 1); end = start + timedelta(hours=1)
    db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", status="online", created_at=start - timedelta(days=1)))
    db.flush()
    db.add_all([DeviceStatusHistory(device_id=115, old_status="unknown", new_status="online", timestamp=start), DeviceStatusHistory(device_id=115, old_status="online", new_status="offline", timestamp=start + timedelta(minutes=10)), DeviceStatusHistory(device_id=115, old_status="offline", new_status="online", timestamp=start + timedelta(minutes=20))])
    db.add_all([DeviceMetric(device_id=115, latency=1.0, packet_loss=0.0 if offset < 600 or offset >= 1200 else 100.0, created_at=start + timedelta(seconds=offset)) for offset in range(0, 3600, 30)])
    db.flush()
    first = calculate_availability(db, "device", 115, start, end, sla_target=99.0); db.commit()
    second = calculate_availability(db, "device", 115, start, end, sla_target=99.0); db.commit()
    assert first.id == second.id
    assert db.query(AvailabilityReport).count() == 1
    assert db.query(AvailabilityOutage).filter_by(report_id=second.id).count() == 1


def test_existing_report_reconciles_from_known_to_unknown_and_clears_outages():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    start = datetime(2026, 1, 1); end = start + timedelta(hours=1)
    db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", status="online", created_at=start - timedelta(days=1)))
    db.flush()
    db.add_all([
        DeviceStatusHistory(device_id=115, old_status="unknown", new_status="online", timestamp=start),
        DeviceStatusHistory(device_id=115, old_status="online", new_status="offline", timestamp=start + timedelta(minutes=10)),
        DeviceStatusHistory(device_id=115, old_status="offline", new_status="online", timestamp=start + timedelta(minutes=20)),
    ])
    db.add_all([DeviceMetric(device_id=115, latency=1.0, packet_loss=100.0 if 600 <= offset < 1200 else 0.0, created_at=start + timedelta(seconds=offset)) for offset in range(0, 3600, 30)])
    db.flush()
    initial = calculate_availability(db, "device", 115, start, end); db.commit()
    assert initial.availability_percent == 83.333
    assert db.query(AvailabilityOutage).filter_by(report_id=initial.id).count() == 1

    db.query(DeviceStatusHistory).delete()
    db.query(DeviceMetric).delete()
    reconciled = calculate_availability(db, "device", 115, start, end); db.commit()
    assert reconciled.id == initial.id
    assert reconciled.availability_percent is None
    assert reconciled.coverage_percent == 0.0
    assert reconciled.unknown_seconds == 3600
    assert reconciled.sla_breached is None
    assert db.query(AvailabilityReport).count() == 1
    assert db.query(AvailabilityOutage).filter_by(report_id=reconciled.id).count() == 0


def test_stale_online_seed_and_no_fresh_observations_become_unknown():
    start = datetime(2026, 8, 30, 15, 33, 3, 635000); end = start + timedelta(hours=24)
    stale = start - timedelta(hours=20, minutes=45)
    intervals, outages, _ = build_intervals([event(50, stale, "online")], start, end)
    assert sum(int((row.end - row.start).total_seconds()) for row in intervals if row.state == "online") == 0
    assert sum(int((row.end - row.start).total_seconds()) for row in intervals if row.state == "unknown") == 86400
    assert outages == []


def test_insufficient_evidence_makes_sla_unevaluable():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    start = datetime(2026, 8, 30, 15, 33, 3, 635000); end = start + timedelta(hours=24)
    db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", status="online", created_at=start - timedelta(days=1)))
    db.flush()
    report = calculate_availability(db, "device", 115, start, end, sla_target=99.0)
    assert report.availability_percent is None
    assert report.sla_breached is None


def test_unknown_seconds_survives_api_serialization_for_zero_coverage():
    report = AvailabilityReport(
        id=38,
        entity_type="device",
        entity_id=115,
        window_start=datetime(2026, 8, 30, 15, 33, 3),
        window_end=datetime(2026, 8, 31, 15, 33, 3),
        total_seconds=86400,
        monitored_duration_seconds=86400,
        uptime_seconds=0,
        downtime_seconds=0,
        unknown_seconds=86400,
        coverage_percent=0.0,
        availability_percent=None,
        outage_count=0,
        mttr_seconds=None,
        mtbf_seconds=None,
        sla_target_percent=99.0,
        sla_breached=None,
        downtime_reasons={},
        generated_at=datetime(2026, 8, 31, 15, 33, 3),
    )
    assert view(report)["unknown_seconds"] == 86400


def test_fresh_observations_expire_then_resume_after_gap():
    start = datetime(2026, 1, 1)
    evidence = [(start, "online"), (start + timedelta(seconds=30), "online"), (start + timedelta(minutes=3), "online"), (start + timedelta(minutes=4), "offline")]
    intervals, outages, _ = build_intervals([], start, start + timedelta(minutes=5), evidence=evidence, freshness_seconds=60)
    assert [(row.state, int((row.end - row.start).total_seconds())) for row in intervals] == [("online", 90), ("unknown", 90), ("online", 60), ("offline", 60)]
    assert outages[0].ongoing is True
