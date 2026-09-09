from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Alert, Device, SyslogRecord, SyslogCorrelationRule

logger = logging.getLogger(__name__)
PRI = re.compile(r"^<(?P<pri>\d{1,3})>(?P<body>.*)$", re.DOTALL)
RFC5424 = re.compile(r"^(?P<version>\d+)\s+(?P<timestamp>-|\S+)\s+(?P<hostname>-|\S+)\s+(?P<application>-|\S+)\s+(?P<procid>-|\S+)\s+(?P<msgid>-|\S+)\s+(?P<structured>(?:\[[^\]]*\])+|-)(?:\s(?P<message>.*))?$", re.DOTALL)
MONTH = re.compile(r"^[A-Z][a-z]{2}$")
DEDUPE_WINDOW = timedelta(seconds=5)


def _timestamp(value: str) -> datetime | None:
    if value == "-":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def parse_syslog(raw: str, source_ip: str | None = None) -> dict[str, Any]:
    received_at = datetime.utcnow()
    value = raw.strip()
    match = PRI.match(value)
    pri = int(match.group("pri")) if match else None
    body = match.group("body").strip() if match else value
    facility = pri // 8 if pri is not None else None
    severity = pri % 8 if pri is not None else None
    timestamp = None
    hostname = application = process_id = message_id = structured_data = None
    message = body

    if pri is not None:
        rfc5424 = RFC5424.match(body)
        if rfc5424:
            timestamp = _timestamp(rfc5424.group("timestamp"))
            hostname = None if rfc5424.group("hostname") == "-" else rfc5424.group("hostname")
            application = None if rfc5424.group("application") == "-" else rfc5424.group("application")
            process_id = None if rfc5424.group("procid") == "-" else rfc5424.group("procid")
            message_id = None if rfc5424.group("msgid") == "-" else rfc5424.group("msgid")
            structured_data = None if rfc5424.group("structured") == "-" else rfc5424.group("structured")
            message = rfc5424.group("message") or ""
        else:
            parts = body.split(None, 4)
            if len(parts) >= 4 and MONTH.match(parts[0]):
                try:
                    timestamp = datetime.strptime(" ".join(parts[:3]), "%b %d %H:%M:%S").replace(year=received_at.year)
                except ValueError:
                    timestamp = None
                hostname, message = parts[3], parts[4] if len(parts) > 4 else ""
            elif len(parts) >= 2:
                hostname, message = parts[0], " ".join(parts[1:])

    fingerprint_input = "\x1f".join(str(x or "") for x in (source_ip, timestamp.isoformat() if timestamp else "", facility, severity, application, message))
    return {"source_ip": source_ip, "facility": facility, "severity": severity, "hostname": hostname, "application": application, "process_id": process_id, "message_id": message_id, "structured_data": structured_data, "event_timestamp": timestamp, "message": message, "raw_message": raw, "received_at": received_at, "fingerprint": hashlib.sha256(fingerprint_input.encode()).hexdigest()}


def resolve_device(db: Session, source_ip: str | None, hostname: str | None) -> Device | None:
    if source_ip:
        device = db.query(Device).filter(Device.ip_address == source_ip, Device.deleted_at.is_(None)).first()
        if device:
            return device
    if hostname:
        matches = db.query(Device).filter(Device.hostname == hostname, Device.deleted_at.is_(None)).limit(2).all()
        if len(matches) == 1:
            return matches[0]
    return None


