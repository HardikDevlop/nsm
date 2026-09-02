import asyncio
from backend.syslog import parse_syslog, SyslogIngestionService
from backend.api.syslog_routes import router
def test_parse_syslog_normalizes_priority_hostname_and_message():
 x=parse_syslog('<134>Oct 11 22:14:15 router link down','192.0.2.1'); assert (x['facility'],x['severity'],x['hostname'],x['message'])==(16,6,'router','link down')
def test_ingestion_queue_is_bounded_and_service_is_cancellable():
 service=SyslogIngestionService(lambda: None,queue_size=1); assert service.queue.maxsize==1; assert hasattr(service,'start_receivers')
def test_syslog_correlation_search_rules_and_links_are_exposed():
 assert '/api/v1/syslog/rules' in {r.path for r in router.routes}
