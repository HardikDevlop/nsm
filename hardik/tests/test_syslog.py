import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.syslog_routes import RulePayload, router
from backend.database.session import Base
from backend.models import Device, SyslogRecord
from backend.syslog import SyslogIngestionService, parse_syslog, resolve_device
def test_parse_syslog_normalizes_priority_hostname_and_message():
 x=parse_syslog('<134>Oct 11 22:14:15 router link down','192.0.2.1'); assert (x['facility'],x['severity'],x['hostname'],x['message'])==(16,6,'router','link down')
def test_ingestion_queue_is_bounded_and_service_is_cancellable():
 service=SyslogIngestionService(lambda: None,queue_size=1); assert service.queue.maxsize==1; assert hasattr(service,'start_receivers')


def test_receiver_enable_flags_and_clean_shutdown(monkeypatch):
    async def exercise():
        service = SyslogIngestionService(lambda: None)
        await service.start(enable_udp=False, enable_tcp=False)
        assert service.started and service.servers == []
        await service.stop()
        class DummyServer:
            def close(self): pass
        async def fake_receivers(*args, **kwargs): service.servers = [DummyServer(), DummyServer()]
        monkeypatch.setattr(service, "start_receivers", fake_receivers)
        await service.start(host="127.0.0.1", udp_port=0, tcp_port=0)
        assert len(service.servers) == 2
        await service.stop()
        assert not service.started and service.servers == []
    asyncio.run(exercise())
def test_syslog_correlation_search_rules_and_links_are_exposed():
 assert '/api/v1/syslog/rules' in {r.path for r in router.routes}


def test_parse_rfc5424_and_missing_timestamp_are_preserved_as_null():
    parsed = parse_syslog('<165>1 2026-09-02T12:34:56.123Z edge01 agnigate-agent 42 ID47 [meta@32473 iut="3" eventSource="Application"] link down', '192.0.2.10')
    assert (parsed['facility'], parsed['severity'], parsed['hostname'], parsed['application'], parsed['process_id'], parsed['message_id']) == (20, 5, 'edge01', 'agnigate-agent', '42', 'ID47')
    assert parsed['structured_data'].startswith('[meta@32473') and parsed['event_timestamp'] == datetime(2026, 9, 2, 12, 34, 56, 123000)
    assert parse_syslog('<165>1 - edge01 app - - - event')['event_timestamp'] is None


def test_device_correlation_requires_exact_ip_or_unique_hostname():
    engine = create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine); db = sessionmaker(bind=engine)()
    db.add_all([Device(id=1, hostname='edge01', ip_address='192.0.2.10'), Device(id=2, hostname='shared', ip_address='192.0.2.11'), Device(id=3, hostname='shared', ip_address='192.0.2.12')]); db.commit()
    assert resolve_device(db, '192.0.2.10', 'unknown').id == 1
    assert resolve_device(db, None, 'edge01').id == 1
    assert resolve_device(db, None, 'shared') is None
    assert resolve_device(db, None, 'unknown') is None


def test_dedupe_fingerprint_is_stable_but_time_window_allows_repeated_events():
    first = parse_syslog('<134>Oct 11 22:14:15 router link down', '192.0.2.1')
    second = parse_syslog('<134>Oct 11 22:14:15 router link down', '192.0.2.1')
    assert first['fingerprint'] == second['fingerprint']
    engine = create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine); db = sessionmaker(bind=engine)()
    db.add(SyslogRecord(**first)); db.add(SyslogRecord(**{**second, 'received_at': first['received_at'] + timedelta(seconds=6)})); db.commit()
    assert db.query(SyslogRecord).count() == 2


def test_syslog_rules_validate_regex_and_expose_full_filter_and_rule_api():
    with pytest.raises(ValueError): RulePayload(name='bad', pattern='[')
    paths = {r.path for r in router.routes}
    assert '/api/v1/syslog/records' in paths and '/api/v1/syslog/rules/{rule_id}' in paths and '/api/v1/syslog/retention/cleanup' in paths
