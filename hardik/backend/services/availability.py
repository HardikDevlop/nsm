from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from backend.models import AvailabilityOutage, AvailabilityReport, ChangeRequest, ConfigurationItem, CIRelationship, Device, DeviceMetric, DeviceStatusHistory

LOCAL_TZ = ZoneInfo("Asia/Kolkata")
ONLINE, OFFLINE = {"online", "up"}, {"offline", "down", "unreachable"}
EVIDENCE_GAP_SECONDS = max(1, int(os.getenv("AVAILABILITY_EVIDENCE_GAP_SECONDS", "45")))

def normalize_time(value: datetime) -> datetime:
    return value.astimezone(LOCAL_TZ).replace(tzinfo=None) if value.tzinfo else value

def normalize_state(value: str | None) -> str:
    value = (value or "").lower().strip()
    return "online" if value in ONLINE else "offline" if value in OFFLINE else "unknown"

@dataclass
class Interval:
    start: datetime
    end: datetime
    state: str

@dataclass
class Outage:
    start: datetime
    end: datetime | None
    reason: str | None
    ongoing: bool

def merge_windows(windows: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    clipped = sorted((max(a, start), min(b, end)) for a, b in windows if a < end and b > start)
    merged: list[tuple[datetime, datetime]] = []
    for item in clipped:
        if item[0] >= item[1]:
            continue
        if merged and item[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], item[1]))
        else:
            merged.append(item)
    return merged

def split_offline(start: datetime, end: datetime, windows: list[tuple[datetime, datetime]]) -> tuple[int, int]:
    duration = max(0, int((end - start).total_seconds()))
    planned = min(duration, sum(int((min(end, b) - max(start, a)).total_seconds()) for a, b in windows))
    return planned, duration - planned

def build_intervals(events: list[DeviceStatusHistory], start: datetime, end: datetime, created_at: datetime | None = None, evidence: list[tuple[datetime, str]] | None = None, freshness_seconds: int = EVIDENCE_GAP_SECONDS) -> tuple[list[Interval], list[Outage], int]:
    start, end = normalize_time(start), normalize_time(end)
    applicable = max(start, normalize_time(created_at)) if created_at else start
    status_observations = [(normalize_time(event.timestamp), normalize_state(event.new_status), event.id) for event in events]
    metric_observations = [(normalize_time(timestamp), normalize_state(state), index) for index, (timestamp, state) in enumerate(evidence or [], start=1)]
    observations = sorted(status_observations + metric_observations, key=lambda item: (item[0], item[2]))
    before = [item for item in observations if item[0] < applicable]
    inside = [item for item in observations if applicable <= item[0] < end]
    seed = before[-1] if before and (applicable - before[-1][0]).total_seconds() <= freshness_seconds else None
    state = seed[1] if seed else "unknown"
    cursor, expiry = applicable, seed[0] + timedelta(seconds=freshness_seconds) if seed else applicable
    intervals: list[Interval] = []
    outages: list[Outage] = []
    for timestamp, observed_state, _ in inside:
        if timestamp > cursor:
            valid_end = min(timestamp, end, expiry) if state != "unknown" else timestamp
            if valid_end > cursor:
                intervals.append(Interval(cursor, valid_end, state))
            if timestamp > valid_end:
                intervals.append(Interval(valid_end, timestamp, "unknown"))
        state, cursor, expiry = observed_state, timestamp, timestamp + timedelta(seconds=freshness_seconds)
    if cursor < end:
        valid_end = min(end, expiry) if state != "unknown" else cursor
        if valid_end > cursor:
            intervals.append(Interval(cursor, valid_end, state))
        if end > valid_end:
            intervals.append(Interval(valid_end, end, "unknown"))
    merged_intervals: list[Interval] = []
    for interval in intervals:
        if merged_intervals and merged_intervals[-1].state == interval.state and merged_intervals[-1].end == interval.start:
            merged_intervals[-1].end = interval.end
        else:
            merged_intervals.append(interval)
    intervals = merged_intervals
    for interval in intervals:
        if interval.state == "offline":
            ongoing = interval.end == end and expiry >= end
            outages.append(Outage(interval.start, None if ongoing else interval.end, None, ongoing))
    return intervals, outages, max(0, int((applicable - start).total_seconds()))

def resolve_devices(db: Session, entity_type: str, entity_id: int) -> list[Device]:
    if entity_type == "device":
        query = db.query(Device).filter(Device.id == entity_id)
    elif entity_type == "site":
        query = db.query(Device).filter(Device.site_id == entity_id)
    elif entity_type == "interface":
        query = db.query(Device).filter(Device.interfaces.any(id=entity_id))
    else:
        links = db.query(CIRelationship).filter((CIRelationship.source_ci_id == entity_id) | (CIRelationship.target_ci_id == entity_id)).all()
        ids = {entity_id} | {link.source_ci_id for link in links} | {link.target_ci_id for link in links}
        device_ids = [row.device_id for row in db.query(ConfigurationItem).filter(ConfigurationItem.id.in_(ids), ConfigurationItem.device_id.isnot(None)).all()]
        query = db.query(Device).filter(Device.id.in_(device_ids))
    devices = query.filter(Device.deleted_at.is_(None)).all()
    if not devices:
        raise LookupError("Availability entity not found or has no devices")
    return devices

