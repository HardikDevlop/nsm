from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.discovery_routes import router as discovery_router
from backend.api.legacy_routes import router as legacy_router
from backend.api.routes import router
from backend.api.snmp_device_routes import router as snmp_device_router
from backend.api.overview_routes import router as overview_router
from backend.config.settings import get_settings
from backend.database.session import Base, SessionLocal, engine, migrate_credential_columns
from backend.seed import seed_rbac, seed_ouis_and_products
from logging_config import configure_logging
from backend.snmp.polling import SNMPPollingEngine

import backend.models  # noqa: F401  (register all tables on Base.metadata)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_credential_columns()
    with SessionLocal() as db:
        seed_rbac(db)
        seed_ouis_and_products(db)
    polling = None
    try:
        from backend.models import Device
        devices = [row.ip_address for row in SessionLocal().query(Device).filter(Device.monitoring_status.is_(True)).all()]
        polling = SNMPPollingEngine(lambda _device, _collector: None)
        if devices:
            polling.start(devices)
    except ImportError:
        # APScheduler is an explicit deployment dependency; keep startup
        # compatible for environments that only run discovery tests.
        polling = None
    app.state.snmp_polling = polling
    yield
    if polling:
        polling.shutdown()


settings = get_settings()
configure_logging()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

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

# Overview + Kill-all service control
app.include_router(overview_router)

# Legacy endpoints (/api/inventory, /api/discovery/modules, /api/discovery/summary)
# kept alive for backward compatibility with the React frontend.
app.include_router(legacy_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
