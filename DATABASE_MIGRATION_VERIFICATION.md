# Database Migration Verification

Date: 2026-08-29
Project: current NMS in `hardik/`
Scope: read-only verification. No application code was changed and no migrations were applied.

## Summary

| Item | Result |
|---|---|
| Exact configured DB scheme | `postgresql+psycopg` |
| Configured host | `localhost` |
| Configured port | `5432` |
| Database name | `postgres` |
| Role name | `postgres` |
| Password printed | No |
| Database connection | FAIL |
| Database exists | NOT VERIFIED |
| Role authentication | FAIL |
| Required privileges | NOT VERIFIED |
| `schema_migrations` table | NOT VERIFIED |
| Known migration count | 29 |
| Applied migration count | NOT VERIFIED |
| Pending migration count | NOT VERIFIED |
| Pending migration IDs | NOT VERIFIED |
| Migrations applied during this check | No |

## Exact Configuration Inspection

The URL was parsed in memory from `backend/.env`; only non-secret components were printed.

Command:

```bash
cd /home/agnigate/Desktop/NMS/hardik
./.venv/bin/python - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit

values = {}
for raw in Path('backend/.env').read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    values[key] = value.strip().strip('"').strip("'")

parts = urlsplit(values['DATABASE_URL'])
print(parts.scheme, parts.hostname, parts.port, parts.path.lstrip('/'), parts.username)
print('password_printed=no')
PY
```

Output:

```text
configured_scheme=postgresql+psycopg
configured_host=localhost
configured_port=5432
configured_database=postgres
configured_role=postgres
configured_password_printed=no
```

No password, complete URL, token, or secret was printed.

## PostgreSQL Readiness

Command:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Output:

```text
127.0.0.1:5432 - no response
```

Status: **FAIL**

Cluster inspection:

```text
14  main  5432  down  nobody  /var/lib/postgresql/14/main
```

## Exact-Configuration Connection

The following read-only probe used the complete configured URL in memory. It did not print the URL or password.

Command:

```bash
cd /home/agnigate/Desktop/NMS/hardik
./.venv/bin/python - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
from backend.database.migrations import MIGRATIONS

values = {}
for raw in Path('backend/.env').read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    values[key] = value.strip().strip('"').strip("'")

url = values['DATABASE_URL']
print('password_printed=no')
print(f'known_migration_count={len(MIGRATIONS)}')

engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    print(conn.execute(text('SELECT current_database(), current_user')).one())
PY
```

Output:

```text
password_printed=no
known_migration_count=29
connection=FAIL
exact_error=(psycopg.OperationalError) connection is bad: no error details available
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

The configured PostgreSQL role could not authenticate because the server connection failed before authentication/database selection completed. This error does not distinguish a wrong password from an unavailable server.

## Database and Privilege Checks

These queries were prepared but could not execute because the connection failed:

```sql
SELECT current_database(), current_user;
SELECT has_database_privilege(current_user, current_database(), 'CONNECT');
SELECT has_schema_privilege(current_user, current_schema(), 'CREATE');
SELECT to_regclass('public.schema_migrations') IS NOT NULL;
SELECT migration_id FROM schema_migrations;
```

Results:

- Database existence: **NOT VERIFIED**
- Configured role authentication: **FAIL**
- CONNECT privilege: **NOT VERIFIED**
- Schema privilege: **NOT VERIFIED**
- `schema_migrations` existence: **NOT VERIFIED**
- Applied migration IDs: **NOT VERIFIED**

## Migration Comparison

Source inspection reports:

```text
known_migration_count=29
first=20260821_0001_device_credentials_columns
last=20260829_0029_syslog_correlation
```

The project compares known IDs with the database table through `get_migration_status()`, but the database was unavailable. Therefore:

- Applied migration count: **NOT VERIFIED**
- Pending migration count: **NOT VERIFIED**
- Pending migration IDs: **NOT VERIFIED**
- No migrations were applied by this verification.

## Root Blocker

PostgreSQL cluster `14/main` is down and local service control is unavailable in this runtime. Starting it requires the cluster owner or root. The attempted start returned:

```text
Error: You must run this program as the cluster owner (postgres) or root
```

A non-interactive privileged attempt returned:

```text
sudo: a password is required
```

No application configuration was changed. Once PostgreSQL is started, rerun the connection and migration comparison probes; do not run the migration apply command until the pending IDs have been reviewed.

