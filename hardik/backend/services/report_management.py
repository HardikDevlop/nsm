from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from backend.config.settings import get_settings
from backend.models import Alert, Device, DeviceMetric, DeviceStatusHistory, Interface
from backend.models.snmp import DeviceInventory, InterfaceStatistic, PollingHistory, SNMPCredential
from backend.models.identity import DeviceIdentity
from backend.schemas.nms import (
    ReportAlertDetail, ReportInterfaceDetail, ReportInventory, ReportManagementFilters,
    ReportManagementRecord, ReportManagementSection, ReportManagementSummary,
    ReportManagementTrends, ReportTrendAlertPoint, ReportTrendAvailabilityPoint,
    ReportTrendBandwidthPoint, ReportTrendPerformancePoint,
)
from backend.services.availability import build_intervals

REPORT_ALERT_DETAIL_LIMIT = 100
REPORT_INTERFACE_DETAIL_LIMIT = 100

_REPORT_LOOKBACK = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "yearly": timedelta(days=365),
}


def _report_range(period: str, start_date: datetime | None, end_date: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(ZoneInfo(get_settings().report_timezone)).replace(tzinfo=None)
    if period == "custom":
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for custom range")
        # Date-only UI values arrive at midnight; include the complete selected end day.
        if end_date.time() == datetime.min.time():
            end_date = end_date + timedelta(days=1) - timedelta(microseconds=1)
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")
        return start_date, end_date
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == "yesterday":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start - timedelta(days=1), today_start - timedelta(microseconds=1)
    delta = _REPORT_LOOKBACK.get(period)
    if not delta:
        raise ValueError("Invalid period")
    return now - delta, now


def _percent(part: int, total: int) -> float:
    return round((part / total) * 100, 2) if total else 0.0


def _report_trend_bucket_range(start: datetime, end: datetime) -> tuple[str, list[datetime]]:
    span = end - start
    if span <= timedelta(days=2):
        granularity, step = "hourly", timedelta(hours=1)
        current = start.replace(minute=0, second=0, microsecond=0)
        advance = lambda value: value + step
    elif span <= timedelta(days=90):
        granularity, step = "daily", timedelta(days=1)
        current = start.replace(hour=0, minute=0, second=0, microsecond=0)
        advance = lambda value: value + step
    else:
        granularity = "monthly"
        current = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        advance = lambda value: value.replace(year=value.year + (1 if value.month == 12 else 0), month=1 if value.month == 12 else value.month + 1)
    buckets = []
    while current < end:
        buckets.append(current)
        current = advance(current)
    return granularity, buckets


def _build_report_trends(
    period_start: datetime, period_end: datetime, devices: list[Device], history: list, prior_by_device: dict[int, object], metric_rows: list, iface_rows: list, alerts: list,
) -> ReportManagementTrends:
    granularity, buckets = _report_trend_bucket_range(period_start, period_end)
    bucket_end = {bucket: (buckets[index + 1] if index + 1 < len(buckets) else period_end) for index, bucket in enumerate(buckets)}
    def bucket_for(value: datetime):
        for bucket in reversed(buckets):
            if value >= bucket: return bucket
        return None
    down_states = {"offline", "down", "unreachable"}
    availability_points = []
    events_by_device: dict[int, list] = {}
    for event in history:
        events_by_device.setdefault(event.device_id, []).append(event)
    online_seconds = {bucket: 0.0 for bucket in buckets}; down_seconds = {bucket: 0.0 for bucket in buckets}
    for device in devices:
        events = sorted(events_by_device.get(device.id, []), key=lambda item: (item.timestamp, item.id))
        state = str(getattr(prior_by_device.get(device.id), "new_status", None) or "unknown").lower()
        cursor = period_start
        for event in events:
            timestamp = min(max(event.timestamp, period_start), period_end)
            if timestamp > cursor and state in ("online", "up", *down_states):
                segment_start = cursor
                while segment_start < timestamp:
                    bucket = bucket_for(segment_start)
                    if bucket is None: break
                    segment_end = min(timestamp, bucket_end[bucket])
                    target = online_seconds if state in ("online", "up") else down_seconds
                    target[bucket] += max(0, (segment_end - segment_start).total_seconds())
                    segment_start = segment_end
            state, cursor = str(event.new_status or "unknown").lower(), timestamp
        if cursor < period_end and state in ("online", "up", *down_states):
            segment_start = cursor
            while segment_start < period_end:
                bucket = bucket_for(segment_start)
                if bucket is None: break
                segment_end = min(period_end, bucket_end[bucket])
                target = online_seconds if state in ("online", "up") else down_seconds
                target[bucket] += max(0, (segment_end - segment_start).total_seconds())
                segment_start = segment_end
    for bucket in buckets:
        known = online_seconds[bucket] + down_seconds[bucket]
        availability_points.append(ReportTrendAvailabilityPoint(bucket=bucket, availability_percent=round(online_seconds[bucket] / known * 100, 2) if known else None))
    def averages(rows, fields):
        values = {bucket: {field: [] for field in fields} for bucket in buckets}
        for row in rows:
            bucket = bucket_for(row.created_at)
            if bucket:
                for field in fields:
                    value = getattr(row, field, None)
                    if value is not None: values[bucket][field].append(float(value))
        return values
    perf = averages(metric_rows, ("cpu_usage", "memory_usage", "latency")); bandwidth = averages(iface_rows, ("rx_mbps", "tx_mbps"))
    performance_points = [ReportTrendPerformancePoint(bucket=bucket, cpu_avg=round(sum(perf[bucket]["cpu_usage"]) / len(perf[bucket]["cpu_usage"]), 2) if perf[bucket]["cpu_usage"] else None, memory_avg=round(sum(perf[bucket]["memory_usage"]) / len(perf[bucket]["memory_usage"]), 2) if perf[bucket]["memory_usage"] else None, latency_avg_ms=round(sum(perf[bucket]["latency"]) / len(perf[bucket]["latency"]), 2) if perf[bucket]["latency"] else None) for bucket in buckets]
    bandwidth_points = [ReportTrendBandwidthPoint(bucket=bucket, rx_mbps=round(sum(bandwidth[bucket]["rx_mbps"]) / len(bandwidth[bucket]["rx_mbps"]), 2) if bandwidth[bucket]["rx_mbps"] else None, tx_mbps=round(sum(bandwidth[bucket]["tx_mbps"]) / len(bandwidth[bucket]["tx_mbps"]), 2) if bandwidth[bucket]["tx_mbps"] else None) for bucket in buckets]
    alert_counts = {bucket: {"total": 0, "critical": 0, "warning": 0, "info": 0} for bucket in buckets}
    for alert in alerts:
        bucket = bucket_for(alert.created_at)
        if bucket:
            counts = alert_counts[bucket]; counts["total"] += 1
            if alert.severity == "critical": counts["critical"] += 1
            elif alert.severity == "info": counts["info"] += 1
            elif alert.severity in ("warning", "high", "medium"): counts["warning"] += 1
    alert_points = [ReportTrendAlertPoint(bucket=bucket, **alert_counts[bucket]) for bucket in buckets]
    return ReportManagementTrends(bucket_granularity=granularity, availability=availability_points, performance=performance_points, bandwidth=bandwidth_points, alerts=alert_points)


def build_report_rows(db: Session, filters: ReportManagementFilters) -> tuple[ReportManagementSummary, list[dict[str, object]]]:
    _DSH = DeviceStatusHistory
    _IFS = InterfaceStatistic
    period_start, period_end = _report_range(filters.period, filters.start_date, filters.end_date)

    query = (
        db.query(Device)
        .options(joinedload(Device.site), joinedload(Device.device_type))
        .filter(Device.deleted_at.is_(None))
    )
    if filters.device_type_id is not None:
        query = query.filter(Device.device_type_id == filters.device_type_id)
    if filters.device_id is not None:
        query = query.filter(Device.id == filters.device_id)
    if filters.site_id is not None:
        query = query.filter(Device.site_id == filters.site_id)
    if filters.device_status != "all":
        query = query.filter(Device.status.in_({"up": ["online", "up"], "down": ["offline", "down"], "unreachable": ["unreachable"]}[filters.device_status]))

    devices = query.order_by(Device.hostname.asc()).all()
    device_ids = [device.id for device in devices]
    identities = {row.device_id: row for row in db.query(DeviceIdentity).filter(DeviceIdentity.device_id.in_(device_ids or [0])).all()}
    inventory_ranked = (
        db.query(
            DeviceInventory.id.label("inventory_id"),
            func.row_number().over(
                partition_by=DeviceInventory.device_id,
                order_by=(DeviceInventory.created_at.desc(), DeviceInventory.id.desc()),
            ).label("row_number"),
        )
        .filter(DeviceInventory.device_id.in_(device_ids or [0]))
        .subquery()
    )
    inventory_rows = (
        db.query(DeviceInventory)
        .join(inventory_ranked, DeviceInventory.id == inventory_ranked.c.inventory_id)
        .filter(inventory_ranked.c.row_number == 1)
        .all()
    )
    inventories = {row.device_id: row for row in inventory_rows}
    snmp_versions = {row.device_id: row.version for row in db.query(SNMPCredential).filter(SNMPCredential.device_id.in_(device_ids or [0])).all()}

    history = (
        db.query(_DSH)
        .filter(_DSH.timestamp >= period_start, _DSH.timestamp < period_end, _DSH.device_id.in_(device_ids or [0]))
        .order_by(_DSH.device_id.asc(), _DSH.timestamp.asc(), _DSH.id.asc())
        .all()
    )
    prior_ranked = (
        db.query(
            _DSH.id.label("status_id"),
            func.row_number().over(
                partition_by=_DSH.device_id,
                order_by=(_DSH.timestamp.desc(), _DSH.id.desc()),
            ).label("row_number"),
        )
        .filter(_DSH.timestamp < period_start, _DSH.device_id.in_(device_ids or [0]))
        .subquery()
    )
    prior_history = (
        db.query(_DSH)
        .join(prior_ranked, _DSH.id == prior_ranked.c.status_id)
        .filter(prior_ranked.c.row_number == 1)
        .all()
    )
    prior_by_device: dict[int, object] = {}
    for row in prior_history:
        prior_by_device.setdefault(row.device_id, row)
    period_seconds = max(1.0, (period_end - period_start).total_seconds())
    downtime_by_device: dict[int, int] = {}
    availability_by_device: dict[int, float | None] = {}
    availability_raw_by_device: dict[int, float | None] = {}
    availability_details: dict[int, tuple[list[object], datetime | None, datetime | None, str]] = {}
    history_by_device_for_window: dict[int, list] = {}
    for row in history:
        history_by_device_for_window.setdefault(row.device_id, []).append(row)
    # Use the same interval semantics as the canonical availability service.
    # The latest pre-period event is sufficient because build_intervals applies
    # the same evidence-freshness rule before carrying it into the period.
    for device in devices:
        events = ([prior_by_device[device.id]] if device.id in prior_by_device else []) + history_by_device_for_window.get(device.id, [])
        intervals, outages, _ = build_intervals(events, period_start, period_end, device.created_at)
        online_seconds = sum(max(0, int((item.end - item.start).total_seconds())) for item in intervals if item.state == "online")
        offline_seconds = sum(max(0, int((item.end - item.start).total_seconds())) for item in intervals if item.state == "offline")
        known_seconds = online_seconds + offline_seconds
        availability_raw = (online_seconds / known_seconds) * 100 if known_seconds else None
        availability_raw_by_device[device.id] = availability_raw
        availability_by_device[device.id] = round(availability_raw, 2) if availability_raw is not None else None
        downtime_by_device[device.id] = offline_seconds
        last_outage = max((item.start for item in outages), default=None)
        last_recovery = max((item.end for item in outages if item.end is not None), default=None)
        current_state = next((item.state for item in reversed(intervals) if item.state != "unknown"), "unknown")
        availability_details[device.id] = (outages, last_outage, last_recovery, current_state)

    polling = (
        db.query(PollingHistory)
        .filter(PollingHistory.device_id.in_(device_ids or [0]), PollingHistory.created_at >= period_start, PollingHistory.created_at <= period_end)
        .all()
    )
    metric_aggregate_rows = (
        db.query(
            DeviceMetric.device_id.label("device_id"),
            func.avg(DeviceMetric.cpu_usage).label("avg_cpu"),
            func.max(DeviceMetric.cpu_usage).label("max_cpu"),
            func.avg(DeviceMetric.memory_usage).label("avg_memory"),
            func.max(DeviceMetric.memory_usage).label("max_memory"),
            func.avg(DeviceMetric.latency).label("avg_latency"),
            func.max(DeviceMetric.latency).label("max_latency"),
            func.avg(DeviceMetric.packet_loss).label("avg_loss"),
            func.max(DeviceMetric.packet_loss).label("max_loss"),
            func.count(DeviceMetric.id).label("sample_count"),
        )
        .filter(DeviceMetric.device_id.in_(device_ids or [0]), DeviceMetric.created_at >= period_start, DeviceMetric.created_at <= period_end)
        .group_by(DeviceMetric.device_id)
        .all()
    )
    metric_aggregates = {row.device_id: row for row in metric_aggregate_rows}
    # Exact nearest-rank P95 still uses only the metric columns required for
    # percentile calculation; averages/maxima come from the grouped query.
    metric_sample_rows = (
        db.query(DeviceMetric.device_id, DeviceMetric.cpu_usage, DeviceMetric.memory_usage, DeviceMetric.latency, DeviceMetric.packet_loss)
        .filter(DeviceMetric.device_id.in_(device_ids or [0]), DeviceMetric.created_at >= period_start, DeviceMetric.created_at <= period_end)
        .all()
    )
    iface_rows = (
        db.query(_IFS)
        .filter(_IFS.device_id.in_(device_ids or [0]), _IFS.created_at >= period_start, _IFS.created_at <= period_end)
        .all()
    )
    iface_device_aggregate_rows = (
        db.query(
            _IFS.device_id.label("device_id"),
            func.avg(_IFS.rx_mbps).label("avg_rx"),
            func.avg(_IFS.tx_mbps).label("avg_tx"),
            func.avg(_IFS.utilization_percent).label("avg_utilization"),
            func.max(_IFS.utilization_percent).label("max_utilization"),
            func.avg(_IFS.error_rate).label("avg_error_rate"),
            func.count(_IFS.id).label("sample_count"),
        )
        .filter(_IFS.device_id.in_(device_ids or [0]), _IFS.created_at >= period_start, _IFS.created_at <= period_end)
        .group_by(_IFS.device_id)
        .all()
    )
    iface_device_aggregates = {row.device_id: row for row in iface_device_aggregate_rows}

    # InterfaceStatistic contains counters/utilization only.  Port state is
    # persisted on the real Interface record, so use that table for status.
    interface_states = (
        db.query(Interface)
        .filter(Interface.device_id.in_(device_ids or [0]))
        .all()
    )

    history_by_device: dict[int, list] = {}
    for row in history:
        history_by_device.setdefault(row.device_id, []).append(row)
    polling_by_device: dict[int, list] = {}
    for row in polling:
        polling_by_device.setdefault(row.device_id, []).append(row)
    metrics_by_device: dict[int, list] = {}
    for row in metric_sample_rows:
        metrics_by_device.setdefault(row.device_id, []).append(row)
    iface_by_device: dict[int, list] = {}
    for row in iface_rows:
        iface_by_device.setdefault(row.device_id, []).append(row)
    interface_state_by_device: dict[int, list] = {}
    for row in interface_states:
        interface_state_by_device.setdefault(row.device_id, []).append(row)

    records: list[ReportManagementRecord] = []
    protocol_filter = filters.protocol
    for device in devices:
        device_hist = history_by_device.get(device.id, [])
        if protocol_filter == "icmp" and not device_hist:
            continue
        if protocol_filter == "snmp" and not (polling_by_device.get(device.id) or metrics_by_device.get(device.id) or iface_by_device.get(device.id)):
            continue
        uptime = sum(1 for item in device_hist if item.new_status == "online")
        downtime = downtime_by_device.get(device.id, 0)
        total_transitions = len(device_hist)
        availability_pct = availability_by_device.get(device.id)
        snmp_ok = sum(1 for item in polling_by_device.get(device.id, []) if item.status == "success")
        snmp_total = len(polling_by_device.get(device.id, []))
        icmp_ok = uptime
        icmp_total = total_transitions or (1 if device.status else 0)
        metric_samples = metrics_by_device.get(device.id, [])
        cpu_vals = [row.cpu_usage for row in metric_samples if row.cpu_usage is not None]
        mem_vals = [row.memory_usage for row in metric_samples if row.memory_usage is not None]
        latency_vals = [row.latency for row in metric_samples if row.latency is not None]
        loss_vals = [row.packet_loss for row in metric_samples if row.packet_loss is not None]
        metric_aggregate = metric_aggregates.get(device.id)
        iface_vals = [row.utilization_percent for row in iface_by_device.get(device.id, []) if row.utilization_percent is not None]
        def p95(values):
            if not values: return None
            ordered = sorted(values)
            return round(ordered[max(0, int(__import__("math").ceil(len(ordered) * 0.95)) - 1)], 2)
        state_rows = interface_state_by_device.get(device.id, [])
        iface_down = sum(1 for row in state_rows if (row.status or "").lower() == "down")
        avg_cpu = round(float(metric_aggregate.avg_cpu), 2) if metric_aggregate and metric_aggregate.avg_cpu is not None else None
        avg_mem = round(float(metric_aggregate.avg_memory), 2) if metric_aggregate and metric_aggregate.avg_memory is not None else None
        avg_latency = round(float(metric_aggregate.avg_latency), 2) if metric_aggregate and metric_aggregate.avg_latency is not None else None
        avg_loss = round(float(metric_aggregate.avg_loss), 2) if metric_aggregate and metric_aggregate.avg_loss is not None else None
        iface_aggregate = iface_device_aggregates.get(device.id)
        avg_iface = round(float(iface_aggregate.avg_utilization), 2) if iface_aggregate and iface_aggregate.avg_utilization is not None else None
        snmp_success_rate = _percent(snmp_ok, snmp_total) if snmp_total else None
        icmp_success_rate = _percent(icmp_ok, icmp_total) if icmp_total else None
        performance_score = None
        score_parts = [v for v in [avg_cpu, avg_mem, avg_iface] if v is not None]
        if score_parts:
            performance_score = round(sum(score_parts) / len(score_parts), 2)
        health_points = 100.0
        if snmp_success_rate is not None:
            health_points -= max(0.0, 100.0 - snmp_success_rate) * 0.5
        if icmp_success_rate is not None:
            health_points -= max(0.0, 100.0 - icmp_success_rate) * 0.3
        if iface_down:
            health_points -= min(30.0, iface_down * 5.0)
        snmp_health = "healthy" if health_points >= 85 else "degraded" if health_points >= 60 else "critical"
        sla_target = 99.0
        sla_status = "unknown" if availability_pct is None else "met" if availability_raw_by_device.get(device.id, availability_pct) >= sla_target else "breached"
        allowed_downtime = round(period_seconds * (1 - sla_target / 100))
        sla_breach_seconds = None if availability_pct is None else max(0, downtime - allowed_downtime)
        protocol = "snmp" if protocol_filter == "snmp" else "icmp" if protocol_filter == "icmp" else "mixed"
        device_outages, last_outage_time, last_recovery_time, current_status = availability_details.get(device.id, ([], None, None, str(device.status or "unknown").lower()))
        interface_details = []
        for iface in state_rows:
            samples = [row for row in iface_by_device.get(device.id, []) if row.interface_id == iface.id]
            util_vals = [row.utilization_percent for row in samples if row.utilization_percent is not None]
            rx_vals = [row.rx_mbps for row in samples if row.rx_mbps is not None]
            tx_vals = [row.tx_mbps for row in samples if row.tx_mbps is not None]
            err_vals = [row.error_rate for row in samples if row.error_rate is not None]
            ordered_util = sorted(util_vals)
            p95_util = round(ordered_util[max(0, int(__import__("math").ceil(len(ordered_util) * 0.95)) - 1)], 2) if ordered_util else None
            interface_details.append(ReportInterfaceDetail(
                interface_id=iface.id,
                name=iface.interface_name,
                speed=iface.speed,
                operational_status=iface.status,
                current_status=iface.status,
                avg_utilization_pct=round(sum(util_vals) / len(util_vals), 2) if util_vals else None,
                max_utilization_pct=round(max(util_vals), 2) if util_vals else None,
                p95_utilization_pct=p95_util,
                avg_inbound_mbps=round(sum(rx_vals) / len(rx_vals), 2) if rx_vals else None,
                avg_outbound_mbps=round(sum(tx_vals) / len(tx_vals), 2) if tx_vals else None,
                avg_error_rate_pct=round(sum(err_vals) / len(err_vals), 4) if err_vals else None,
            ))
        identity = identities.get(device.id)
        inventory = inventories.get(device.id)
        mac = device.mac_address or ((identity.mac_addresses or [None])[0] if identity else None)
        inventory_data = ReportInventory(hostname=device.hostname, ip_address=device.ip_address, mac_address=mac, device_type=identity.device_type if identity and identity.device_type else (device.device_type.name if device.device_type else None), vendor=identity.vendor if identity and identity.vendor else (device.vendor.vendor_name if device.vendor else None), model=(inventory.model if inventory and inventory.model else (identity.model if identity else None)) or device.model, serial_number=(inventory.serial_number if inventory and inventory.serial_number else (identity.serial_number if identity else None)) or device.serial_number, os_version=identity.os_version if identity else None, firmware_version=(inventory.firmware if inventory and inventory.firmware else (identity.firmware_version if identity else None)) or device.firmware_version, site=device.site.name if device.site else None, snmp_version=snmp_versions.get(device.id), first_discovered_at=device.created_at, last_seen_at=device.last_seen)
        records.append(ReportManagementRecord(
            device_id=device.id,
            hostname=device.hostname,
            ip_address=device.ip_address,
            site_name=device.site.name if device.site else None,
            device_type_name=device.device_type.name if device.device_type else None,
            protocol=protocol,
            availability_pct=availability_pct,
            downtime_seconds=downtime,
            outage_count=len(device_outages),
            longest_outage_seconds=max((round(((item.end or period_end) - item.start).total_seconds()) for item in device_outages), default=0),
            last_outage_time=last_outage_time,
            last_recovery_time=last_recovery_time,
            current_status=current_status,
            snmp_success_rate=snmp_success_rate,
            icmp_success_rate=icmp_success_rate,
            snmp_health=snmp_health,
            performance_score=performance_score,
            interface_count=(len({row.interface_id for row in iface_by_device.get(device.id, [])}) or len(state_rows) or None),
            interface_down_count=iface_down or None,
            avg_cpu_percent=avg_cpu,
            avg_memory_percent=avg_mem,
            avg_latency_ms=avg_latency,
            packet_loss_pct=avg_loss,
            max_cpu_percent=round(float(metric_aggregate.max_cpu), 2) if metric_aggregate and metric_aggregate.max_cpu is not None else None,
            p95_cpu_percent=p95(cpu_vals),
            max_memory_percent=round(float(metric_aggregate.max_memory), 2) if metric_aggregate and metric_aggregate.max_memory is not None else None,
            p95_memory_percent=p95(mem_vals),
            max_latency_ms=round(float(metric_aggregate.max_latency), 2) if metric_aggregate and metric_aggregate.max_latency is not None else None,
            p95_latency_ms=p95(latency_vals),
            avg_packet_loss_pct=avg_loss,
            max_packet_loss_pct=round(float(metric_aggregate.max_loss), 2) if metric_aggregate and metric_aggregate.max_loss is not None else None,
            inventory=inventory_data,
                        interface_details=interface_details[:REPORT_INTERFACE_DETAIL_LIMIT],
            interface_details_total=len(interface_details),
            interface_details_truncated=len(interface_details) > REPORT_INTERFACE_DETAIL_LIMIT,
            sla_target_percent=sla_target,
            sla_variance_percent=round(availability_raw_by_device[device.id] - sla_target, 6) if availability_raw_by_device[device.id] is not None else None,
            allowed_downtime_seconds=allowed_downtime,
            sla_breach_seconds=sla_breach_seconds,
            sla_status=sla_status,
            period_start=period_start,
            period_end=period_end,
        ))

    known_availability = [availability_raw_by_device.get(r.device_id) for r in records if availability_raw_by_device.get(r.device_id) is not None]
    availability_pct = round(sum(known_availability) / len(known_availability), 2) if known_availability else None
    downtime_seconds = sum(r.downtime_seconds for r in records)
    snmp_devices = sum(1 for r in records if r.snmp_success_rate is not None)
    icmp_devices = sum(1 for r in records if r.icmp_success_rate is not None)
    avg_snmp_health = round(sum(100 if r.snmp_health == "healthy" else 70 if r.snmp_health == "degraded" else 40 for r in records) / len(records), 2) if records else None
    avg_performance_score = round(sum(r.performance_score for r in records if r.performance_score is not None) / max(1, len([r for r in records if r.performance_score is not None])), 2) if any(r.performance_score is not None for r in records) else None
    sla_met_devices = sum(1 for r in records if r.sla_status == "met")
    sla_breached_devices = sum(1 for r in records if r.sla_status == "breached")
    sla_unknown_devices = sum(1 for r in records if r.sla_status == "unknown")
    sla_configured_devices = sla_met_devices + sla_breached_devices
    sla_met_pct = _percent(sla_met_devices, sla_configured_devices)
    alert_filters = [
        Alert.deleted_at.is_(None),
        Alert.created_at >= period_start,
        Alert.created_at <= period_end,
        Alert.device_id.in_(device_ids or [0]),
    ]
    if filters.alert_severity != "all":
        alert_filters.append(Alert.severity == filters.alert_severity)

    alert_summary_row = db.query(
        func.count(Alert.id).label("total"),
        func.count(case((Alert.severity == "critical", 1))).label("critical"),
        func.count(case((Alert.severity.in_(("warning", "high", "medium")), 1))).label("warning"),
        func.count(case((Alert.severity == "info", 1))).label("info"),
        func.count(case((Alert.status.in_(("open", "acknowledged")), 1))).label("active"),
        func.count(case((Alert.status == "resolved", 1))).label("resolved"),
        func.count(case(((Alert.status == "acknowledged") | Alert.acknowledged_by.isnot(None), 1))).label("acknowledged"),
    ).filter(*alert_filters).one()
    total_alerts = int(alert_summary_row.total or 0)
    critical_alerts = int(alert_summary_row.critical or 0)
    warning_alerts = int(alert_summary_row.warning or 0)
    info_alerts = int(alert_summary_row.info or 0)
    active_alerts = int(alert_summary_row.active or 0)
    resolved_alerts = int(alert_summary_row.resolved or 0)
    acknowledged_alerts = int(alert_summary_row.acknowledged or 0)

    alert_device_rows = db.query(
        Alert.device_id.label("device_id"),
        func.count(Alert.id).label("total"),
        func.count(case((Alert.severity == "critical", 1))).label("critical"),
        func.count(case((Alert.severity.in_(("warning", "high", "medium")), 1))).label("warning"),
        func.count(case((Alert.status.in_(("open", "acknowledged")), 1))).label("active"),
        func.count(case((Alert.status == "resolved", 1))).label("resolved"),
    ).filter(*alert_filters).group_by(Alert.device_id).order_by(func.count(Alert.id).desc(), Alert.device_id.asc()).all()
    alert_counts_by_device = {row.device_id: row for row in alert_device_rows if row.device_id is not None}
    most_affected_device_id = alert_device_rows[0].device_id if alert_device_rows else None
    most_affected_device = next((d for d in devices if d.id == most_affected_device_id), None)

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        alert_mttr_value = db.query(
            func.avg(func.extract("epoch", Alert.resolved_at - Alert.created_at))
        ).filter(*alert_filters, Alert.resolved_at.isnot(None), Alert.created_at.isnot(None)).scalar()
        alert_mttr_seconds = round(float(alert_mttr_value), 2) if alert_mttr_value is not None else None
    else:
        mttr_rows = db.query(Alert.created_at, Alert.resolved_at).filter(*alert_filters, Alert.resolved_at.isnot(None), Alert.created_at.isnot(None)).all()
        durations = [max(0, (resolved - created).total_seconds()) for created, resolved in mttr_rows]
        alert_mttr_seconds = round(sum(durations) / len(durations), 2) if durations else None

    detail_alerts = (
        db.query(Alert)
        .options(joinedload(Alert.device).joinedload(Device.site))
        .filter(*alert_filters)
        .order_by(Alert.created_at.desc(), Alert.id.desc())
        .limit(REPORT_ALERT_DETAIL_LIMIT)
        .all()
    )
    alert_details = [ReportAlertDetail(alert_id=a.id, device_id=a.device_id, device_name=a.device.hostname if a.device else None, site_name=a.device.site.name if a.device and a.device.site else None, severity=a.severity, title=a.title, description=a.description, created_at=a.created_at, acknowledged_by=a.acknowledged_by, resolved_at=a.resolved_at, duration_seconds=max(0, int((a.resolved_at - a.created_at).total_seconds())) if a.resolved_at and a.created_at else None, status=a.status) for a in detail_alerts]
    alert_details_by_device: dict[int, list[ReportAlertDetail]] = {}
    for detail in alert_details:
        if detail.device_id is not None:
            alert_details_by_device.setdefault(detail.device_id, []).append(detail)

    trend_metric_rows = []
    trend_iface_rows = []
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        granularity = _report_trend_bucket_range(period_start, period_end)[0]
        metric_bucket = func.date_trunc({"hourly": "hour", "daily": "day", "monthly": "month"}[granularity], DeviceMetric.created_at)
        metric_trend = db.query(metric_bucket.label("bucket"), func.avg(DeviceMetric.cpu_usage).label("cpu_avg"), func.avg(DeviceMetric.memory_usage).label("memory_avg"), func.avg(DeviceMetric.latency).label("latency_avg")).filter(DeviceMetric.device_id.in_(device_ids or [0]), DeviceMetric.created_at >= period_start, DeviceMetric.created_at <= period_end).group_by(metric_bucket).order_by(metric_bucket).all()
        iface_bucket = func.date_trunc({"hourly": "hour", "daily": "day", "monthly": "month"}[granularity], _IFS.created_at)
        iface_trend = db.query(iface_bucket.label("bucket"), func.avg(_IFS.rx_mbps).label("rx_mbps"), func.avg(_IFS.tx_mbps).label("tx_mbps")).filter(_IFS.device_id.in_(device_ids or [0]), _IFS.created_at >= period_start, _IFS.created_at <= period_end).group_by(iface_bucket).order_by(iface_bucket).all()
        trend_metric_rows = [SimpleNamespace(created_at=row.bucket, cpu_usage=row.cpu_avg, memory_usage=row.memory_avg, latency=row.latency_avg) for row in metric_trend]
        trend_iface_rows = [SimpleNamespace(created_at=row.bucket, rx_mbps=row.rx_mbps, tx_mbps=row.tx_mbps) for row in iface_trend]
    else:
        trend_metric_rows, trend_iface_rows = metric_sample_rows, iface_rows
    if dialect == "postgresql":
        alert_granularity = _report_trend_bucket_range(period_start, period_end)[0]
        alert_bucket = func.date_trunc({"hourly": "hour", "daily": "day", "monthly": "month"}[alert_granularity], Alert.created_at)
        alert_trend_rows = db.query(
            alert_bucket.label("bucket"),
            func.count(Alert.id).label("total"),
            func.count(case((Alert.severity == "critical", 1))).label("critical"),
            func.count(case((Alert.severity.in_(("warning", "high", "medium")), 1))).label("warning"),
            func.count(case((Alert.severity == "info", 1))).label("info"),
        ).filter(*alert_filters).group_by(alert_bucket).order_by(alert_bucket).all()
        alert_trend_points = [ReportTrendAlertPoint(bucket=row.bucket, total=int(row.total or 0), critical=int(row.critical or 0), warning=int(row.warning or 0), info=int(row.info or 0)) for row in alert_trend_rows]
        trends = _build_report_trends(period_start, period_end, devices, history, prior_by_device, trend_metric_rows, trend_iface_rows, [])
        trends.alerts = alert_trend_points
    else:
        alert_trend_source = db.query(Alert.created_at, Alert.severity).filter(*alert_filters).all()
        alert_trend_rows = [SimpleNamespace(created_at=row.created_at, severity=row.severity) for row in alert_trend_source]
        trends = _build_report_trends(period_start, period_end, devices, history, prior_by_device, trend_metric_rows, trend_iface_rows, alert_trend_rows)
    total_outages = sum(r.outage_count for r in records)
    for record in records:
        alert_row = alert_counts_by_device.get(record.device_id)
        record.alert_count = int(alert_row.total or 0) if alert_row else 0
        record.critical_alert_count = int(alert_row.critical or 0) if alert_row else 0
        record.warning_alert_count = int(alert_row.warning or 0) if alert_row else 0
        record.active_alert_count = int(alert_row.active or 0) if alert_row else 0
        record.resolved_alert_count = int(alert_row.resolved or 0) if alert_row else 0
        record.alert_mttr_seconds = None
        record.alert_details = alert_details_by_device.get(record.device_id, [])
        record.alert_details_total = record.alert_count
        record.alert_details_truncated = record.alert_count > REPORT_ALERT_DETAIL_LIMIT
    current_statuses = [str(device.status or "").lower() for device in devices]
    type_counts = {}; vendor_counts = {}; unknown_assets = 0
    for record in records:
        inv = record.inventory
        type_key = inv.device_type or "Unknown"; vendor_key = inv.vendor or "Unknown"
        type_counts[type_key] = type_counts.get(type_key, 0) + 1; vendor_counts[vendor_key] = vendor_counts.get(vendor_key, 0) + 1
        if not inv.vendor and not inv.model and not inv.serial_number: unknown_assets += 1
    summary = ReportManagementSummary(
        filters=filters,
        period_start=period_start,
        period_end=period_end,
        total_devices=len(devices),
        total_records=len(records),
        availability_pct=availability_pct,
        downtime_seconds=downtime_seconds,
        avg_snmp_health=avg_snmp_health,
        avg_performance_score=avg_performance_score,
        sla_met_pct=sla_met_pct,
        sla_configured_devices=sla_configured_devices, sla_met_devices=sla_met_devices, sla_breached_devices=sla_breached_devices, sla_unknown_devices=sla_unknown_devices,
        snmp_devices=snmp_devices,
        icmp_devices=icmp_devices,
        up_devices=sum(x in ("online", "up") for x in current_statuses), down_devices=sum(x in ("offline", "down") for x in current_statuses), unreachable_devices=sum(x == "unreachable" for x in current_statuses), total_alerts=total_alerts, critical_alerts=critical_alerts, total_outages=total_outages,
        warning_alerts=warning_alerts, info_alerts=info_alerts, active_alerts=active_alerts, resolved_alerts=resolved_alerts, acknowledged_alerts=acknowledged_alerts,
        alert_mttr_seconds=alert_mttr_seconds, most_affected_device_id=most_affected_device_id, most_affected_device_name=most_affected_device.hostname if most_affected_device else None,
        alert_details=alert_details, alert_details_total=total_alerts, alert_details_truncated=total_alerts > REPORT_ALERT_DETAIL_LIMIT,
        trends=trends, inventory_total_assets=len(records), inventory_by_device_type=type_counts, inventory_by_vendor=vendor_counts, inventory_unknown_assets=unknown_assets,
        sections={
            "availability": ReportManagementSection(title="Availability", count=len(records), average=availability_pct, maximum=max((r.availability_pct for r in records if r.availability_pct is not None), default=None), minimum=min((r.availability_pct for r in records if r.availability_pct is not None), default=None)),
            "downtime": ReportManagementSection(title="Downtime", count=len(records), average=round(downtime_seconds / len(records), 2) if records else None, maximum=max((r.downtime_seconds for r in records), default=None), minimum=min((r.downtime_seconds for r in records), default=None)),
            "snmp_health": ReportManagementSection(title="SNMP Health", count=snmp_devices, average=avg_snmp_health),
            "interface": ReportManagementSection(title="Interface/Port", count=sum(r.interface_count or 0 for r in records)),
            "performance": ReportManagementSection(title="Performance", count=sum(1 for r in records if r.performance_score is not None), average=avg_performance_score),
            "sla": ReportManagementSection(title="SLA Summary", count=len(records), average=sla_met_pct),
        },
        records=records,
    )
    export_rows = [r.model_dump() for r in records]
    return summary, export_rows



