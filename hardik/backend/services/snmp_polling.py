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
import inspect
import logging
import time
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.session import SessionLocal
from backend.models import Device, Interface
from backend.models.snmp import MonitoringConfig, MonitoringStatus, PollingHistory, PollStatus
from backend.models.identity import DeviceCapabilities
from backend.snmp.collector import SNMPService
from backend.snmp.credentials import SNMPCredentials
from backend.utils.crypto import decrypt_secret
from backend.utils.time import as_utc, utc_now, iso_utc

logger = logging.getLogger(__name__)
def now_utc() -> datetime:
    return utc_now()


def _is_restart_restorable_config(enabled: bool, status: str) -> bool:
    return enabled and status in {
        MonitoringStatus.RUNNING.value,
        MonitoringStatus.ERROR.value,
    }


def _build_reschedule_payload(config: Any) -> dict[str, Any]:
    """Carry the original config identity into post-success scheduling."""
    return {
        "id": config.id,
        "device_id": config.device_id,
        "module_name": config.module_name,
        "interval_seconds": config.interval_seconds,
        "config_id": config.id,
        "next_poll_at": config.next_poll_at,
    }


def _interface_elapsed_seconds(now: datetime, previous: datetime | None) -> float:
    """Return elapsed UTC seconds for interface counter-rate calculations.

    InterfaceStatistic is a legacy DateTime column, so PostgreSQL may return
    its semantically-UTC value as naive while application ``now`` is aware.
    The canonical helper makes that legacy semantic explicit before arithmetic.
    """
    if previous is None:
        return 60
    current_utc = as_utc(now, legacy="UTC_NAIVE")
    previous_utc = as_utc(previous, legacy="UTC_NAIVE")
    return (current_utc - previous_utc).total_seconds()

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
    # Interface counters/status are refreshed every 15 seconds so the
    # monitoring screen and PostgreSQL latest/history records stay near-real-time.
    "interfaces": 15,
    "environment": 300,
    "vlan": 600,
    "lldp": 600,
    "cdp": 600,
    "routing": 600,
    # FDB/ARP changes are high-value topology data; keep the DB snapshot fresh
    # without making every frontend request perform a live SNMP walk.
    "arp": 30,
    "mac_table": 30,
    "inventory": 86400,
    "topology": 600,
    "firewall": 60,
    "wireless": 60,
    "health": 60,
}

