from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.discovery_routes import router as discovery_router
from backend.api.legacy_routes import router as legacy_router
from backend.api.routes import router
from backend.api.snmp_device_routes import router as snmp_device_router
from backend.api.manual_topology_routes import router as manual_topology_router
from backend.api.overview_routes import router as overview_router
from backend.api.monitoring_data_routes import router as monitoring_data_router
from backend.linux_monitoring.api import router as linux_monitoring_router
import backend.linux_monitoring.models  # noqa: F401 (register Linux monitoring tables)
from backend.linux_monitoring.models import LINUX_MONITORING_TABLES
from backend.config.settings import get_settings
from backend.database.migrations import run_migrations
from backend.database.session import Base, SessionLocal, engine
from backend.observability import install_db_timing, request_timing_middleware
from backend.seed import seed_rbac, seed_ouis_and_products
from backend.services.snmp_polling import get_polling_scheduler, shutdown_polling_scheduler
from backend.linux_monitoring.scheduler import LinuxMonitoringScheduler
from logging_config import configure_logging

import backend.models  # noqa: F401  (register all tables on Base.metadata)


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

    # Start centralized SNMP polling scheduler
    scheduler = await get_polling_scheduler()
    app.state.snmp_polling = scheduler
    linux_scheduler = LinuxMonitoringScheduler()
    app.state.linux_monitoring_scheduler = linux_scheduler
    await linux_scheduler.restore_enabled_servers()
    yield
    await linux_scheduler.shutdown()
    await shutdown_polling_scheduler()


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
app.include_router(linux_monitoring_router)

# Overview + Kill-all service control
app.include_router(overview_router)

# Legacy endpoints (/api/inventory, /api/discovery/modules, /api/discovery/summary)
# kept alive for backward compatibility with the React frontend.
app.include_router(legacy_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
