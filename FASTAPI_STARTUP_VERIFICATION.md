# FastAPI Startup Verification

Date: 2026-08-29
Project: current NMS in `hardik/`
Scope: startup-only verification. No application code, APIs, frontend code, SNMP collectors, database rows, or migrations were modified.

## Summary

| Check | Result |
|---|---|
| Existing backend configuration read | PASS |
| PostgreSQL reachability | FAIL |
| Database connection | FAIL |
| FastAPI startup | FAIL |
| Application lifespan completion | FAIL |
| Migrations recognized as applied | NOT VERIFIED |
| RBAC seeding/startup | NOT REACHED |
| Scheduler initialization | NOT REACHED |
| `GET /api/v1/health` | FAIL (blocked) |

The runtime environment is still blocked by PostgreSQL. The local PostgreSQL 14 `main` cluster is down, and this environment cannot start it because root/cluster-owner privileges are unavailable.

## Startup Command

Run from `/home/agnigate/Desktop/NMS/hardik`:

```bash
timeout 20s .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Configuration

The existing `backend/.env` was parsed in memory. Only non-secret URL components were reported:

| Field | Value |
|---|---|
| Scheme | `postgresql+psycopg` |
| Host | `localhost` |
| Port | `5432` |
| Database | `postgres` |
| Role | `postgres` |
| Password | Not printed |

No configuration value was changed.

## PostgreSQL Result

Command:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Output:

```text
127.0.0.1:5432 - no response
```

Cluster status:

```text
14  main  5432  down  nobody  /var/lib/postgresql/14/main
```

Exact configured-URL SQLAlchemy connection error:

```text
(psycopg.OperationalError) connection is bad: no error details available
```

Status: **FAIL**

## FastAPI Result

Startup output:

```text
INFO:     Started server process [6]
INFO:     Waiting for application startup.
psycopg.OperationalError: connection is bad: no error details available
sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection is bad: no error details available
ERROR:    Application startup failed. Exiting.
```

Failing stage:

```text
backend.main.lifespan
Base.metadata.create_all(bind=engine, tables=existing_tables)
```

The failure occurs before:

- `run_migrations(engine)`
- RBAC seeding
- scheduler lease acquisition
- SNMP scheduler initialization
- application lifespan `yield`
- HTTP route serving

Status: **FAIL**

## Migration Result

Source contains 29 known migrations, from:

```text
20260821_0001_device_credentials_columns
through
20260829_0029_syslog_correlation
```

The database-backed migration status could not be queried because PostgreSQL was unavailable. No migration apply command was run.

Status: **NOT VERIFIED**

## RBAC and Scheduler Result

RBAC seeding and scheduler initialization were not reached because database initialization failed first. This is not a code-level RBAC or scheduler failure.

Status: **NOT REACHED**

## Health Endpoint Result

Command:

```bash
curl --connect-timeout 2 --max-time 5 -sS -o /tmp/nms-health-body -w 'http=%{http_code}\n' http://127.0.0.1:8000/api/v1/health
```

Output:

```text
curl: (7) Couldn't connect to server
http=000
```

Status: **FAIL (blocked by FastAPI startup)**

## Remaining Blocker

PostgreSQL must be started by a host administrator or cluster owner. The attempted local start failed because this runtime lacks the required privilege:

```text
Error: You must run this program as the cluster owner (postgres) or root
sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
```

After PostgreSQL is available, rerun:

```bash
pg_isready -h 127.0.0.1 -p 5432
cd /home/agnigate/Desktop/NMS/hardik
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/api/v1/health
```

No secrets were printed and no application or database state was changed.