# Allowed interval options for UI
ALLOWED_INTERVALS = [15, 30, 60, 120, 300, 600]


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
        self._notification_intents = None

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
            port=getattr(cred, "snmp_port", None) or 161,
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

    def _load_latest_interface_statistics(
        self, device_id: int, relevant_interface_ids: set[int]
    ) -> list[Any]:
        """Load at most one deterministic previous sample per interface."""
        from backend.models.snmp import InterfaceStatistic

        if not relevant_interface_ids:
            return []
        ranked_history = self.db.query(
            InterfaceStatistic.id.label("stat_id"),
            func.row_number().over(
                partition_by=InterfaceStatistic.interface_id,
                order_by=(
                    InterfaceStatistic.created_at.desc(),
                    InterfaceStatistic.id.desc(),
                ),
            ).label("row_number"),
        ).filter(
            InterfaceStatistic.device_id == device_id,
            InterfaceStatistic.interface_id.in_(relevant_interface_ids),
        ).subquery()
        return self.db.query(InterfaceStatistic).join(
            ranked_history,
            InterfaceStatistic.id == ranked_history.c.stat_id,
        ).filter(ranked_history.c.row_number == 1).all()

    async def poll(self, job: PollJob, *, commit: bool = True) -> dict[str, Any]:
        """Execute a single poll for the job."""
        from backend.models import Device
        from backend.services.snmp_poll_guard import poll_guard
        device = self.db.query(Device).filter(Device.id == job.device_id).first()
        if not device:
            return {"success": False, "error": "Device not found"}

        ip = device.ip_address
        credentials = self._get_credentials(job.device_id)
        if not credentials:
            return {"success": False, "error": "No SNMP credentials"}

        # Do not hold a DB connection during the network round-trip.  Cached
        # capability flags are hints from discovery, not a connectivity gate:
        # stale/partial discovery previously turned reachable NVRs into
        # ``Module not supported`` before their standard MIBs were queried.
        self.db.close()

        collector_name = MODULE_COLLECTOR_MAP.get(job.module_name, job.module_name)
        started = time.perf_counter()

        guard = poll_guard(job.device_id, job.module_name, blocking=False)
        acquired = guard.__enter__()
        if not acquired:
            guard.__exit__(None, None, None)
            logger.info("Skipping duplicate poll for %s", job.job_id)
            return {"success": True, "skipped": True, "in_progress": True, "duration_ms": 0}

        try:
            # collect_domain is synchronous and performs network I/O. Running it
            # directly here blocks the asyncio scheduler and serializes all jobs.
            # Keep the event loop free so independent devices/modules poll in parallel.
            service = SNMPService(credentials=credentials, device_id=job.device_id)
            result = await asyncio.to_thread(service.collect_domain, ip, collector_name)
            duration_ms = round((time.perf_counter() - started) * 1000, 1)

            supported = result.get("supported", False)
            data = result.get("data", {})

            # Persist latest values and history
            self.db = SessionLocal()
            self._notification_intents = [] if not commit else None
            await self._persist_results(
                job, data, supported, duration_ms, commit=commit
            )

            return {
                "success": True,
                "supported": supported,
                "data": data,
                "duration_ms": duration_ms,
                "_persistence_pending": not commit,
                "_notification_intents": self._notification_intents or [],
            }

        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.error("Poll failed for %s: %s", job.job_id, exc)
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": duration_ms,
            }
        finally:
            guard.__exit__(None, None, None)

    async def _persist_results(
        self,
        job: PollJob,
        data: dict,
        supported: bool,
        duration_ms: float | None = None,
        commit: bool = True,
    ) -> None:
        """Persist poll results to latest-value tables and history.

        Discovery can persist several collector payloads in one transaction;
        normal scheduler polls retain the existing per-poll commit behavior.
        """
        module = job.module_name
        device_id = job.device_id
        now = now_utc()

        try:
            if self.db is None:
                self.db = SessionLocal()
            cap = self.db.query(DeviceCapabilities).filter(
                DeviceCapabilities.device_id == device_id
            ).first()
            if cap:
                detail = dict(cap.capability_detail or {})
                existing = detail.get(module, {}) if isinstance(detail.get(module), dict) else {}
                persisted_data = dict(data or existing.get("data") or {})
                if module == "topology":
                    arp_data = ((detail.get("arp") or {}).get("data") or {})
                    arp_by_mac: dict[str, str] = {}
                    for entry in arp_data.get("entries") or []:
                        raw_mac = entry.get("mac") or entry.get("mac_address")
                        mac = "".join(ch for ch in str(raw_mac or "").lower() if ch in "0123456789abcdef")
                        ip = entry.get("ip_address") or entry.get("ip")
                        if len(mac) == 12 and ip and mac not in arp_by_mac:
                            arp_by_mac[mac] = str(ip)
                    if arp_by_mac and isinstance(persisted_data.get("nodes"), list):
                        nodes = []
                        for node in persisted_data["nodes"]:
                            item = dict(node)
                            raw_mac = item.get("mac_address") or item.get("mac")
                            mac = "".join(ch for ch in str(raw_mac or "").lower() if ch in "0123456789abcdef")
                            if not item.get("ip_address") and len(mac) == 12 and mac in arp_by_mac:
                                item["ip_address"] = arp_by_mac[mac]
                                item["ip"] = arp_by_mac[mac]
                            nodes.append(item)
                        persisted_data["nodes"] = nodes
                if module == "inventory":
                    chassis = persisted_data.get("chassis") or {}
                    ports = persisted_data.get("ports") or []
                    device = self.db.query(Device).filter(Device.id == device_id).first()
                    uptime_seconds = getattr(device, "uptime_seconds", None) if device else None
                    uptime_display = None
                    if uptime_seconds is not None:
                        total = int(uptime_seconds)
                        days, remainder = divmod(total, 86400)
                        hours, remainder = divmod(remainder, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        uptime_display = f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"
                    persisted_data.update({
                        "port_count": len(ports),
                        "loader_date": now.isoformat(),
                        "system_uptime": uptime_display,
                        "loader_version": chassis.get("loader_version") or chassis.get("software_rev"),
                        "firmware_version": chassis.get("firmware_version") or chassis.get("firmware_rev"),
                    })
                detail[module] = {
                    **existing,
                    "collector": module,
                    "supported": supported,
                    "timestamp": now.isoformat(),
                    "data": persisted_data,
                    "missing": existing.get("missing", []),
                    "warnings": existing.get("warnings", []),
                    "reason": None if supported else existing.get("reason") or "Module not supported",
                    "collection_status": "SUCCESS" if supported else "FAILED",
                    "last_good_timestamp": now.isoformat() if supported else existing.get("last_good_timestamp") or existing.get("timestamp"),
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

            self._evaluate_alerts(device_id, module, data)

            # Always persist to history tables
            await self._persist_history(device_id, module, data, supported, now, duration_ms)

            if commit:
                self.db.commit()
        except Exception as exc:
            logger.error("Failed to persist results for %s: %s", job.job_id, exc)
            self.db.rollback()
            raise

    def _evaluate_alerts(self, device_id: int, module: str, data: dict) -> None:
        """Turn supported SNMP health values into deduplicated alerts."""
        from backend.services.alerting import create_threshold_alert, resolve_alert
        from backend.models import Alert
        create_parameters = inspect.signature(create_threshold_alert).parameters.values()
        supports_deferred_notifications = any(
            parameter.name == "notification_intents"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in create_parameters
        )

        def create_alert(*args, **kwargs):
            if supports_deferred_notifications:
                kwargs["notification_intents"] = self._notification_intents
            return create_threshold_alert(*args, **kwargs)

        checks: list[tuple[str, float | None, float, str]] = []
        if module == "cpu":
            checks.append(("High CPU", data.get("overall_percent"), 85, "%"))
        elif module == "memory":
            checks.append(("High Memory", data.get("utilization_percent"), 85, "%"))
        elif module == "storage":
            checks.append(("High Storage", data.get("utilization_percent"), 80, "%"))
        elif module == "interfaces":
            interface_payloads = [
                iface for iface in data.get("interfaces", []) if isinstance(iface, dict)
            ]
            interface_names = {
                str(
                    iface.get("name")
                    or iface.get("interface")
                    or iface.get("interface_name")
                    or iface.get("description")
                    or "unknown"
                )
                for iface in interface_payloads
            }
            interface_rows = self.db.query(Interface).filter(
                Interface.device_id == device_id,
            ).all() if interface_names else []
            interface_by_name = {row.interface_name: row for row in interface_rows}
            active_alerts = self.db.query(Alert).filter(
                Alert.device_id == device_id,
                Alert.title.ilike("Interface Down:%"),
                Alert.status.in_(("open", "acknowledged")),
                Alert.deleted_at.is_(None),
            ).order_by(Alert.created_at.desc()).all()
            alert_by_interface_id = {}
            alert_by_title = {}
            for alert in active_alerts:
                if alert.interface_id is not None:
                    alert_by_interface_id.setdefault(alert.interface_id, alert)
                alert_by_title.setdefault(alert.title, alert)

            for iface in interface_payloads:
                interface_name = str(
                    iface.get("name")
                    or iface.get("interface")
                    or iface.get("interface_name")
                    or iface.get("description")
                    or "unknown"
                )
                interface = interface_by_name.get(interface_name)
                interface_id = interface.id if interface else None
                admin_status = str(iface.get("admin_status", "")).lower()
                oper_status = str(iface.get("oper_status", iface.get("status", ""))).lower()
                # An administratively disabled/unused port is expected to be
                # down. Alert only when the operator enabled the port but SNMP
                # reports its operational link as down.
                admin_up = admin_status in {"up", "1", "true", "enabled", "on"}
                if admin_up and oper_status in {"down", "2", "false"}:
                    title = f"Interface Down: {interface_name}"
                    existing = alert_by_title.get(title)
                    created = create_alert(
                        self.db,
                        device_id,
                        title,
                        "SNMP reports interface is down",
                        "critical",
                        interface_id=interface_id,
                        existing_alert=existing,
                    )
                    if created is not None:
                        alert_by_title[title] = created
                        if interface_id is not None:
                            alert_by_interface_id[interface_id] = created
                elif oper_status in {"up", "1", "true"} and interface_id is not None:
                    from backend.services.alerting import resolve_interface_down_alert
                    title = f"Interface Down: {interface_name}"
                    existing = alert_by_interface_id.get(interface_id) or alert_by_title.get(title)
                    resolved = resolve_interface_down_alert(
                        self.db,
                        device_id,
                        interface_id,
                        interface_name,
                        existing_alert=existing,
                    )
                    if resolved is not None:
                        alert_by_interface_id.pop(interface_id, None)
                        alert_by_title.pop(resolved.title, None)
        elif module == "environment":
            for sensor in data.get("temperatures", []):
                checks.append((f"High Temperature: {sensor.get('name', 'sensor')}", sensor.get("value"), 70, "°C"))
        for name, value, threshold, unit in checks:
            if value is not None and float(value) >= threshold:
                severity = "critical" if float(value) >= threshold + 10 else "warning"
                create_alert(
                    self.db, device_id, name,
                    f"Value {value}{unit} reached threshold {threshold}{unit}", severity,
                )
            elif value is not None:
                active = self.db.query(Alert).filter(
                    Alert.device_id == device_id,
                    Alert.title == name,
                    Alert.status.in_(("open", "acknowledged")),
                    Alert.deleted_at.is_(None),
                ).order_by(Alert.created_at.desc()).first()
                if active:
                    resolve_alert(
                        self.db,
                        active,
                        f"Verified value {value}{unit} is below the recovery threshold {threshold}{unit}.",
                        notification_intents=self._notification_intents,
                    )

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
        latest_rows = self.db.query(LatestStorage).filter(
            LatestStorage.device_id == device_id,
        ).all() if volumes else []
        latest_by_volume_id = {row.volume_id: row for row in latest_rows}
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

            latest = latest_by_volume_id.get(vol_id)
            if not latest:
                latest = LatestStorage(device_id=device_id, volume_id=vol_id)
                self.db.add(latest)
                latest_by_volume_id[vol_id] = latest
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
        valid_interfaces = [
            iface for iface in interfaces
            if isinstance(iface, dict) and iface.get("ifIndex")
        ]
        if not valid_interfaces:
            return

        # Discovery commonly carries dozens of interfaces, so preload related
        # rows instead of issuing SELECTs for every interface.
        names = {
            str(iface.get("name") or iface.get("description") or f"IF-{iface['ifIndex']}")
            for iface in valid_interfaces
        }
        interface_rows = self.db.query(Interface).filter(
            Interface.device_id == device_id,
            Interface.interface_name.in_(names),
        ).all()
        interface_by_name = {row.interface_name: row for row in interface_rows}
        for name in names:
            if name not in interface_by_name:
                row = Interface(device_id=device_id, interface_name=name[:120])
                self.db.add(row)
                interface_by_name[name] = row
        self.db.flush()

        if_indexes = {iface.get("ifIndex") for iface in valid_interfaces}
        interface_ids = {row.id for row in interface_by_name.values()}
        relevant_history_ids = interface_ids | if_indexes
        stat_rows = self._load_latest_interface_statistics(
            device_id, relevant_history_ids
        )
        previous_by_id = {}
        for row in stat_rows:
            previous_by_id[row.interface_id] = {
                "rx_octets": row.rx_octets,
                "tx_octets": row.tx_octets,
                "rx_packets": getattr(row, "rx_packets", 0) or 0,
                "tx_packets": getattr(row, "tx_packets", 0) or 0,
                "errors": row.error_rate,
                "created_at": row.created_at,
            }

        latest_rows = self.db.query(LatestInterface).filter(
            LatestInterface.device_id == device_id,
            LatestInterface.interface_id.in_(interface_ids),
        ).all()
        latest_by_id = {row.interface_id: row for row in latest_rows}

        # Retain the ifIndex fallback for historical rows written before the
        # interface foreign key was consistently used.
        prev_counters = {}

        for iface in valid_interfaces:
            if_index = iface.get("ifIndex")

            iface_name = iface.get("name") or iface.get("description") or f"IF-{if_index}"

            # Latest/history tables reference the legacy interface row.
            iface_rec = interface_by_name[str(iface_name)]

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

            prev = previous_by_id.get(iface_rec.id) or previous_by_id.get(if_index)
            if prev:
                prev_counters[if_index] = {
                    "rx_octets": prev["rx_octets"],
                    "tx_octets": prev["tx_octets"],
                    "rx_packets": prev["rx_packets"],
                    "tx_packets": prev["tx_packets"],
                    "errors": prev["errors"],
                    "created_at": prev["created_at"],
                }

            # Calculate rates if we have previous data
            rx_mbps = tx_mbps = packet_rate = error_rate = None
            if if_index in prev_counters:
                prev = prev_counters[if_index]
                elapsed = _interface_elapsed_seconds(now, prev["created_at"])
                if elapsed > 0:
                    from backend.snmp.statistics_engine import interface_rate_mbps
                    rx_mbps = interface_rate_mbps(
                        in_oct, prev["rx_octets"], elapsed, speed
                    )
                    tx_mbps = interface_rate_mbps(
                        out_oct, prev["tx_octets"], elapsed, speed
                    )
                    pkt_delta = (in_pkt + out_pkt) - (prev.get("rx_packets", 0) + prev.get("tx_packets", 0))
                    packet_rate = round(pkt_delta / elapsed, 2)
                    err_delta = errors - (prev.get("errors", 0) or 0)
                    error_rate = round(err_delta / max(pkt_delta, 1) * 100, 4)

            # Latest
            latest = latest_by_id.get(iface_rec.id)
            if not latest:
                latest = LatestInterface(device_id=device_id, interface_id=iface_rec.id)
                self.db.add(latest)
                latest_by_id[iface_rec.id] = latest
            latest.if_index = if_index
            latest.name = str(iface_name)
            latest.mac_address = iface.get("mac") or iface.get("mac_address")
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

        latest_rows = self.db.query(LatestEnvironment).filter(
            LatestEnvironment.device_id == device_id,
        ).all() if sensors else []
        latest_by_sensor_id = {row.sensor_id: row for row in latest_rows}

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

            latest = latest_by_sensor_id.get(sensor_id)
            if not latest:
                latest = LatestEnvironment(device_id=device_id, sensor_id=sensor_id)
                self.db.add(latest)
                latest_by_sensor_id[sensor_id] = latest
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

    async def _persist_history(
        self,
        device_id: int,
        module: str,
        data: dict,
        supported: bool,
        now: datetime,
        duration_ms: float | None = None,
    ) -> None:
        """Persist to polling_history for audit trail."""
        status = PollStatus.SUCCESS.value if supported else PollStatus.NOT_SUPPORTED.value
        self.db.add(PollingHistory(
            device_id=device_id,
            collector=module,
            status=status,
            duration_ms=duration_ms if duration_ms is not None else 0,
            error=None if supported else "Module not supported",
            created_at=now,
        ))


def _database_worker(method):
    """Run synchronous SQL work in a session-owning worker, not the API loop."""
    @wraps(method)
    async def wrapped(*args, **kwargs):
        return await asyncio.to_thread(lambda: asyncio.run(method(*args, **kwargs)))
    return wrapped


class PollingScheduler:
    """Centralized polling scheduler with APScheduler."""

    def __init__(self, worker_count: int = 4):
        self.scheduler = AsyncIOScheduler()
        self.worker_count = worker_count
        self._worker_semaphore: asyncio.Semaphore | None = None
        self._running = False
        self.last_job_started_at: datetime | None = None
        self.last_job_finished_at: datetime | None = None
        self.last_job_success_at: datetime | None = None
        self.last_job_failure_at: datetime | None = None
        self.recent_failure_count = 0
        self.active_jobs = 0

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

    @_database_worker
    async def _load_jobs_from_db(self) -> None:
        """Restore enabled runnable configs, including retryable errors."""
        db = SessionLocal()
        try:
            # enabled is the durable monitoring intent; runtime status may be
            # stale after a crash/restart. Restore every enabled config.
            configs = db.query(MonitoringConfig).filter(
                MonitoringConfig.enabled.is_(True),
                MonitoringConfig.status != MonitoringStatus.NOT_SUPPORTED.value,
            ).all()

            restored = 0
            for config in configs:
                try:
                    await self._schedule_config(config, db)
                    if self.scheduler.get_job(f"{config.device_id}:{config.module_name}"):
                        restored += 1
                except Exception:
                    logger.exception(
                        "MONITORING_RESTORE_FAILED device_id=%s module=%s",
                        config.device_id, config.module_name,
                    )
            logger.info("MONITORING_RESTORED jobs=%d enabled_configs=%d", restored, len(configs))
        finally:
            db.close()

    async def _schedule_config(self, config: MonitoringConfig, db: Session | None = None) -> None:
        """Schedule a single monitoring config."""
        job_id = f"{config.device_id}:{config.module_name}"

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        # Calculate next poll time
        next_poll = config.next_poll_at or now_utc()
        if next_poll.tzinfo is None:
            next_poll = next_poll.replace(tzinfo=timezone.utc)
        if next_poll < now_utc():
            next_poll = now_utc() + timedelta(seconds=5)

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
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        logger.debug("Scheduled job %s for %s", job_id, next_poll)

    @staticmethod
    def _poll_in_worker(job: PollJob) -> dict[str, Any]:
        """Keep synchronous DB writes and alert delivery off the API event loop.

        Create and close sessions in the worker that owns them, including the
        replacement session opened by poll() after the SNMP round-trip.
        """
        db = SessionLocal()
        poller = SNMPPoller(db)
        try:
            poll_parameters = inspect.signature(poller.poll).parameters.values()
            supports_deferred_commit = any(
                parameter.name == "commit"
                or parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in poll_parameters
            )
            if supports_deferred_commit:
                result = asyncio.run(poller.poll(job, commit=False))
            else:
                # Compatibility for legacy test doubles/custom pollers.
                result = asyncio.run(poller.poll(job))

            persistence_pending = result.pop("_persistence_pending", False)
            if persistence_pending:
                transaction_db = poller.db
            else:
                transaction_db = SessionLocal()
                poller.db = transaction_db

            config = transaction_db.query(MonitoringConfig).filter(
                MonitoringConfig.id == job.config_id
            ).first()
            reschedule = None
            if config:
                config.last_poll_at = now_utc()
                if result.get("success"):
                    config.status = MonitoringStatus.RUNNING.value
                    config.error_message = None
                elif result.get("not_supported"):
                    config.status = MonitoringStatus.NOT_SUPPORTED.value
                else:
                    # A failed poll must not disable enabled monitoring.
                    config.status = (
                        MonitoringStatus.RUNNING.value
                        if config.enabled else MonitoringStatus.ERROR.value
                    )
                    config.error_message = result.get("error", "Unknown error")
                config.next_poll_at = now_utc() + timedelta(seconds=config.interval_seconds)
                if config.enabled and config.status != MonitoringStatus.NOT_SUPPORTED.value:
                    reschedule = _build_reschedule_payload(config)

            transaction_db.commit()
            result["_reschedule"] = reschedule
            intents = result.pop("_notification_intents", [])
            if intents:
                from backend.services.alerting import deliver_notification_intents
                delivery_db = SessionLocal()
                try:
                    deliver_notification_intents(delivery_db, intents)
                    delivery_db.commit()
                except Exception:
                    delivery_db.rollback()
                    logger.exception("Post-commit SNMP notification delivery failed")
                finally:
                    delivery_db.close()
            return result
        except Exception:
            if poller.db is not None:
                poller.db.rollback()
            raise
        finally:
            if poller.db is not db and poller.db is not None:
                poller.db.close()
            db.close()

    async def _execute_poll_job(self, device_id: int, module_name: str, interval_seconds: int, config_id: int) -> None:
        """Execute a poll job and reschedule."""
        self.active_jobs += 1
        self.last_job_started_at = utc_now()
        async with self._worker_semaphore:
            job = PollJob(
                device_id=device_id,
                module_name=module_name,
                collector_name=MODULE_COLLECTOR_MAP.get(module_name, module_name),
                interval_seconds=interval_seconds,
                config_id=config_id,
            )

            try:
                # Retry transient worker failures twice before marking the
                # monitoring config unhealthy. Each retry is deliberately
                # short and bounded so one device cannot occupy a worker.
                result = None
                last_error: Exception | None = None
                for attempt in range(1, 3):
                    try:
                        result = await asyncio.to_thread(self._poll_in_worker, job)
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        if attempt < 2:
                            await asyncio.sleep(0.5)
                if last_error is not None:
                    raise last_error
                reschedule = result.pop("_reschedule", None)
                if reschedule:
                    from types import SimpleNamespace
                    await self._schedule_config(SimpleNamespace(**reschedule))

                if result.get("success") and not result.get("skipped"):
                    self.last_job_success_at = utc_now()
                    if result.get("supported"):
                        db = SessionLocal()
                        try:
                            from backend.models import Alert
                            from backend.services.alerting import resolve_alert
                            active = db.query(Alert).filter(
                                Alert.device_id == device_id,
                                Alert.title == f"SNMP Unavailable: {module_name}",
                                Alert.status.in_(("open", "acknowledged")),
                                Alert.deleted_at.is_(None),
                            ).order_by(Alert.created_at.desc()).first()
                            if active:
                                resolve_alert(db, active, f"SNMP {module_name} poll succeeded after retry and returned verified data.")
                                db.commit()
                        finally:
                            db.close()

            except Exception as exc:
                self.last_job_failure_at = utc_now()
                self.recent_failure_count += 1
                logger.error("Poll job %s failed: %s", job.job_id, exc)
                db = SessionLocal()
                # Persist scheduler-level failures too; failures raised
                # before the poller can write its normal attempt record must
                # remain visible in polling history after a restart.
                db.add(PollingHistory(
                    device_id=device_id,
                    collector=job.collector_name,
                    status=PollStatus.ERROR.value,
                    duration_ms=None,
                    error=f"worker failure after retry: {exc}",
                    created_at=utc_now(),
                ))
                from backend.models import Alert
                from backend.services.alerting import create_threshold_alert
                create_threshold_alert(
                    db, device_id, f"SNMP Unavailable: {module_name}",
                    f"SNMP {module_name} polling failed after retry: {exc}", "critical",
                )
                config = db.query(MonitoringConfig).filter(MonitoringConfig.id == config_id).first()
                if config:
                    # Worker/transport failure is transient; preserve active
                    # monitoring intent and leave the retry job registered.
                    config.status = (
                        MonitoringStatus.RUNNING.value
                        if config.enabled else MonitoringStatus.ERROR.value
                    )
                    config.error_message = str(exc)
                    config.next_poll_at = now_utc() + timedelta(seconds=config.interval_seconds)
                    db.commit()
                    if config.enabled:
                        await self._schedule_config(config)
                db.close()
            finally:
                self.last_job_finished_at = utc_now()
                self.active_jobs = max(0, self.active_jobs - 1)

    @_database_worker
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
                    last_started_at=now_utc(),
                )
                db.add(config)
            else:
                config.enabled = True
                config.interval_seconds = interval_seconds
                config.status = MonitoringStatus.RUNNING.value
                config.last_started_at = now_utc()
                config.error_message = None

            db.commit()
            await self._schedule_config(config, db)
            return config
        finally:
            db.close()

    @_database_worker
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
                config.last_stopped_at = now_utc()
                config.next_poll_at = None
                db.commit()
                return True
            return False
        finally:
            db.close()

    @_database_worker
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

    @_database_worker
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
                "active_jobs": self.active_jobs,
            }
        finally:
            db.close()

    @_database_worker
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
_scheduler_lifecycle_lock = asyncio.Lock()


async def get_polling_scheduler() -> PollingScheduler:
    """Get or create the global polling scheduler."""
    global _scheduler
    async with _scheduler_lifecycle_lock:
        if _scheduler is None:
            scheduler = PollingScheduler(worker_count=8)
            await scheduler.start()
            _scheduler = scheduler
        return _scheduler


async def shutdown_polling_scheduler() -> None:
    """Shutdown the global polling scheduler."""
    global _scheduler
    async with _scheduler_lifecycle_lock:
        if _scheduler:
            scheduler = _scheduler
            await scheduler.stop()
            _scheduler = None
