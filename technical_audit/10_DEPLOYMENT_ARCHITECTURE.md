# Deployment and Runtime Architecture

## Evidence-backed design

The documented/local startup path is a Python environment running Uvicorn with `backend.main:app` on `127.0.0.1:8000`; shell scripts also exist for starting backend/monitoring services. PostgreSQL is the configured database, Redis is configured as a cache dependency, and APScheduler/background service objects run inside the backend process. Optional flow and syslog listeners bind configurable addresses/ports.

## Not verified

No Dockerfile, Docker Compose file, Nginx config, PM2 config, or systemd unit was found in the audited paths. `requirements.txt` contains systemd command examples, which supports a documented deployment intent but not an installed/running service. Backup dumps exist, but backup automation, restore procedures and RPO/RTO are not established by source evidence.

## Startup sequence

FastAPI lifespan → create/migrate schema → seed RBAC/OUI → reconcile CMDB → optionally start flow/syslog → initialize remote access and reconcile stale sessions → acquire scheduler lease → restore reports/SNMP/Linux/ICMP work. This sequence is source-defined; actual runtime success is unverified.