def cleanup_syslog(db: Session, retention_days: int, batch_size: int = 1000) -> int:
    if retention_days <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    deleted = 0
    while True:
        ids = [row.id for row in db.query(SyslogRecord.id).filter(SyslogRecord.received_at < cutoff).order_by(SyslogRecord.id).limit(batch_size).all()]
        if not ids:
            break
        db.query(SyslogRecord).filter(SyslogRecord.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        deleted += len(ids)
    return deleted


class SyslogIngestionService:
    def __init__(self, session_factory, queue_size=10000):
        self.session_factory = session_factory; self.queue = asyncio.Queue(maxsize=queue_size); self.task = None; self.servers = []; self.started = False

    async def start(self, host="0.0.0.0", udp_port=5514, tcp_port=6514, enable_udp=True, enable_tcp=True):
        if self.started:
            return
        self.started = True
        self.task = asyncio.create_task(self._worker(), name="syslog-ingestion")
        try:
            await self.start_receivers(host, udp_port, tcp_port, enable_udp, enable_tcp)
        except Exception:
            self.started = False
            if self.task:
                self.task.cancel()
            logger.exception("syslog_receiver_start_failed host=%s udp=%s tcp=%s", host, udp_port, tcp_port)
            raise

    async def stop(self):
        for server in self.servers:
            server.close()
            if hasattr(server, "wait_closed"):
                await server.wait_closed()
        self.servers.clear()
        if self.task:
            self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        self.task = None; self.started = False

    def submit(self, raw, source_ip=None):
        self.queue.put_nowait((raw, source_ip))

    async def start_receivers(self, host="0.0.0.0", udp_port=5514, tcp_port=6514, enable_udp=True, enable_tcp=True):
        loop = asyncio.get_running_loop()
        if enable_udp:
            transport, _ = await loop.create_datagram_endpoint(lambda: _UDP(self), local_addr=(host, udp_port)); self.servers.append(transport)
        if enable_tcp:
            self.servers.append(await asyncio.start_server(lambda reader, writer: self._tcp(reader, writer), host, tcp_port))

    async def _tcp(self, reader, writer):
        try:
            while data := await reader.readline():
                try: self.submit(data.decode("utf-8", "replace"), writer.get_extra_info("peername")[0])
                except asyncio.QueueFull: logger.warning("syslog_queue_full transport=tcp")
        finally:
            writer.close(); await writer.wait_closed()

    async def _worker(self):
        while True:
            raw, source = await self.queue.get()
            try:
                with self.session_factory() as db:
                    item = parse_syslog(raw, source)
                    device = resolve_device(db, source, item["hostname"])
                    item["device_id"] = device.id if device else None
                    recent = db.query(SyslogRecord.id).filter(SyslogRecord.fingerprint == item["fingerprint"], SyslogRecord.received_at >= item["received_at"] - DEDUPE_WINDOW).first()
                    if recent:
                        continue
                    record = SyslogRecord(**item); db.add(record); db.flush(); correlate_record(db, record); db.commit()
            except Exception:
                logger.exception("syslog_event_processing_failed")
            finally:
                self.queue.task_done()


class _UDP(asyncio.DatagramProtocol):
    def __init__(self, service): self.service = service
    def datagram_received(self, data, address):
        try: self.service.submit(data.decode("utf-8", "replace"), address[0])
        except asyncio.QueueFull: logger.warning("syslog_queue_full transport=udp")


def correlate_record(db: Session, record: SyslogRecord):
    from datetime import timedelta
    for rule in db.query(SyslogCorrelationRule).filter_by(enabled=True).all():
        if rule.device_id is not None and rule.device_id != record.device_id: continue
        if rule.source_ip is not None and rule.source_ip != record.source_ip: continue
        if rule.hostname is not None and rule.hostname != record.hostname: continue
        if rule.facility is not None and rule.facility != record.facility: continue
        if rule.application is not None and rule.application != record.application: continue
        if rule.min_severity is not None and (record.severity is None or record.severity > rule.min_severity): continue
        try: matched = re.search(rule.pattern, record.message, re.IGNORECASE)
        except re.error: logger.warning("syslog_rule_invalid_regex rule_id=%s", rule.id); continue
        if not matched: continue
        recent = db.query(Alert).filter(Alert.device_id == record.device_id, Alert.title == f"Syslog: {rule.name}", Alert.created_at >= datetime.utcnow() - timedelta(seconds=rule.cooldown_seconds)).first()
        if recent: continue
        alert = Alert(device_id=record.device_id, severity=rule.alert_severity, title=f"Syslog: {rule.name}", description=record.message, created_at=datetime.utcnow()); db.add(alert); db.flush(); record.alert_id = alert.id
        try:
            from backend.incidents.service import process_alert_for_incident
            incident = process_alert_for_incident(db, alert.id)
            record.incident_id = incident.id if incident else None
        except Exception:
            logger.exception("syslog_incident_processing_failed alert_id=%s", alert.id)
