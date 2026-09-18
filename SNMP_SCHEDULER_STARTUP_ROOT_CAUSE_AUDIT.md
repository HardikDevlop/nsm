# SNMP Scheduler Startup Root-Cause Audit

Read-only source audit based on the supplied clean-systemd runtime evidence. No code, scheduler state, or database data was changed.

## Lifecycle

`backend/main.py:lifespan()` automatically creates `SchedulerLease`, calls `acquire()`, and calls `get_polling_scheduler()` only when `scheduler_lease_owned` is true. It stores the scheduler in `app.state.snmp_polling` and starts lease renewal only after successful scheduler creation.

`get_polling_scheduler()` is a process-global singleton protected by an asyncio lock. First creation constructs `PollingScheduler(worker_count=8)` and awaits `PollingScheduler.start()`. `start()` starts APScheduler, loads DB jobs, sets `_running=True`, and logs `Polling scheduler started with 8 workers`.

`_load_jobs_from_db()` selects `MonitoringConfig.enabled IS TRUE` and `status == RUNNING`, then schedules each config. `_schedule_config()` uses `{device_id}:{module_name}`, checks capabilities, normalizes `next_poll_at`, and registers a one-shot `DateTrigger`; completed jobs reschedule themselves.

Automatic startup is therefore intended and exists, but is gated by lease ownership.

## Lease and Redis

`SchedulerLease` uses Redis key `nms:scheduler:leader`, a 30-second TTL, and a process/UUID token. Acquisition is `SET key token NX EX 30`. If the Redis client is `None`, it returns `environment != "production"`; Redis exceptions return `False`. In production, unavailable Redis or a lease held by another process prevents scheduler creation. Renewal verifies the token and extends TTL. Release deletes only a matching token. A stale lease can survive a restart only until its TTL expires, unless another process renews it.

The Redis helper creates a client without proving connectivity. `SchedulerLease.acquire()` silently converts connection/operation failure into false. There is no scheduler-specific log for lease acquired, lease denied, or Redis unavailable. Cache-level debug messages include `redis_cache_unavailable` and `redis_cache_read_failed`. Successful scheduler logs are `Polling scheduler started with 8 workers` and `Loaded N polling jobs from database`; shutdown logs `Polling scheduler stopped`. Startup exceptions would propagate to Uvicorn/systemd logging, but the lifespan block has no specific catch/log.

The supplied `lease_owned=false`, stopped state, and zero jobs are evidence that startup was gated before scheduler creation. They are not merely an expected pre-start state because the lifespan is designed to auto-start it.

## Config restoration and endpoint behavior

The 26 configured rows are restored only after successful lease acquisition and scheduler start. They become individual device/module jobs only when enabled, status RUNNING, and capability checks permit them. The restore query does not explicitly filter deleted devices. Therefore 26 enabled rows should register 26 jobs only conditionally; unsupported capabilities can change status to `not_supported` and skip registration.

`POST /api/v1/monitoring/polling/start` in `overview_routes.py` is a recovery endpoint. It first checks `request.app.state.scheduler_lease_owned`; when false it immediately returns `_get_service_states(request)`. When true it calls the singleton getter. It is idempotent, but HTTP 200 does not guarantee that the scheduler is running. It does not acquire or repair the lease.

Other explicit SNMP monitoring-management endpoints call `get_polling_scheduler()` for module configuration operations. The Dashboard overview path is the relevant recovery caller here.

## Frontend and read-path side effect

The active frontend caller is `figma design/src/pages/Dashboard.tsx:Dashboard.load()`. It calls `getOverview()`, and when `snapshot.services.snmp_polling.running` is false, calls `startPollingService()`, then calls `getOverview()` again. A `useEffect` repeats `load(true)` every 30 seconds while visible. Source search found no additional active frontend callers in Dashboard-adjacent Layout, Sidebar, React Query, or monitoring hooks.

This explains the repeated POST logs: every refresh sees stopped state, calls the endpoint, receives 200 while lease ownership remains false, and repeats 30 seconds later. Dashboard overview loading therefore has a start/recovery write side effect. It is a lifecycle defect and symptom amplifier, not the underlying scheduler failure.

## Singleton and observability

There is one scheduler singleton per FastAPI process, protected by `_scheduler_lifecycle_lock`. Separate processes have separate Python singletons and rely on the Redis lease. The earlier duplicate-backend incident is not required for the current one-process stopped state; stale lease ownership remains a possible secondary condition for the 30-second TTL.

`/monitoring/services` obtains runtime state from `request.app.state.snmp_polling` (or `backend.main.app` when called without a request). `running` and `scheduler_running` are `scheduler.running`; `job_count` and `registered_jobs` are `len(scheduler.get_jobs())`; `scheduler_state` is derived from that boolean; `lease_owned` is the startup snapshot on app state; `active_jobs` and all five timestamps plus `recent_failure_count` are process-local fields on `PollingScheduler`. Null timestamps before the first execution are accurate. These fields do not use historical `PollingHistory` as proof of current activity.

## Root cause

The primary root cause is lease acquisition failure or non-ownership during FastAPI lifespan. In production, the current design requires Redis for the lease; false acquisition leaves `app.state.snmp_polling=None`, registers no jobs, and starts no renewal task. The recovery endpoint cannot correct this and can still return HTTP 200.

Secondary causes are silent lease/Redis diagnostics and the Dashboard’s 30-second read-path recovery request, which makes a no-op look like successful recovery in access logs. The safe minimal fix is to add explicit lease/startup diagnostics and correct the recovery/read-path contract after confirming Redis/lease state. A Redis fallback should not be introduced without an architecture decision.

INTENDED STARTUP OWNER: FastAPI `lifespan()`
AUTO-START EXPECTED: YES
CURRENT AUTO-START PATH EXISTS: YES
WHY SCHEDULER CAN REMAIN STOPPED: Lease acquisition returns false, so lifespan skips `get_polling_scheduler()`; recovery endpoint also no-ops when lease is false
REDIS REQUIRED FOR START: YES in production under current implementation
LEASE REQUIRED FOR START: YES
LEASE FAILURE BEHAVIOR: Silent false; scheduler is not created, renewal is not started, and recovery may return HTTP 200 without starting it
ENABLED CONFIG RESTORE PATH: `PollingScheduler.start()` → `_load_jobs_from_db()` → enabled/RUNNING configs → `_schedule_config()`
26 CONFIGS SHOULD AUTO-REGISTER: CONDITIONAL
POLLING START ENDPOINT IDEMPOTENT: YES
HTTP 200 GUARANTEES SCHEDULER RUNNING: NO
FRONTEND START CALLERS: `Dashboard.tsx:Dashboard.load()` via 30-second refresh; no other active frontend caller found
WHY ~30 SECOND START CALLS OCCUR: Dashboard interval repeats overview, sees stopped state, and calls recovery
READ PATH HAS START SIDE EFFECT: YES
DUPLICATE SCHEDULER INSTANCE RISK: Low within one process due singleton lock; cross-process risk is lease-controlled
PRIMARY ROOT CAUSE: Production lease acquisition failure/non-ownership prevents scheduler creation
SECONDARY ROOT CAUSES: Silent Redis/lease diagnostics, HTTP 200 no-op recovery, Dashboard read-path start side effect
SAFE MINIMAL FIX: Add explicit lease/startup diagnostics and correct recovery/read-path contract after confirming Redis/lease state
CODE CHANGED: NO
