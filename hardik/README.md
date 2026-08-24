# AgniGate NMS — Unified FastAPI Backend (port 8000)

All NMS services now run on a **single port**: `http://127.0.0.1:8000`.

The legacy Flask Discovery Service (`icmp_discovery/app.py`, port 5000) is
**deprecated** — every endpoint it used to expose has been migrated into
the FastAPI backend.

## Service Map

| What                        | Port | URL                          |
| --------------------------- | ---- | ---------------------------- |
| **NMS Backend (unified)**   | 8000 | http://localhost:8000/api/v1 |
| **React Dashboard (Vite)**  | 5173 | http://localhost:5173        |

## What lives at port 8000

1. **CRUD + Auth + RBAC** (17 resource modules: Organizations, Sites,
   Vendors, Device Types, Devices, Credentials, Interfaces, Monitoring
   Jobs, Metrics, Thresholds, Alerts, Events, Notifications, Reports,
   Users, Roles, Permissions), Dashboard, Audit Logs — all behind JWT
   auth. Default admin: `admin@gmail.com / admin123`.

2. **Discovery / Monitoring / Analytics modules** (no auth required):
   `POST /api/v1/discovery/{ip,icmp,tcp,arp,dns,http,snmp,ssh,wmi,profile}`
   `POST /api/v1/monitoring/{icmp,snmp,syslog/ingest,syslog/parse,trap/ingest}`
   `POST /api/v1/analytics/{alerts/evaluate,alerts/thresholds,events/from-samples,events/normalize,topology}`

3. **Orchestrated runs** (RBAC-protected):
   `POST /api/v1/discovery/run` (full scan → DB)
   `POST /api/v1/monitoring/run` (single check → DB)

4. **Legacy backward-compatible routes** (for the React frontend):
   `GET /api/inventory`, `GET /api/discovery/modules`,
   `GET /api/discovery/summary`

## Quick Start

```powershell
cd C:\Users\Agnigate\Desktop\hardik
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
source .venv/bin/activate
```
<!-- Test And Kill SERVER
lsof -ti:8000 
lsof -ti:8000 | xargs kill 129061 -->

Or use the launcher (starts backend + a Flask legacy stub for
reference, both stop on Ctrl+C):

```powershell
.\.venv\Scripts\python.exe start_services.py
```

## Postman Collections

Two collections, both pointing at the same single-port backend:

- `backend/postman/NMS_Backend_API.postman_collection.json`
  → `baseUrl = http://localhost:8000/api/v1` (102 endpoints)

- `icmp_discovery/postman/Discovery_Service_API.postman_collection.json`
  → `baseUrl = http://127.0.0.1:8000/api/v1` (29 endpoints, no auth)

## React Frontend Proxy

`frontend/vite.config.js` proxies every `/api/*` request to port 8000,
so the React app can call relative URLs and reach both legacy and new
endpoints on the same backend.

## Database Setup (one-time)

```powershell
.\.venv\Scripts\python.exe -m backend.init_db
```

Initializes the database configured in `DATABASE_URL`, creates the schema,
applies startup migrations, seeds permissions/roles, and ensures the
default admin account exists.

Important: this project now uses the existing configured PostgreSQL
database instead of assuming a separate `NMS_DB` database must be
created. In the current local setup, that live database is `postgres`.

## Smoke Test

```powershell
.\.venv\Scripts\python.exe backend\unified_smoke_test.py
```

29 endpoints covering health, legacy, discovery modules, monitoring
modules, analytics, auth, dashboard, and CRUD listings — all on the
single port 8000. **29/29 PASS** in ~2 seconds.

## What happened to the Flask service?

`icmp_discovery/app.py` is still present in the repo as a legacy
artifact, but it is **no longer used**. All discovery / monitoring /
analytics endpoints it used to serve have been ported to
`backend/api/discovery_routes.py` (FastAPI `APIRouter`) and
`backend/api/legacy_routes.py` (backward-compatible paths). The
underlying Python modules under `icmp_discovery/discovery_modules/`,
`monitoring_modules/`, and `analytics_modules/` are reused unchanged
by the FastAPI backend.