def calculate_availability(db: Session, entity_type: str, entity_id: int, start: datetime, end: datetime, generated_by: int | None = None, sla_target: float = 99.0) -> AvailabilityReport:
    start, end = normalize_time(start), normalize_time(end)
    if end <= start: raise ValueError("end must be after start")
    if not 0 <= sla_target <= 100: raise ValueError("sla_target must be between 0 and 100")
    devices = resolve_devices(db, entity_type, entity_id)
    windows = merge_windows([(normalize_time(row.maintenance_start), normalize_time(row.maintenance_end)) for row in db.query(ChangeRequest).filter(ChangeRequest.maintenance_start < end, ChangeRequest.maintenance_end > start).all() if row.maintenance_start and row.maintenance_end], start, end)
    total = int((end - start).total_seconds()); monitored = uptime = downtime = unknown = planned = unplanned = 0; outage_rows: list[tuple[Device, Outage, int, bool]] = []
    for device in devices:
        evidence_floor = start - timedelta(seconds=EVIDENCE_GAP_SECONDS)
        events = db.query(DeviceStatusHistory).filter(DeviceStatusHistory.device_id == device.id, DeviceStatusHistory.timestamp >= evidence_floor, DeviceStatusHistory.timestamp < end).order_by(DeviceStatusHistory.timestamp.asc(), DeviceStatusHistory.id.asc()).all()
        metrics = db.query(DeviceMetric).filter(DeviceMetric.device_id == device.id, DeviceMetric.created_at >= evidence_floor, DeviceMetric.created_at < end).order_by(DeviceMetric.created_at.asc(), DeviceMetric.id.asc()).all()
        metric_evidence = [(metric.created_at, "offline" if metric.packet_loss is not None and metric.packet_loss >= 100 else "online") for metric in metrics if metric.packet_loss is not None or metric.latency is not None]
        intervals, outages, pre_creation = build_intervals(events, start, end, device.created_at, metric_evidence)
        applicable = total - pre_creation; monitored += max(0, applicable)
        for interval in intervals:
            seconds = max(0, int((interval.end - interval.start).total_seconds()))
            if interval.state == "online": uptime += seconds
            elif interval.state == "offline":
                downtime += seconds; p, u = split_offline(interval.start, interval.end, windows); planned += p; unplanned += u
            else: unknown += seconds
        for outage in outages:
            effective_end = outage.end or end; duration = max(0, int((effective_end - outage.start).total_seconds())); p, _ = split_offline(outage.start, effective_end, windows); outage_rows.append((device, outage, duration, p == duration and duration > 0))
    known = uptime + downtime; availability = round(uptime / known * 100, 3) if known else None; coverage = round(known / monitored * 100, 3) if monitored else 0.0
    completed = sorted((row for row in outage_rows if not row[1].ongoing), key=lambda row: row[1].start); mttr = round(sum(row[2] for row in completed) / len(completed), 3) if completed else None; mtbf = None
    if len(completed) > 1:
        gaps = [max(0, int((completed[i][1].start - (completed[i - 1][1].end or completed[i - 1][1].start)).total_seconds())) for i in range(1, len(completed))]; mtbf = round(sum(gaps) / len(gaps), 3) if gaps else None
    report = db.query(AvailabilityReport).filter_by(entity_type=entity_type, entity_id=entity_id, window_start=start, window_end=end).first()
    if report is None:
        report = AvailabilityReport(entity_type=entity_type, entity_id=entity_id, window_start=start, window_end=end)
        db.add(report)
    report.total_seconds = total; report.monitored_duration_seconds = monitored; report.uptime_seconds = uptime; report.downtime_seconds = downtime; report.unknown_seconds = max(0, monitored - known); report.planned_downtime_seconds = min(planned, downtime); report.unplanned_downtime_seconds = min(unplanned, downtime - report.planned_downtime_seconds); report.coverage_percent = coverage; report.availability_percent = availability; report.outage_count = len(outage_rows); report.mttr_seconds = mttr; report.mtbf_seconds = mtbf; report.sla_target_percent = sla_target; report.sla_breached = None if availability is None else availability < sla_target; report.downtime_reasons = {reason: sum(1 for _, outage, _, _ in outage_rows if (outage.reason or "device_unreachable") == reason) for reason in {outage.reason or "device_unreachable" for _, outage, _, _ in outage_rows}}; report.generated_by = generated_by; report.generated_at = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    # Populate all non-null report fields before flushing to obtain its PK.
    db.flush()
    for old in list(report.outages): db.delete(old)
    db.flush()
    for device, outage, duration, is_planned in outage_rows: db.add(AvailabilityOutage(report_id=report.id, entity_type="device", entity_id=device.id, start_time=outage.start, end_time=outage.end, duration_seconds=duration, ongoing=outage.ongoing, planned=is_planned, reason=outage.reason or "device_unreachable"))
    db.flush(); return report

def outage_views(db: Session, report: AvailabilityReport) -> list[dict]:
    rows = db.query(AvailabilityOutage).filter(AvailabilityOutage.report_id == report.id).order_by(AvailabilityOutage.start_time.asc()).all()
    return [{"id": row.id, "device_id": row.entity_id, "start_time": row.start_time, "end_time": row.end_time, "duration_seconds": row.duration_seconds, "ongoing": row.ongoing, "planned": row.planned, "reason": row.reason} for row in rows]
