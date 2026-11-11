# AgniGate NMS — Project Overview

## Audit basis

Read-only static audit of `/home/agnigate/Desktop/NMS` on 2026-11-04. Runtime state, live database state, device connectivity, migrations, tests, and services were not executed. Claims below are repository evidence; behavior not exercised is **IMPLEMENTED — UNVERIFIED**.

## Identity and stack

The repository implements AgniGate Network Monitoring System (NMS): a network/server monitoring and IT operations platform covering discovery, inventory, polling, alerts, reporting, remote access, topology, flow/syslog, Windows/Linux monitoring, CMDB, incidents/problems/changes, knowledge, and administration.

| Area | Evidence | Finding |
|---|---|---|
| Backend | `hardik/backend/main.py` | FastAPI application, startup lifespan, routers, schedulers, ingestion services |
| Backend language | `hardik/backend/**/*.py` | Python |
| Frontend | `figma design/src/main.tsx`, `App.tsx`, `routes.tsx` | React 19, TypeScript, React Router 8, Vite |
| Database | `hardik/backend/database/session.py`, `requirements.txt` | SQLAlchemy 2 with PostgreSQL/psycopg; migrations are application-owned SQL |
| Async/runtime | `main.py`, service modules | asyncio, Uvicorn, APScheduler, Redis cache support |
| Monitoring | `backend/snmp`, `monitoring_modules`, OS monitoring packages | ICMP, SNMP, SSH/Telnet, WinRM/CIM, Linux SSH/SNMP; flow/syslog receivers |
| Security | `backend/auth`, `dependencies.py`, `utils/crypto.py` | JWT, bcrypt/passlib, Fernet credential encryption, role/permission/site checks |
| Deployment evidence | `hardik/start_*.sh`, `requirements.txt`, settings | local/Uvicorn and systemd references; no Docker or Nginx deployment artifact was found |

## Major roots

- `hardik/backend`: backend application, API, domain services, models, migrations, monitoring adapters.
- `hardik/discovery_modules`: ICMP/IP/TCP/ARP/DNS/HTTP/SSH/SNMP/WMI discovery and profiling.
- `hardik/analytics_modules`: topology, event and alert engines.
- `figma design`: frontend application, routes, components, API client and regression tests.
- `hardik/docs`: operational/feature notes and examples.
- `db_backups`: database dumps; not used as live-state evidence.

## Overall architecture

The system is a modular monolith: one FastAPI process registers broad REST routers and owns application startup, PostgreSQL access, scheduled polling/reporting, optional flow/syslog receivers, remote-session ownership, and Linux/ICMP scheduler restoration. The React SPA calls `/api/v1` endpoints and uses authenticated WebSockets for terminal sessions. A remote collector deployment is not verified in source/configuration.

