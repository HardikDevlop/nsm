# Polling Reliability and Observability Report

## Scope

Step 4 only. No polling intervals, OIDs, collector output, device-health calculation, or page redesign was changed.

## Polling paths

### SNMP

`backend/main.py:lifespan()` acquires `SchedulerLease` and starts the singleton `PollingScheduler`. `get_polling_scheduler()` creates one `AsyncIOScheduler`; `_load_jobs_from_db()` restores enabled/running `MonitoringConfig` rows. `_schedule_config()` uses deterministic `device_id:module_name` IDs and `replace_existing=True`. `_execute_poll_job()` runs the poll in a bounded application semaphore and worker thread, persists config state, then schedules the next one. Exceptions update config error state and reschedule. Lifespan shutdown calls `shutdown_polling_scheduler()`.

### ICMP

`MonitorEngine` in `backend/services/realtime_monitor.py` is a singleton with one background thread and bounded executor. `start_all()` is idempotent by IP. Step 4 adds `restore_enabled_devices()`, called once during FastAPI lifespan, to restore persisted `Device.monitoring_status=True` devices. `ICMPMonitor` and `run_monitoring_check()` remain collection/manual paths; optimized probe/executor internals were not rewritten.

## Reliability changes

- Explicit APScheduler `max_instances=1` prevents the same scheduled job from overlapping itself.
- `coalesce=True` prevents a delayed scheduler from replaying a large backlog of missed DateTrigger executions.
- Existing `misfire_grace_time=300` is retained: only a recent missed execution is eligible; stale misses are discarded.
- Existing `poll_guard` remains the device/module single-flight protection.
- Scheduler heartbeat fields now track active jobs, last start/finish/success/failure, and recent failures.
- ICMP startup restoration uses the existing singleton and idempotent `start_all()`, preventing duplicate monitor loops.
- Existing failure rollback/session cleanup and next-poll rescheduling paths remain intact.

## Observability API

`GET /api/v1/monitoring/services` remains backward-compatible and now adds to `snmp_polling`:

`scheduler_running`, `scheduler_state`, `lease_owned`, `registered_jobs`, `active_jobs`, `last_job_started_at`, `last_job_finished_at`, `last_job_success_at`, `last_job_failure_at`, and `recent_failure_count`.

Existing `running` and `job_count` fields remain. Per-job APIs continue exposing device/module, interval, last poll, next poll, status, error, and scheduled state. No credentials are exposed.

## Attempt observability limitation

Existing `PollingHistory` records completed persisted outcomes with duration/error, but it does not yet contain separate `scheduled_at`, `started_at`, and `finished_at` columns or an explicit persisted `SKIPPED_OVERLAP` row. The in-memory heartbeat exposes active and aggregate timing, while the existing guard still logs skipped overlaps. A full attempt ledger is deferred because the step requested reuse of existing storage and no unnecessary duplicate table.

## Final summary

- SNMP SCHEDULER START: **PASS** (source; runtime pending)
- SCHEDULER SINGLE INSTANCE: **PASS** with global lifecycle lock and lease; runtime pending
- SCHEDULER LEASE: **PARTIAL** — ownership is acquired/renewed/released and now exposed, but Redis/production runtime was not available
- JOB RESTORE AFTER RESTART: **PASS** source; runtime pending
- ICMP RESTORE AFTER RESTART: **PASS** source; runtime pending
- DUPLICATE SNMP POLLS: **PROTECTED** (`max_instances=1`, deterministic IDs, replace-existing, poll guard)
- DUPLICATE ICMP LOOPS: **PROTECTED** singleton/idempotent registry
- MAX_INSTANCES: **1 per APScheduler job**
- COALESCE: **true**
- MISFIRE POLICY: **300-second grace; coalesce one eligible execution; stale backlog discarded**
- FAILED POLL RESCHEDULE: **PASS** source
- LONG POLL HANDLING: **PASS/PARTIAL** — overlap blocked and bounded; explicit persisted skipped-attempt row remains deferred
- DB FAILURE ISOLATION: **PARTIAL** — worker rollback/cleanup and next-cycle reschedule exist; temporary PostgreSQL failure was not runtime tested
- SCHEDULER HEARTBEAT: **PASS** source/API; runtime pending
- POLL ATTEMPT OBSERVABILITY: **PARTIAL** — completed attempts are persisted; start/finish/scheduled fields are not yet a durable ledger
- MONITORING SERVICES API: **PASS** additive fields
- 3 CONSECUTIVE REAL POLLS: **PENDING**
- POLLING CONTINUES OVER TIME: **PENDING**
- PYTHON COMPILE: **PASS**

## Confirmed root cause of “polling works then stops”

Source evidence confirms the system previously allowed scheduler state to look healthy without a durable execution heartbeat, used implicit APScheduler overlap/misfire defaults, and did not restore the ICMP registry automatically on startup. A definitive single runtime root cause cannot be claimed without observing three real cycles and failure injection. The most actionable reliability defects are now addressed with explicit scheduling policy, heartbeat metadata, and ICMP restoration.

## P0 issues remaining

- Runtime proof is still required to confirm the scheduler continues through three cycles and after a database/device failure.
- Durable per-attempt start/finish/scheduled timestamps and explicit skipped-overlap persistence remain incomplete.

## P1 issues

- Add focused tests when the project test runner is available (`pytest` is not installed here).
- Add bounded heartbeat age classification (`RUNNING`, `DEGRADED`, `STALE`, `STOPPED`) to the service response using real last-finished timestamps.
- Verify production Redis lease behavior and multi-worker deployment.

## Files changed

- `hardik/backend/services/snmp_polling.py`
- `hardik/backend/services/realtime_monitor.py`
- `hardik/backend/main.py`
- `hardik/backend/api/overview_routes.py`
- `POLLING_RELIABILITY_OBSERVABILITY_REPORT.md`

## Safe to continue foundation

**YES**, after runtime verification of consecutive cycles and restart/failure behavior. Page-by-page verification is intentionally not started.

