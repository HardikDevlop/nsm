# Runtime Recovery Report

Date: 2026-08-29
Project: current NMS in `hardik`
Scope: infrastructure/runtime startup only. No application business logic, SNMP collectors, APIs, frontend modules, enterprise features, database rows, or secrets were changed.

## Root Cause

The configured PostgreSQL 14 `main` cluster was down:

```text
Ver Cluster Port Status Owner  Data directory
14  main    5432 down   nobody /var/lib/postgresql/14/main
```

The backend configuration points to the PostgreSQL URL in `backend/.env`, with database name `postgres`, role `postgres`, and local port `5432`. The password value is intentionally not printed.

The cluster could not be started from this execution environment because the data directory is owned by `nobody:nogroup` and privileged service control is unavailable. `sudo` is blocked by the container's `no new privileges` policy and also reports an invalid ownership warning for `/etc/sudo.conf`.

## Actions and Exact Results

### Configuration inspection

Commands:

```bash
cd /home/agnigate/Desktop/NMS/hardik
awk -F= '{print $1}' backend/.env
sed -n '1,45p' backend/config/settings.py
```

Result:

- `backend/.env` contains `DATABASE_URL`; its value was not printed.
- `backend/config/settings.py` reads that environment file.
- The configured database target is PostgreSQL on local port 5432, database `postgres`, role `postgres`.
- Redis is configured as `redis://localhost:6379/0`.
- No configuration change was required or made.

### PostgreSQL readiness

Command:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Output:

```text
127.0.0.1:5432 - no response
```

Status: **FAIL**

### PostgreSQL cluster/service inspection

Commands:

```bash
pg_lsclusters
pg_ctlcluster 14 main start
sudo -n pg_ctlcluster 14 main start
```

Results:

```text
14  main  5432  down  nobody  /var/lib/postgresql/14/main
```

```text
Error: You must run this program as the cluster owner (postgres) or root
```

```text
sudo: a password is required
```

A final privileged attempt reported:

```text
sudo: /etc/sudo.conf is owned by uid 65534, should be 0
sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
sudo: If sudo is running in a container, you may need to adjust the container configuration to disable it.
```

Status: **NOT RECOVERED**

### PostgreSQL listener/configuration

The existing PostgreSQL configuration already specifies:

```text
listen_addresses = '*'
port = 5432
unix_socket_directories = '/var/run/postgresql'
```

No listener change was made. The cluster is down, so there is no active listener.

### PostgreSQL authentication/database/privileges

Command:

```bash
psql -h 127.0.0.1 -d postgres -c 'SELECT 1;'
```

Output:

```text
psql: error: connection to server at "127.0.0.1", port 5432 failed: could not create socket: Operation not permitted
```

Status: **NOT VERIFIED**

Database existence, role password authentication, and privileges cannot be checked until the server is running. No password was printed or changed.

### Redis

Inspection found:

- `redis-cli` is not installed.
- No Redis process was running.
- Redis cache code is fail-open for selected reads/writes.
- HA scheduler ownership uses Redis when available, but development configuration permits startup without a Redis client.

Status: **NOT RECOVERED / NOT REQUIRED TO FIX THE CURRENT FIRST BLOCKER**

No Redis installation or configuration change was made.

### Migration status

Source inspection found 29 known migrations, from:

```text
20260821_0001_device_credentials_columns
through
20260829_0029_syslog_correlation
```

The application migration status function reads `schema_migrations`, but PostgreSQL is unavailable. No migration command was run because the database server was down; no schema change was attempted.

Status: **NOT VERIFIED**

### FastAPI startup

Command from `/home/agnigate/Desktop/NMS/hardik`:

```bash
timeout 20s .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Output:

```text
INFO:     Waiting for application startup.
psycopg.OperationalError: connection is bad: no error details available
sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection is bad: no error details available
ERROR:    Application startup failed. Exiting.
```

Failing stage: `backend.main.lifespan`, during `Base.metadata.create_all(...)`, before `run_migrations(engine)`, scheduler initialization, or route serving.

Status: **FAIL**

## Verification Summary

| Item | Status | Reason |
|---|---|---|
| PostgreSQL service/cluster | FAIL | Cluster `14/main` is down. |
| Listening on 127.0.0.1:5432 | FAIL | No active listener because cluster is down. |
| Configured DB target | PASS | Existing configuration points to PostgreSQL database `postgres` on port 5432; no secret exposed. |
| PostgreSQL authentication | NOT VERIFIED | Server unavailable. |
| Database existence | NOT VERIFIED | Server unavailable. |
| Role privileges | NOT VERIFIED | Server unavailable. |
| `schema_migrations` | NOT VERIFIED | Server unavailable. |
| All migrations applied | NOT VERIFIED | Applied IDs could not be queried. |
| Redis | NOT RECOVERED | CLI absent and service not verified; current code treats cache as optional in development. |
| FastAPI startup | FAIL | Database connection fails during lifespan. |
| `GET /health` | BLOCKED | FastAPI never reached route serving. |

## Remaining Blocker

A host administrator must start the existing PostgreSQL cluster as the cluster owner/root, for example from a host with service privileges:

```bash
sudo systemctl start postgresql@14-main
# or:
sudo pg_ctlcluster 14 main start
```

After that, rerun:

```bash
pg_isready -h 127.0.0.1 -p 5432
cd /home/agnigate/Desktop/NMS/hardik
.venv/bin/python -c "from backend.database.migrations import get_migration_status; from backend.database.session import engine; print(get_migration_status(engine))"
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/api/v1/health
```

At the time of this report, PostgreSQL could not be recovered from the restricted runtime, so database authentication, migration application state, FastAPI startup success, and `GET /health` remain unverified.

