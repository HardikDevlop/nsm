# Runtime Verification Report

Date: 2026-08-29
Project: current NMS in `hardik/`
Scope: read-only runtime verification. No application code was changed and no mock/static data was inserted.

## Executive Result

Verification stopped at infrastructure startup dependencies. PostgreSQL was not reachable, so the FastAPI lifespan failed before migrations, RBAC seeding, scheduler startup, or route serving. Redis could not be positively verified. The frontend dev server failed to bind because this execution environment returned `EPERM`.

No live module API returned an HTTP response. No endpoint is marked `EMPTY`: an unreachable endpoint is `FAIL (blocked)`, not an empty data result. Authentication and RBAC were not functionally exercised because the API never started and no credentials were used.

## Status Vocabulary

- `PASS`: live verification completed successfully.
- `FAIL`: the requested runtime step was attempted and failed.
- `EMPTY`: endpoint responded successfully but returned no data.
- `NOT IMPLEMENTED`: no corresponding implementation/route exists.
- `FAIL (blocked)`: unreachable because an earlier runtime dependency failed.

## Dependency Results

| Check | Status | Result / failing stage |
|---|---|---|
| PostgreSQL running | FAIL | `127.0.0.1:5432` did not respond. |
| PostgreSQL connectivity | FAIL | `psql` could not create a socket. |
| Migrations applied | FAIL (blocked) | `schema_migrations` could not be queried. Source contains 29 known migrations, IDs `0001` through `0029`. |
| Redis status | FAIL | `redis-cli` was not installed; listener/handshake verification was unavailable. |
| FastAPI startup | FAIL | Lifespan failed during `Base.metadata.create_all(...)` with `psycopg.OperationalError: connection is bad: no error details available`. |
| Frontend startup | FAIL | Vite failed to bind `127.0.0.1:5173`: `listen EPERM: operation not permitted`. This is an environment bind restriction, not evidence of a frontend code failure. |
| Health endpoint | FAIL (blocked) | FastAPI was not serving. |
| Authentication | FAIL (blocked) | Login endpoint was unreachable; no credentials were supplied. |
| RBAC | FAIL (blocked) | Protected API was unreachable; permission behavior was not exercised. |
| Database connectivity through API | FAIL | SQLAlchemy connection failed during startup. |

## Exact Commands and Errors

### PostgreSQL

Command:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Output:

```text
127.0.0.1:5432 - no response
```

Command:

```bash
psql -h 127.0.0.1 -d postgres -c 'SELECT 1;'
```

Output:

```text
psql: error: connection to server at "127.0.0.1", port 5432 failed: could not create socket: Operation not permitted
```

The installed client reported `psql (PostgreSQL) 14.24`, but no database connection was established.

### Migration metadata

Command from `/home/agnigate/Desktop/NMS/hardik`:

```bash
.venv/bin/python -c "from backend.database.migrations import MIGRATIONS; print(len(MIGRATIONS)); print(MIGRATIONS[0].migration_id); print(MIGRATIONS[-1].migration_id)"
```

Output:

```text
29
20260821_0001_device_credentials_columns
20260829_0029_syslog_correlation
```

The application function `get_migration_status()` reads `schema_migrations`, but applied state could not be read without PostgreSQL. This does not prove migrations are unapplied.

### Redis

Commands:

```bash
command -v redis-cli
ss -ltn | rg ':(5432|6379|8000|5173)\b' || true
```

Output:

```text
Cannot open netlink socket: Operation not permitted
```

`redis-cli` produced no path. The environment denied listener inspection, so Redis was not verified as running.

### FastAPI

Command from `/home/agnigate/Desktop/NMS/hardik`:

```bash
timeout 20s .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Relevant output:

```text
INFO:     Started server process [6]
INFO:     Waiting for application startup.
psycopg.OperationalError: connection is bad: no error details available
sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection is bad: no error details available
ERROR:    Application startup failed. Exiting.
```

Failing stage: `backend.main.lifespan`, at `Base.metadata.create_all(...)), before `run_migrations(engine)`, RBAC seeding, scheduler initialization, and `yield`.

### Frontend

Command from `/home/agnigate/Desktop/NMS/figma design`:

```bash
timeout 15s npm run dev -- --host 127.0.0.1 --port 5173
```

Output:

```text
> NMS@1.0.0 dev
> vite --host 0.0.0.0 --host 127.0.0.1 --port 5173
error when starting dev server:
Error: listen EPERM: operation not permitted 127.0.0.1:5173
code: 'EPERM'
```

Failing stage: Vite listener bind. No browser/API behavior was asserted.

## Health, Authentication, RBAC and Connectivity

The source defines `GET /health`, `POST /auth/login`, and `GET /auth/me` in `hardik/backend/api/routes.py`.

Command:

```bash
for path in /health /api/v1/health /api/v1/auth/login /api/v1/auth/me /api/v1/devices; do
  curl --connect-timeout 2 --max-time 5 -sS -o /tmp/nms-runtime-body -w "$path http=%{http_code}\n" "http://127.0.0.1:8000$path" || true
done
```

Every probe returned:

```text
curl: (7) Couldn't connect to server
<path> http=000
```

No POST login was sent, so no credentials or database rows were modified.

## Major Module API Results

All probes were unauthenticated, read-only `GET` requests against `http://127.0.0.1:8000`. Every request failed with `http=000` and `curl: (7) Couldn't connect to server`.

| Module | Probe | Status | Exact reason |
|---|---|---|---|
| Core devices | `/api/v1/devices` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Discovery | `/api/v1/discovery/modules` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Monitoring | `/api/v1/monitoring/jobs` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Alerts | `/api/v1/alerts` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Topology | `/api/v1/topology` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Reports | `/api/v1/reports` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Flow analytics | `/api/v1/flows/analytics/trends` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| APM | `/api/v1/apm/overview` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| CMDB | `/api/v1/cmdb/items` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| RCA | `/api/v1/rca/incidents` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Incidents | `/api/v1/incidents` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Problems | `/api/v1/problems` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Changes | `/api/v1/changes` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Knowledge base | `/api/v1/knowledge` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Config backup | `/api/v1/config-backups/devices/1` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Compliance | `/api/v1/config-compliance/policies` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Availability | `/api/v1/availability/reports` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Virtualization | `/api/v1/virtualization/objects` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| QoS | `/api/v1/qos/samples` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| BGP | `/api/v1/bgp/neighbors` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |
| Syslog | `/api/v1/syslog/records` | FAIL (blocked) | FastAPI startup failed on PostgreSQL. |

No endpoint returned 200, so no result is classified as `EMPTY`. No endpoint is classified as `NOT IMPLEMENTED`, because runtime failed before route resolution; implementation status must be assessed separately from reachability.

## Required Next Verification Sequence

1. Start PostgreSQL and confirm `pg_isready -h 127.0.0.1 -p 5432` reports accepting connections.
2. Query `schema_migrations` and run migration status; confirm all 29 known IDs are applied.
3. Start Redis and verify `redis-cli -h 127.0.0.1 ping` or an equivalent authenticated health check.
4. Start FastAPI and confirm the lifespan reaches `yield`.
5. Start the frontend on an allowed port or outside the restricted listener environment.
6. Repeat health, login with an existing account, `/auth/me`, permission-denied and permission-allowed checks.
7. Repeat module API calls using real stored data only; classify HTTP 200 empty collections as `EMPTY`.

