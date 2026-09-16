from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.discovery_routes import router as discovery_router
from backend.api.legacy_routes import router as legacy_router
from backend.api.routes import router
from backend.api.snmp_device_routes import router as snmp_device_router
from backend.api.manual_topology_routes import router as manual_topology_router
from backend.api.overview_routes import router as overview_router
from backend.api.monitoring_data_routes import router as monitoring_data_router
from backend.api.flow_routes import router as flow_router
from backend.api.apm_routes import router as apm_router
from backend.api.cmdb_routes import router as cmdb_router
from backend.api.rca_routes import router as rca_router
from backend.api.incident_routes import router as incident_router
from backend.api.problem_routes import router as problem_router
from backend.api.change_routes import router as change_router
from backend.api.knowledge_routes import router as knowledge_router
from backend.api.config_backup_routes import router as config_backup_router
from backend.api.config_compliance_routes import router as config_compliance_router
from backend.api.availability_routes import router as availability_router
from backend.api.virtualization_routes import router as virtualization_router
from backend.api.qos_routes import router as qos_router
from backend.api.bgp_routes import router as bgp_router
from backend.api.syslog_routes import router as syslog_router
from backend.flow.receiver import FlowReceiver
from backend.flow.service import FlowIngestService
from backend.syslog import SyslogIngestionService
from backend.linux_monitoring.api import router as linux_monitoring_router
import backend.linux_monitoring.models  # noqa: F401 (register Linux monitoring tables)
from backend.linux_monitoring.models import LINUX_MONITORING_TABLES
from backend.config.settings import get_settings
from backend.database.migrations import run_migrations
from backend.database.session import Base, SessionLocal, engine
from backend.observability import install_db_timing, request_timing_middleware
from backend.seed import seed_rbac, seed_ouis_and_products
from backend.services.snmp_polling import get_polling_scheduler, shutdown_polling_scheduler
from backend.snmp.client import shutdown_snmp_workers
from backend.services.realtime_monitor import get_engine
from backend.services.ha_scheduler import SchedulerLease
from backend.cmdb.service import reconcile_cmdb
from backend.linux_monitoring.scheduler import LinuxMonitoringScheduler
from logging_config import configure_logging

import backend.models  # noqa: F401  (register all tables on Base.metadata)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Linux tables are created by their idempotent module migrations below.
    # Keeping them out of the global create_all avoids PostgreSQL attempting
    # to recreate existing Linux indexes during every application startup.
    linux_table_names = {table.name for table in LINUX_MONITORING_TABLES}
    existing_tables = [table for table in Base.metadata.tables.values() if table.name not in linux_table_names]
    Base.metadata.create_all(bind=engine, tables=existing_tables)
    run_migrations(engine)
    with SessionLocal() as db:
        seed_rbac(db)
        seed_ouis_and_products(db)
        try:
            # Reconcile persisted NMS state only; CMDB never starts network polling.
            reconcile_cmdb(db)
        except Exception:
            logger.exception("cmdb_startup_reconciliation_failed")
    flow_ingest = None
    flow_receiver = None
    if settings.flow_enabled:
        flow_ingest = FlowIngestService(SessionLocal)
        await flow_ingest.start()
        flow_receiver = FlowReceiver(
            flow_ingest,
            bind_host=settings.flow_bind_host,
            ipfix_port=settings.flow_ipfix_port,
            sflow_port=settings.flow_sflow_port,
        )
        await flow_receiver.start()
    app.state.flow_ingest = flow_ingest
    app.state.flow_receiver = flow_receiver
    syslog_service = None
    if settings.syslog_enabled:
        syslog_service = SyslogIngestionService(SessionLocal)
        try:
            await syslog_service.start(settings.syslog_bind_host, settings.syslog_udp_port, settings.syslog_tcp_port, settings.syslog_enable_udp, settings.syslog_enable_tcp)
        except Exception:
            logger.exception("syslog_receiver_startup_failed")
            syslog_service = None
    app.state.syslog = syslog_service

    # Start centralized SNMP polling scheduler
    app.state.scheduler_lease = SchedulerLease()
    app.state.scheduler_lease_owned = app.state.scheduler_lease.acquire()
    scheduler = await get_polling_scheduler() if app.state.scheduler_lease_owned else None
    app.state.snmp_polling = scheduler
    lease_task = asyncio.create_task(_renew_scheduler_lease(app.state.scheduler_lease)) if scheduler is not None else None
    linux_scheduler = LinuxMonitoringScheduler()
    app.state.linux_monitoring_scheduler = linux_scheduler
    await linux_scheduler.restore_enabled_servers()
    # Restore the singleton ICMP registry from persisted device intent. The
    # engine's start_all() is idempotent and prevents duplicate loops/devices.
    await asyncio.to_thread(get_engine().restore_enabled_devices)
    yield
    if flow_receiver is not None:
        await flow_receiver.stop()
    if flow_ingest is not None:
        await flow_ingest.stop()
    if syslog_service is not None:
        await syslog_service.stop()
    await linux_scheduler.shutdown()
    if scheduler is not None:
        await shutdown_polling_scheduler()
    if lease_task is not None:
        lease_task.cancel()
        await asyncio.gather(lease_task, return_exceptions=True)
    app.state.scheduler_lease.release()
    await asyncio.to_thread(shutdown_snmp_workers)
    await asyncio.to_thread(get_engine().shutdown)

async def _renew_scheduler_lease(lease: SchedulerLease):
    while True:
        await asyncio.sleep(max(1, lease.ttl // 3))
        if not lease.renew():
            return


settings = get_settings()
configure_logging()
install_db_timing(engine)
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.middleware("http")(request_timing_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Main NMS backend (CRUD + RBAC + Auth + dashboard + audit)
app.include_router(router)

# Discovery / Monitoring / Analytics modules (formerly served by Flask on port 5000)
app.include_router(discovery_router, prefix="/api/v1")

# SNMP per-device monitoring endpoints (fills the gap the frontend already expects)
app.include_router(snmp_device_router)
app.include_router(manual_topology_router)

# Monitoring Data API (reads from database, no live polling)
app.include_router(monitoring_data_router)
app.include_router(flow_router)
app.include_router(apm_router)
app.include_router(cmdb_router)
app.include_router(rca_router)
app.include_router(incident_router)
app.include_router(problem_router)
app.include_router(change_router)
app.include_router(knowledge_router)
app.include_router(config_backup_router)
app.include_router(config_compliance_router)
app.include_router(availability_router)
app.include_router(virtualization_router)
app.include_router(qos_router)
app.include_router(bgp_router)
app.include_router(syslog_router)
app.include_router(linux_monitoring_router)

# Overview + Kill-all service control
app.include_router(overview_router)

# Legacy endpoints (/api/inventory, /api/discovery/modules, /api/discovery/summary)
# kept alive for backward compatibility with the React frontend.
app.include_router(legacy_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
