import time
from backend.utils.time import utc_now

from sqlalchemy.orm import Session

from backend.models import DeviceMetric, DeviceStatusHistory, Device
from backend.services.alerting import create_offline_alert
from backend.services.discovery import _ping


def _record_status_change(db: Session, device: Device, new_status: str, reason: str) -> None:
    now = utc_now()
    old_status = device.status
    if old_status == new_status:
        return
    db.add(
        DeviceStatusHistory(
            device_id=device.id,
            old_status=old_status,
            new_status=new_status,
            change_reason=reason,
        )
    )
    if device.last_status_change:
        elapsed = int((now - device.last_status_change).total_seconds())
        if old_status == "online":
            device.uptime_seconds += elapsed
        elif old_status == "offline":
            device.downtime_seconds += elapsed
    device.status = new_status
    device.last_status_change = now
    if new_status == "offline":
        create_offline_alert(db, device.id, device.hostname, device.ip_address)


def run_monitoring_check(
    db: Session,
    ip_addresses: list[str] | None = None,
    timeout_ms: int = 1000,
) -> list[Device]:
    query = db.query(Device).filter(Device.deleted_at.is_(None), Device.monitoring_status.is_(True))
    if ip_addresses:
        query = query.filter(Device.ip_address.in_(ip_addresses))
    devices = query.all()

    for device in devices:
        started = time.perf_counter()
        reachable = _ping(device.ip_address, timeout_ms)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if reachable:
            device.last_seen = utc_now()
            _record_status_change(db, device, "online", "ICMP check succeeded")
            db.add(DeviceMetric(device_id=device.id, latency=latency_ms, packet_loss=0.0))
        else:
            _record_status_change(db, device, "offline", "ICMP check failed")
            db.add(DeviceMetric(device_id=device.id, latency=None, packet_loss=100.0))
    db.flush()
    return devices
