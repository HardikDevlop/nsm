"""Centralized SNMP Polling Scheduler with Worker Pool.

Architecture:
- Single scheduler process reads monitoring_configs from DB
- Schedules jobs based on next_poll_at timestamps
- Worker pool executes SNMP polls asynchronously
- Job identity: device_id + module_name (unique)
- Survives application restarts by reconstructing from DB
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.session import SessionLocal
from backend.models.snmp import MonitoringConfig, MonitoringStatus, PollingHistory, PollStatus
from backend.models.identity import DeviceCapabilities
from backend.snmp.collector import SNMPService
from backend.snmp.credentials import SNMPCredentials
from backend.utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)

# Module name to collector name mapping
MODULE_COLLECTOR_MAP = {
    "system": "system",
    "cpu": "cpu",
    "memory": "memory",
    "storage": "storage",
    "interfaces": "interfaces",
    "environment": "environment",
    "vlan": "vlan",
    "lldp": "lldp",
    "cdp": "cdp",
    "routing": "routing",
    "arp": "arp",
    "mac_table": "mac_table",
    "inventory": "inventory",
    "topology": "topology",
    "firewall": "firewall",
    "wireless": "wireless",
    "health": "health",
}

# Default intervals per module (seconds)
DEFAULT_INTERVALS = {
    "system": 300,
    "cpu": 60,
    "memory": 60,
    "storage": 300,
    "interfaces": 30,
    "environment": 300,
    "vlan": 600,
    "lldp": 600,
    "cdp": 600,
    "routing": 600,
    "arp": 300,
    "mac_table": 300,
    "inventory": 86400,
    "topology": 600,
    "firewall": 60,
    "wireless": 60,
    "health": 60,
}

# Allowed interval options for UI
ALLOWED_INTERVALS = [30, 60, 120, 300, 600]


@dataclass
class PollJob:
    """Represents a single polling job."""
    device_id: int
    module_name: str
    collector_name: str
    interval_seconds: int
    config_id: int

    @property
    def job_id(self) -> str:
        return f"{self.device_id}:{self.module_name}"


class SNMPPoller:
    """Executes SNMP polls for a single device+module."""

    def __init__(self, db: Session):
        self.db = db

    def _get_credentials(self, device_id: int) -> SNMPCredentials | None:
        """Get decrypted SNMP credentials for a device."""
        from backend.models import DeviceCredential
        cred = self.db.query(DeviceCredential).filter(
            DeviceCredential.device_id == device_id
        ).first()
        if not cred:
            return None

        version = cred.snmp_version or "v2c"
        community = None
        if cred.community_string:
            try:
                community = decrypt_secret(cred.community_string)
            except Exception:
                community = cred.community_string

        auth_pass = None
        if cred.auth_password:
            try:
                auth_pass = decrypt_secret(cred.auth_password)
            except Exception:
                auth_pass = cred.auth_password

        priv_pass = None
        if cred.privacy_password:
            try:
                priv_pass = decrypt_secret(cred.privacy_password)
            except Exception:
                priv_pass = cred.privacy_password

        return SNMPCredentials(
            version=version,
            community=community or "public",
            username=cred.username,
            auth_protocol=cred.auth_protocol,
            auth_password=auth_pass,
            privacy_protocol=cred.privacy_protocol,
            privacy_password=priv_pass,
            security_level=cred.security_level,
        )

    def _get_device_ip(self, device_id: int) -> str | None:
        from backend.models import Device
        device = self.db.query(Device).filter(Device.id == device_id).first()
        return device.ip_address if device else None

    def _is_module_supported(self, device_id: int, module_name: str) -> bool:
        """Check if the device supports this module."""
        cap = self.db.query(DeviceCapabilities).filter(
            DeviceCapabilities.device_id == device_id
        ).first()
        if not cap:
            return False
        cap_map = cap.to_map()
        return cap_map.get(module_name, False)

    async def poll(self, job: PollJob) -> dict[str, Any]:
        """Execute a single poll for the job."""
        from backend.models import Device
        device = self.db.query(Device).filter(Device.id == job.device_id).first()
        if not device:
            return {"success": False, "error": "Device not found"}

        ip = device.ip_address
        credentials = self._get_credentials(job.device_id)
        if not credentials:
            return {"success": False, "error": "No SNMP credentials"}

        # Check capability
        if not self._is_module_supported(job.device_id, job.module_name):
            return {"success": False, "error": "Module not supported", "not_supported": True}

        collector_name = MODULE_COLLECTOR_MAP.get(job.module_name, job.module_name)
        started = time.perf_counter()

        try:
            service = SNMPService(credentials=credentials, timeout=3.0)
            result = service.collect_domain(ip, collector_name)
            duration_ms = round((time.perf_counter() - started) * 1000, 1)

            supported = result.get("supported", False)
            data = result.get("data", {})

            # Persist latest values and history
            await self._persist_results(job, data, supported)

            return {
                "success": True,
                "supported": supported,
                "data": data,
                "duration_ms": duration_ms,
            }

        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.error("Poll failed for %s: %s", job.job_id, exc)
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": duration_ms,
            }

    async def _persist_results(self, job: PollJob, data: dict, supported: bool) -> None:
        """Persist poll results to latest-value tables and history."""
        module = job.module_name
        device_id = job.device_id
        now = datetime.utcnow()

        try:
            cap = self.db.query(DeviceCapabilities).filter(
                DeviceCapabilities.device_id == device_id
            ).first()
            if cap:
                detail = dict(cap.capability_detail or {})
                existing = detail.get(module, {}) if isinstance(detail.get(module), dict) else {}
                detail[module] = {
                    **existing,
                    "collector": module,
                    "supported": supported,
                    "timestamp": now.isoformat(),
                    "data": data or existing.get("data") or {},
                    "missing": existing.get("missing", []),
                    "warnings": existing.get("warnings", []),
                    "reason": None if supported else existing.get("reason") or "Module not supported",
                }
                cap.capability_detail = detail
                cap.updated_at = now

            if module == "cpu" and data:
                await self._persist_cpu(device_id, data, now)
            elif module == "memory" and data:
                await self._persist_memory(device_id, data, now)
            elif module == "storage" and data:
                await self._persist_storage(device_id, data, now)
            elif module == "interfaces" and data:
                await self._persist_interfaces(device_id, data, now)
            elif module == "environment" and data:
                await self._persist_environment(device_id, data, now)

            # Always persist to history tables
            await self._persist_history(device_id, module, data, supported, now)

            self.db.commit()
        except Exception as exc:
            logger.error("Failed to persist results for %s: %s", job.job_id, exc)
            self.db.rollback()

    async def _persist_cpu(self, device_id: int, data: dict, now: datetime) -> None:
        from backend.models.snmp import CPUStatistic, LatestCPU
        overall = data.get("overall_percent")
        per_core = data.get("per_core", [])
        load_avg = data.get("load_avg", {})

        # Latest
        latest = self.db.query(LatestCPU).filter(LatestCPU.device_id == device_id).first()
        if not latest:
            latest = LatestCPU(device_id=device_id)
            self.db.add(latest)
        latest.utilization_percent = overall
        latest.per_core = {
            str(c.get("index") or c.get("core")): c.get("percent") if c.get("percent") is not None else c.get("usage")
            for c in per_core
            if isinstance(c, dict) and (c.get("index") is not None or c.get("core") is not None)
        }
        latest.load_avg = load_avg
        latest.polled_at = now

        # History
        if overall is not None:
            hist = CPUStatistic(device_id=device_id, utilization_percent=overall, created_at=now)
            self.db.add(hist)

    async def _persist_memory(self, device_id: int, data: dict, now: datetime) -> None:
        from backend.models.snmp import MemoryStatistic, LatestMemory
        total = data.get("total_bytes")
        used = data.get("used_bytes")
        free = data.get("free_bytes")
        cached = data.get("cached_bytes")
        buffer_ = data.get("buffer_bytes")
        swap_total = data.get("swap_total_bytes")
        swap_free = data.get("swap_free_bytes")
        util = data.get("utilization_percent")

        latest = self.db.query(LatestMemory).filter(LatestMemory.device_id == device_id).first()
        if not latest:
            latest = LatestMemory(device_id=device_id)
            self.db.add(latest)
        latest.total_bytes = total
        latest.used_bytes = used
        latest.free_bytes = free
        latest.cached_bytes = cached
        latest.buffer_bytes = buffer_
        latest.swap_total = swap_total
        latest.swap_free = swap_free
        latest.utilization_percent = util
        latest.polled_at = now

        if total is not None or used is not None:
            hist = MemoryStatistic(
                device_id=device_id,
                total_bytes=total,
                used_bytes=used,
                utilization_percent=util,
                created_at=now,
            )
            self.db.add(hist)

    async def _persist_storage(self, device_id: int, data: dict, now: datetime) -> None:
        from backend.models.snmp import StorageStatistic, LatestStorage
        volumes = data.get("volumes", [])
        for vol in volumes:
            if not isinstance(vol, dict):
                continue
            vol_id = str(vol.get("index") or vol.get("mount_point") or vol.get("filesystem") or "unknown")
            mount = vol.get("filesystem") or vol.get("mount_point") or vol.get("descr") or f"vol-{vol_id}"
            total = vol.get("total_bytes")
            used = vol.get("used_bytes")
            free = vol.get("free_bytes")
            util = vol.get("utilization_percent")
            type_label = vol.get("type_label") or vol.get("type")

            latest = self.db.query(LatestStorage).filter(
                LatestStorage.device_id == device_id,
                LatestStorage.volume_id == vol_id
            ).first()
            if not latest:
                latest = LatestStorage(device_id=device_id, volume_id=vol_id)
                self.db.add(latest)
            latest.mount_name = mount
            latest.total_bytes = total
            latest.used_bytes = used
            latest.free_bytes = free
            latest.utilization_percent = util
            latest.type_label = type_label
            latest.polled_at = now

            if total is not None:
                hist = StorageStatistic(
                    device_id=device_id,
                    mount_name=mount,
                    total_bytes=total,
                    used_bytes=used,
                    utilization_percent=util,
                    created_at=now,
                )
                self.db.add(hist)

    async def _persist_interfaces(self, device_id: int, data: dict, now: datetime) -> None:
        from backend.models.snmp import InterfaceStatistic, LatestInterface
        from backend.models import Interface
        interfaces = data.get("interfaces", [])

        # Get previous counters for rate calculation
        prev_counters = {}
        for iface in interfaces:
            if_index = iface.get("ifIndex")
            if if_index:
                prev = self.db.query(InterfaceStatistic).filter(
                    InterfaceStatistic.device_id == device_id,
                    InterfaceStatistic.interface_id == if_index,
                ).order_by(InterfaceStatistic.id.desc()).first()
                if prev:
                    prev_counters[if_index] = {
                        "rx_octets": prev.rx_octets,
                        "tx_octets": prev.tx_octets,
                        "rx_packets": prev.rx_packets,
                        "tx_packets": prev.tx_packets,
                        "errors": prev.error_rate,
                        "created_at": prev.created_at,
                    }

        for iface in interfaces:
            if not isinstance(iface, dict):
                continue
            if_index = iface.get("ifIndex")
            if not if_index:
                continue

            iface_name = iface.get("name") or iface.get("description") or f"IF-{if_index}"

            # Find or create legacy interface row; latest/history tables FK to interfaces.id.
            iface_rec = self.db.query(Interface).filter(
                Interface.device_id == device_id,
                Interface.interface_name == str(iface_name),
            ).first()
            if not iface_rec:
                iface_rec = Interface(device_id=device_id, interface_name=str(iface_name)[:120])
                self.db.add(iface_rec)
                self.db.flush()

            in_oct = iface.get("in_octets") or iface.get("hc_in_octets")
            out_oct = iface.get("out_octets") or iface.get("hc_out_octets")
            in_pkt = iface.get("in_ucast_pkts", 0) + iface.get("in_multicast_pkts", 0) + iface.get("in_broadcast_pkts", 0)
            out_pkt = iface.get("out_ucast_pkts", 0) + iface.get("out_multicast_pkts", 0) + iface.get("out_broadcast_pkts", 0)
            errors = (iface.get("in_errors", 0) or 0) + (iface.get("out_errors", 0) or 0)
            discards = (iface.get("in_discards", 0) or 0) + (iface.get("out_discards", 0) or 0)
            speed = iface.get("speed_bps")
            util = iface.get("utilization_percent")
            iface_rec.status = str(iface.get("oper_status") or "unknown").lower()[:30]
            iface_rec.speed = str(speed or iface.get("speed_label") or "unknown")[:50]
            iface_rec.traffic_in = float(in_oct or 0)
            iface_rec.traffic_out = float(out_oct or 0)
            iface_rec.packet_errors = int(errors or 0)
            iface_rec.last_updated = now

            prev = self.db.query(InterfaceStatistic).filter(
                InterfaceStatistic.device_id == device_id,
                InterfaceStatistic.interface_id == iface_rec.id,
            ).order_by(InterfaceStatistic.id.desc()).first()
            if prev:
                prev_counters[if_index] = {
                    "rx_octets": prev.rx_octets,
                    "tx_octets": prev.tx_octets,
                    "rx_packets": 0,
                    "tx_packets": 0,
                    "errors": prev.error_rate,
                    "created_at": prev.created_at,
                }

            # Calculate rates if we have previous data
            rx_mbps = tx_mbps = packet_rate = error_rate = None
            if if_index in prev_counters:
                prev = prev_counters[if_index]
                elapsed = (now - prev["created_at"]).total_seconds() if prev["created_at"] else 60
                if elapsed > 0:
                    from backend.snmp.statistics_engine import counter_delta
                    rx_delta = counter_delta(float(in_oct or 0), float(prev["rx_octets"] or 0))
                    tx_delta = counter_delta(float(out_oct or 0), float(prev["tx_octets"] or 0))
                    rx_mbps = round(rx_delta * 8 / elapsed / 1_000_000, 3)
                    tx_mbps = round(tx_delta * 8 / elapsed / 1_000_000, 3)
                    pkt_delta = (in_pkt + out_pkt) - (prev.get("rx_packets", 0) + prev.get("tx_packets", 0))
                    packet_rate = round(pkt_delta / elapsed, 2)
                    err_delta = errors - (prev.get("errors", 0) or 0)
                    error_rate = round(err_delta / max(pkt_delta, 1) * 100, 4)

            # Latest
            latest = self.db.query(LatestInterface).filter(
                LatestInterface.device_id == device_id,
                LatestInterface.interface_id == iface_rec.id,
            ).first()
            if not latest:
                latest = LatestInterface(device_id=device_id, interface_id=iface_rec.id)
                self.db.add(latest)
            latest.if_index = if_index
            latest.name = str(iface_name)
            latest.oper_status = (iface.get("oper_status") or "UNKNOWN").upper()
            latest.admin_status = (iface.get("admin_status") or "UNKNOWN").upper()
            latest.speed_bps = speed
            latest.rx_mbps = rx_mbps
            latest.tx_mbps = tx_mbps
            latest.rx_octets = in_oct
            latest.tx_octets = out_oct
            latest.rx_packets = in_pkt
            latest.tx_packets = out_pkt
            latest.errors = errors
            latest.discards = discards
            latest.utilization_percent = util
            latest.polled_at = now

            # History
            hist = InterfaceStatistic(
                device_id=device_id,
                interface_id=iface_rec.id,
                rx_mbps=rx_mbps,
                tx_mbps=tx_mbps,
                utilization_percent=util,
                error_rate=error_rate,
                packet_rate=packet_rate,
                rx_octets=in_oct,
                tx_octets=out_oct,
                created_at=now,
            )
            self.db.add(hist)

    async def _persist_environment(self, device_id: int, data: dict, now: datetime) -> None:
        from backend.models.snmp import EnvironmentStatistic, LatestEnvironment
        sensors = []
        for group_key in ("temperatures", "fans", "power_supplies", "voltages", "currents", "other_sensors"):
            group = data.get(group_key) or []
            if isinstance(group, list):
                for s in group:
                    if isinstance(s, dict):
                        sensors.append(s)

        for idx, sensor in enumerate(sensors):
            sensor_id = sensor.get("name") or f"sensor-{idx}"
            sensor_type = sensor.get("type") or "other"
            if sensor_type not in ("temperature", "fan", "voltage", "power", "humidity", "current", "other"):
                sensor_type = "other"
            value = sensor.get("value")
            unit = sensor.get("unit")
            status_raw = str(sensor.get("status") or "unknown").lower()
            if status_raw in ("normal", "ok", "online"):
                status = "ok"
            elif status_raw in ("warning", "warn"):
                status = "warning"
            elif status_raw in ("critical", "alarm", "failed", "down"):
                status = "critical"
            else:
                status = "unknown"

            latest = self.db.query(LatestEnvironment).filter(
                LatestEnvironment.device_id == device_id,
                LatestEnvironment.sensor_id == sensor_id,
            ).first()
            if not latest:
                latest = LatestEnvironment(device_id=device_id, sensor_id=sensor_id)
                self.db.add(latest)
            latest.sensor_name = sensor.get("name") or f"Sensor-{idx}"
            latest.sensor_type = sensor_type
            latest.value = float(value) if value is not None else None
            latest.unit = unit
            latest.status = status
            latest.polled_at = now

            hist = EnvironmentStatistic(
                device_id=device_id,
                sensor_name=latest.sensor_name,
                temperature_celsius=float(value) if value is not None and sensor_type == "temperature" else None,
                power_watts=float(value) if value is not None and sensor_type == "power" else None,
                created_at=now,
            )
            self.db.add(hist)

    async def _persist_history(self, device_id: int, module: str, data: dict, supported: bool, now: datetime) -> None:
        """Persist to polling_history for audit trail."""
        status = PollStatus.SUCCESS.value if supported else PollStatus.NOT_SUPPORTED.value
        self.db.add(PollingHistory(
            device_id=device_id,
            collector=module,
            status=status,
            duration_ms=0,  # Will be updated by caller
            error=None if supported else "Module not supported",
            created_at=now,
        ))


class PollingScheduler:
    """Centralized polling scheduler with APScheduler."""

    def __init__(self, worker_count: int = 4):
        self.scheduler = AsyncIOScheduler()
        self.worker_count = worker_count
        self._worker_semaphore: asyncio.Semaphore | None = None
        self._running = False

    async def start(self) -> None:
        """Start the scheduler and initialize jobs from DB."""
        if self._running:
            return

        self._worker_semaphore = asyncio.Semaphore(self.worker_count)
        self.scheduler.start()
        await self._load_jobs_from_db()
        self._running = True
        logger.info("Polling scheduler started with %d workers", self.worker_count)

    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return
        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Polling scheduler stopped")

    async def _load_jobs_from_db(self) -> None:
        """Load all enabled monitoring configs from DB and schedule them."""
        db = SessionLocal()
        try:
            configs = db.query(MonitoringConfig).filter(
                MonitoringConfig.enabled.is_(True),
                MonitoringConfig.status == MonitoringStatus.RUNNING.value,
            ).all()

            for config in configs:
                await self._schedule_config(config, db)
            logger.info("Loaded %d polling jobs from database", len(configs))
        finally:
            db.close()

    async def _schedule_config(self, config: MonitoringConfig, db: Session | None = None) -> None:
        """Schedule a single monitoring config."""
        job_id = f"{config.device_id}:{config.module_name}"

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        # Check capability
        cap = db.query(DeviceCapabilities).filter(
            DeviceCapabilities.device_id == config.device_id
        ).first() if db else None

        if cap:
            cap_map = cap.to_map()
            if not cap_map.get(config.module_name, False):
                logger.info("Module %s not supported on device %d, skipping", config.module_name, config.device_id)
                config.status = MonitoringStatus.NOT_SUPPORTED.value
                if db:
                    db.commit()
                return

        # Calculate next poll time
        next_poll = config.next_poll_at or datetime.utcnow()
        if next_poll < datetime.utcnow():
            next_poll = datetime.utcnow() + timedelta(seconds=5)

        config.next_poll_at = next_poll
        if db:
            db.commit()

        # Schedule the job
        self.scheduler.add_job(
            self._execute_poll_job,
            DateTrigger(run_date=next_poll),
            args=[config.device_id, config.module_name, config.interval_seconds, config.id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.debug("Scheduled job %s for %s", job_id, next_poll)

    async def _execute_poll_job(self, device_id: int, module_name: str, interval_seconds: int, config_id: int) -> None:
        """Execute a poll job and reschedule."""
        async with self._worker_semaphore:
            job = PollJob(
                device_id=device_id,
                module_name=module_name,
                collector_name=MODULE_COLLECTOR_MAP.get(module_name, module_name),
                interval_seconds=interval_seconds,
                config_id=config_id,
            )

            db = SessionLocal()
            try:
                poller = SNMPPoller(db)
                started = time.perf_counter()
                result = await poller.poll(job)
                duration_ms = round((time.perf_counter() - started) * 1000, 1)

                # Update polling history with actual duration
                hist = db.query(PollingHistory).filter(
                    PollingHistory.device_id == device_id,
                    PollingHistory.collector == module_name,
                ).order_by(PollingHistory.id.desc()).first()
                if hist:
                    hist.duration_ms = duration_ms

                # Update config
                config = db.query(MonitoringConfig).filter(MonitoringConfig.id == config_id).first()
                if config:
                    config.last_poll_at = datetime.utcnow()
                    if result.get("success"):
                        config.status = MonitoringStatus.RUNNING.value
                        config.error_message = None
                    else:
                        if result.get("not_supported"):
                            config.status = MonitoringStatus.NOT_SUPPORTED.value
                        else:
                            config.status = MonitoringStatus.ERROR.value
                            config.error_message = result.get("error", "Unknown error")

                    # Schedule next poll
                    config.next_poll_at = datetime.utcnow() + timedelta(seconds=config.interval_seconds)
                    db.commit()

                    # Reschedule if still running
                    if config.enabled and config.status == MonitoringStatus.RUNNING.value:
                        await self._schedule_config(config, db)

            except Exception as exc:
                logger.error("Poll job %s failed: %s", job.job_id, exc)
                config = db.query(MonitoringConfig).filter(MonitoringConfig.id == config_id).first()
                if config:
                    config.status = MonitoringStatus.ERROR.value
                    config.error_message = str(exc)
                    config.next_poll_at = datetime.utcnow() + timedelta(seconds=config.interval_seconds)
                    db.commit()
            finally:
                db.close()

    async def add_job(self, device_id: int, module_name: str, interval_seconds: int) -> MonitoringConfig:
        """Add or update a monitoring config and schedule it."""
        db = SessionLocal()
        try:
            config = db.query(MonitoringConfig).filter(
                MonitoringConfig.device_id == device_id,
                MonitoringConfig.module_name == module_name,
            ).first()

            if not config:
                config = MonitoringConfig(
                    device_id=device_id,
                    module_name=module_name,
                    enabled=True,
                    interval_seconds=interval_seconds,
                    status=MonitoringStatus.RUNNING.value,
                    last_started_at=datetime.utcnow(),
                )
                db.add(config)
            else:
                config.enabled = True
                config.interval_seconds = interval_seconds
                config.status = MonitoringStatus.RUNNING.value
                config.last_started_at = datetime.utcnow()
                config.error_message = None

            db.commit()
            await self._schedule_config(config, db)
            return config
        finally:
            db.close()

    async def stop_job(self, device_id: int, module_name: str) -> bool:
        """Stop a monitoring job."""
        job_id = f"{device_id}:{module_name}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        db = SessionLocal()
        try:
            config = db.query(MonitoringConfig).filter(
                MonitoringConfig.device_id == device_id,
                MonitoringConfig.module_name == module_name,
            ).first()
            if config:
                config.enabled = False
                config.status = MonitoringStatus.STOPPED.value
                config.last_stopped_at = datetime.utcnow()
                config.next_poll_at = None
                db.commit()
                return True
            return False
        finally:
            db.close()

    async def update_job_interval(self, device_id: int, module_name: str, interval_seconds: int) -> bool:
        """Update polling interval for a running job."""
        if interval_seconds not in ALLOWED_INTERVALS:
            return False

        db = SessionLocal()
        try:
            config = db.query(MonitoringConfig).filter(
                MonitoringConfig.device_id == device_id,
                MonitoringConfig.module_name == module_name,
            ).first()
            if not config:
                return False

            config.interval_seconds = interval_seconds
            db.commit()

            # If running, reschedule with new interval
            if config.enabled and config.status == MonitoringStatus.RUNNING.value:
                await self._schedule_config(config, db)
            return True
        finally:
            db.close()

    async def get_job_status(self, device_id: int, module_name: str) -> dict[str, Any] | None:
        """Get status of a monitoring job."""
        db = SessionLocal()
        try:
            config = db.query(MonitoringConfig).filter(
                MonitoringConfig.device_id == device_id,
                MonitoringConfig.module_name == module_name,
            ).first()
            if not config:
                return None

            job_id = f"{device_id}:{module_name}"
            scheduled = self.scheduler.get_job(job_id) is not None

            return {
                "device_id": device_id,
                "module_name": module_name,
                "enabled": config.enabled,
                "interval_seconds": config.interval_seconds,
                "status": config.status,
                "last_started_at": config.last_started_at.isoformat() if config.last_started_at else None,
                "last_stopped_at": config.last_stopped_at.isoformat() if config.last_stopped_at else None,
                "last_poll_at": config.last_poll_at.isoformat() if config.last_poll_at else None,
                "next_poll_at": config.next_poll_at.isoformat() if config.next_poll_at else None,
                "error_message": config.error_message,
                "scheduled": scheduled,
            }
        finally:
            db.close()

    async def get_device_jobs(self, device_id: int) -> list[dict[str, Any]]:
        """Get all monitoring jobs for a device."""
        db = SessionLocal()
        try:
            configs = db.query(MonitoringConfig).filter(
                MonitoringConfig.device_id == device_id
            ).all()
            return [
                {
                    "device_id": c.device_id,
                    "module_name": c.module_name,
                    "enabled": c.enabled,
                    "interval_seconds": c.interval_seconds,
                    "status": c.status,
                    "last_started_at": c.last_started_at.isoformat() if c.last_started_at else None,
                    "last_stopped_at": c.last_stopped_at.isoformat() if c.last_stopped_at else None,
                    "last_poll_at": c.last_poll_at.isoformat() if c.last_poll_at else None,
                    "next_poll_at": c.next_poll_at.isoformat() if c.next_poll_at else None,
                    "error_message": c.error_message,
                    "scheduled": self.scheduler.get_job(f"{c.device_id}:{c.module_name}") is not None,
                }
                for c in configs
            ]
        finally:
            db.close()


# Global scheduler instance
_scheduler: PollingScheduler | None = None


async def get_polling_scheduler() -> PollingScheduler:
    """Get or create the global polling scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = PollingScheduler(worker_count=4)
        await _scheduler.start()
    return _scheduler


async def shutdown_polling_scheduler() -> None:
    """Shutdown the global polling scheduler."""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
