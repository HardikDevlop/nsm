import asyncio, re
from datetime import datetime
from sqlalchemy.orm import Session
from backend.models import Alert, Device, SyslogRecord, SyslogCorrelationRule
PRI = re.compile(r'^<(?P<pri>\d{1,3})>(?P<body>.*)$')
def parse_syslog(raw: str, source_ip: str | None = None) -> dict:
    value = raw.strip(); match = PRI.match(value); pri = int(match.group('pri')) if match else 13; body = match.group('body').strip() if match else value
    facility, severity = pri // 8, pri % 8; hostname = None; message = body; timestamp = datetime.utcnow()
    parts = body.split(None, 4)
    if len(parts) >= 4 and re.match(r'^[A-Z][a-z]{2}$', parts[0]):
        try: timestamp = datetime.strptime(' '.join(parts[:3]), '%b %d %H:%M:%S').replace(year=datetime.utcnow().year)
        except ValueError: pass
        hostname, message = parts[3], parts[4] if len(parts) > 4 else ''
    elif len(parts) >= 2: hostname, message = parts[0], ' '.join(parts[1:])
    return {'source_ip': source_ip, 'facility': facility, 'severity': severity, 'hostname': hostname, 'event_timestamp': timestamp, 'message': message, 'raw_message': raw, 'received_at': datetime.utcnow()}
class SyslogIngestionService:
    def __init__(self, session_factory, queue_size=10000): self.session_factory=session_factory; self.queue=asyncio.Queue(maxsize=queue_size); self.task=None; self.servers=[]
    async def start(self): self.task=asyncio.create_task(self._worker())
    async def stop(self):
        for server in self.servers: server.close()
        if self.task: self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
    def submit(self, raw, source_ip=None): self.queue.put_nowait((raw, source_ip))
    async def start_receivers(self, host='0.0.0.0', udp_port=5514, tcp_port=6514):
        loop=asyncio.get_running_loop(); transport,_=await loop.create_datagram_endpoint(lambda: _UDP(self), local_addr=(host,udp_port)); self.servers.append(transport); tcp=await asyncio.start_server(lambda r,w:self._tcp(r,w),host,tcp_port); self.servers.append(tcp)
    async def _tcp(self, reader, writer):
        try:
            while data:=await reader.readline(): self.submit(data.decode('utf-8','replace'), writer.get_extra_info('peername')[0])
        finally: writer.close(); await writer.wait_closed()
    async def _worker(self):
        while True:
            raw, source = await self.queue.get()
            try:
                with self.session_factory() as db:
                    item=parse_syslog(raw, source); device=db.query(Device).filter(Device.ip_address == source, Device.deleted_at.is_(None)).first() if source else None; item['device_id']=device.id if device else None; record=SyslogRecord(**item); db.add(record); db.flush(); correlate_record(db, record); db.commit()
            finally: self.queue.task_done()
class _UDP(asyncio.DatagramProtocol):
    def __init__(self, service): self.service=service
    def datagram_received(self, data, address):
        try: self.service.submit(data.decode('utf-8','replace'), address[0])
        except asyncio.QueueFull: pass
def correlate_record(db: Session, record: SyslogRecord):
    from datetime import timedelta
    for rule in db.query(SyslogCorrelationRule).filter_by(enabled=True).all():
        if rule.min_severity is not None and (record.severity is None or record.severity > rule.min_severity): continue
        if not re.search(rule.pattern, record.message, re.IGNORECASE): continue
        recent=db.query(Alert).filter(Alert.device_id==record.device_id,Alert.title==f"Syslog: {rule.name}",Alert.created_at>=datetime.utcnow()-timedelta(seconds=rule.cooldown_seconds)).first()
        if recent: continue
        alert=Alert(device_id=record.device_id,severity=rule.alert_severity,title=f"Syslog: {rule.name}",description=record.message,created_at=datetime.utcnow());db.add(alert);db.flush();record.alert_id=alert.id
        try:
            from backend.incidents.service import process_alert_for_incident
            process_alert_for_incident(db, alert.id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Incident processing failed for syslog alert %s", alert.id)
