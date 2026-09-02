# Scheduler Runtime Verification

Date: 2026-08-29
Project: current NMS in `hardik`
Scope: read-only runtime verification. No code, database rows, devices, jobs, credentials, OIDs, or poll state were changed.

## Overall Result

**ENVIRONMENT ACCESS BLOCKED**

The current execution environment cannot reach the host FastAPI backend or PostgreSQL service. No existing device or monitoring job could be selected, and no poll was triggered. The scheduler source was inspected only; source presence is not runtime verification.

## Verification Results

| Item | Result | Evidence |
|---|---|---|
| Scheduler starts during FastAPI lifespan | NOT TESTABLE | Backend was inaccessible; no lifespan could be observed. |
| Existing monitoring jobs are loaded | NOT TESTABLE | Database and monitoring API were inaccessible. |
| Configured polling intervals recognized | NOT TESTABLE | No existing job/configuration record could be read. |
| Existing monitored device selected | NOT TESTABLE | No device query/API response was available. |
| `polling_history` receives entries | NOT TESTABLE | No poll was triggered and database was inaccessible. |
| Latest metrics update after polling | NOT TESTABLE | No poll was triggered and latest-metrics API was inaccessible. |
| Historical metrics update | NOT TESTABLE | No poll was triggered and database/API were inaccessible. |
| Duplicate poll protection active | NOT TESTABLE | No live poll or concurrent request was sent. |
| Scheduler stop/restart is clean | NOT TESTABLE | Backend lifecycle could not be started or stopped. |

No item is marked `FAIL`: these results reflect host access being blocked, not evidence that the scheduler implementation is broken. No item is marked `EMPTY` because no successful API/database response was received.

## Exact Reachability Checks

### FastAPI health

Command:

```bash
curl --connect-timeout 3 --max-time 8 -sS \
  -D /tmp/nms-scheduler-health-headers \
  -o /tmp/nms-scheduler-health-body \
  -w 'http=%{http_code} remote=%{remote_ip}\n' \
  http://127.0.0.1:8000/api/v1/health
```

Output:

```text
curl: (7) Couldn't connect to server
http=000 remote=
```

### PostgreSQL

Command:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Output:

```text
127.0.0.1:5432 - no response
```

### Backend process

Command:

```bash
ps -ef | rg 'uvicorn|gunicorn|fastapi' | rg -v 'rg '
```

Result: no backend process was visible in this execution environment.

## Source-Level Scheduler Trace

The existing source defines the runtime flow:

1. `backend/main.py` creates a `SchedulerLease` during FastAPI lifespan.
2. It calls `get_polling_scheduler()` during lifespan.
3. `backend/services/snmp_polling.py` creates an `AsyncIOScheduler`, starts it, and loads enabled monitoring configurations.
4. The scheduler exposes existing monitoring/status and polling-history routes.
5. Shutdown calls `shutdown_polling_scheduler()`.

These points were not promoted to `PASS` because the application never became reachable.

## Runtime Calls Not Performed

The following calls were intentionally not sent because the backend was inaccessible and the request requires existing live data only:

```text
GET  /api/v1/snmp/devices
GET  /api/v1/snmp/devices/{device_id}/monitoring
GET  /api/v1/snmp/devices/{device_id}/monitoring/{module}/status
GET  /api/v1/snmp/devices/{device_id}/polling-history
GET  /api/v1/snmp/devices/{device_id}/metrics/latest
POST /api/v1/snmp/devices/{device_id}/poll
```

No mock device, fake job, manual poll, credential change, or database write was performed.

## Required Host-Side Verification

Run from the same network namespace as the healthy host backend:

```bash
BASE=http://127.0.0.1:8000
curl -fsS "$BASE/api/v1/health"
curl -fsS "$BASE/api/v1/snmp/devices"
```

Then select an existing device with an enabled job and compare, before and after a normal scheduler cycle:

```bash
curl -fsS "$BASE/api/v1/snmp/devices/<device_id>/monitoring"
curl -fsS "$BASE/api/v1/snmp/devices/<device_id>/polling-history"
curl -fsS "$BASE/api/v1/snmp/devices/<device_id>/metrics/latest"
```

A real duplicate-protection test requires two concurrent requests for the same existing device/module and should observe one active poll plus the existing conflict/guard behavior. Stop/restart must be observed through the actual service lifecycle, not simulated with test data.

## Remaining Blocker

The host backend and database are not accessible from this restricted environment. Scheduler startup, job restoration, intervals, persistence, latest/history updates, duplicate protection, and restart behavior remain unverified until the checks are run from the backend host/network namespace.

