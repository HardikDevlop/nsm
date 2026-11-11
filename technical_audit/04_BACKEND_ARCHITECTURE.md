# Backend Architecture

## Startup and boundaries

`hardik/backend/main.py` creates the FastAPI app, installs CORS and timing middleware, registers 26 route modules, creates/migrates tables, seeds RBAC/OUI data, reconciles CMDB and remote sessions, optionally starts flow/syslog receivers, acquires an HA scheduler lease, restores report/SNMP/Linux/ICMP jobs, and shuts down process-owned resources. Startup therefore has significant operational side effects and is not a passive API process.

## Layers

- API routers and Pydantic schemas handle HTTP contracts.
- Dependencies (`dependencies.py`) resolve database sessions, current users, permissions and site scope.
- Services implement discovery, monitoring, polling, alerting, reporting, remote sessions, OS monitoring and domain workflows.
- SQLAlchemy models under `backend/models` and OS-specific model modules define persistence.
- Protocol adapters are grouped under SNMP, discovery modules, remote access and Windows/Linux monitoring.

## Verified source relationships

`main.py` registers routers for core, discovery, SNMP, topology, overview, remote access, monitoring data, flow, APM, CMDB, RCA, incidents, problems, changes, knowledge, backups, compliance, availability, virtualization, QoS, BGP, syslog, Linux, Windows and Windows helper APIs. The main core router in `api/routes.py` contains the largest legacy/core surface (131 route declarations).

## Architectural observations

- The modular-monolith boundary is logical rather than process-isolated.
- `Base.metadata.create_all` plus custom `run_migrations` creates dual schema-management paths.
- Scheduling is centralized but startup restores multiple scheduler domains.
- Remote terminal transport is process-owned while durable session records survive restart; startup reconciliation disconnects stale sessions.
- Redis is an optional cache dependency in settings, not evidence of a required distributed cache deployment.

