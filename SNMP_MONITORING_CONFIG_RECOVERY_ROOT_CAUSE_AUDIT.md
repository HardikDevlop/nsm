# SNMP MonitoringConfig Recovery Root-Cause Audit

Read-only source audit based on the supplied runtime facts. No code, database rows, statuses, Redis state, or polling state were changed.

## Model and statuses

`backend/models/snmp.py:MonitoringConfig` is a per-device/per-module unique configuration. Its status values are:

- `stopped`
- `running`
- `waiting_first_poll`
- `not_supported`
- `error`

The column default is `stopped`. `enabled` is the configuration intent flag and defaults to false. `interval_seconds` defaults to 60. `next_poll_at`, `last_poll_at`, `last_started_at`, and `last_stopped_at` are nullable timestamps. `error_message` is the only stored error detail; there is no persisted failure count or retry count on this model. The unique key is `(device_id, module_name)`.

## Every production status writer found

### Successful or unsupported result completion

`backend/services/snmp_polling.py:PollingScheduler._poll_in_worker()` loads the config after a poll and always sets `last_poll_at` and `next_poll_at`.

- `result.success` true: sets status to `running`, clears `error_message`.
- `result.not_supported` true: sets status to `not_supported`.
- Any other unsuccessful result: sets status to `error` and stores the result error.
- Commits in the same transaction.
- If enabled and not `not_supported`, builds a reschedule payload. Thus an ERROR result remains eligible for an in-memory next job.

### Worker exception path

`PollingScheduler._execute_poll_job()` catches exceptions from the worker, sets `last_job_failure_at`, increments the process-local failure count, then loads the config and sets status to `error`, stores `str(exc)`, advances `next_poll_at` by the configured interval, commits, and calls `_schedule_config(config)` when enabled. This is also a one-failure transition and reschedules in the same process.

### Capability rejection during scheduling

`PollingScheduler._schedule_config()` checks `DeviceCapabilities`. If the module is absent/false in the capability map, it sets status to `not_supported`, commits when a DB session was supplied, and returns without registering a job.

### Explicit start/add

`PollingScheduler.add_job()` creates a missing config with `enabled=True`, `status=running`, and `last_started_at`, or updates an existing config to `enabled=True`, `status=running`, updates interval/start time, and clears `error_message`. It commits and then schedules the config. This is the normal explicit recovery path for ERROR rows.

### Explicit stop

`PollingScheduler.stop_job()` removes the in-memory job, sets `enabled=False`, status `stopped`, records `last_stopped_at`, clears `next_poll_at`, and commits.

### Interval update

`update_job_interval()` changes only the interval and commits. It reschedules only when `enabled=True` and status is already `running`; it does not recover ERROR rows.

No other production `MonitoringConfig.status` assignment was found in the audited backend source. Reads in `device_health.py`, overview, monitoring data, and SNMP device routes do not write status.

## Normal scheduled lifecycle

The startup restore query is `enabled=True AND status=running`. Each row is scheduled as `{device_id}:{module_name}`. The job executes `_poll_in_worker()`, persists collector results, updates the config, commits, and constructs a reschedule payload. `_execute_poll_job()` then calls `_schedule_config(SimpleNamespace(**reschedule))`, which replaces the one-shot DateTrigger with the next one.

After SUCCESS, status is explicitly restored/kept as `running`, `error_message` is cleared, `last_poll_at` is updated, and `next_poll_at` is advanced. The job continues.

## Failure lifecycle and restart behavior

A single unsuccessful result or worker exception is enough to set `error`; there is no threshold or retry counter before that transition. `next_poll_at` still advances by `interval_seconds`. If the config remains enabled, the existing process schedules the next run even though the DB status is now ERROR. On the next successful result, the same-process job sets the status back to RUNNING.

After process restart, `_load_jobs_from_db()` ignores ERROR rows because it requires status RUNNING. Therefore the source confirms this failure mode:

```text
RUNNING config
→ one failure
→ DB status ERROR
→ next job remains scheduled in current process
→ backend restarts
→ restore query ignores ERROR
→ polling disappears permanently until explicit start/add recovery
```

ERROR is consequently being used as both a last poll outcome and a restore eligibility gate, rather than solely as a diagnostic state. This is the orphaning defect.

## NOT_SUPPORTED behavior

`not_supported` is assigned when capability detection says a module is unavailable during `_schedule_config()`, and when a poll returns `not_supported`. Such configs are not rescheduled by `_poll_in_worker()` and are excluded by the restart query because they are not RUNNING. This exclusion is appropriate for genuinely unsupported modules. The source shows no automatic capability re-probe that changes NOT_SUPPORTED back to RUNNING; explicit `add_job()`/monitoring start can set RUNNING, after which capability checking may mark it unsupported again. A capability refresh/discovery flow is the apparent reactivation mechanism, not ordinary polling.

## Stale `next_poll_at`

For an eligible RUNNING config, `_schedule_config()` takes `config.next_poll_at` or `now_utc()`. If the timestamp is in the past, it replaces it with `now_utc() + 5 seconds`, commits it, and schedules the job. Therefore a stale eligible row runs shortly after restore; it is not rejected. This behavior is never reached for the current ERROR rows because status filtering excludes them first.

## Bulk reset assessment

Changing all 24 ERROR rows to RUNNING would be unsafe. It could schedule unreachable devices, missing-credential configs, deleted/cascaded device references, unsupported modules, stale configurations, or duplicate jobs if performed while a scheduler is already active. Capability checks may convert individual rows to NOT_SUPPORTED, but that is not a substitute for validating device/configuration eligibility. No reset was performed.

## Related state meanings

- `MonitoringConfig.status`: lifecycle/configuration state, but currently also overwritten with the latest poll outcome.
- `PollingHistory.status`: per-attempt outcome (`success`, timeout, authentication failure, unreachable, unsupported, error, no-data); it is historical and does not itself schedule jobs.
- Derived device health: combines enabled configs, latest history, freshness, and config status to produce SNMP health and overall device health. ERROR status can force SNMP failed/degraded even if other current evidence exists.
- Scheduler job state: in-memory APScheduler registration/execution state. It can continue while the DB config is ERROR in the same process, or disappear after restart because restore filters ERROR.

These are distinct sources and should not be treated as interchangeable.

## Root cause and safe direction

The primary root cause is that one transient poll failure writes `MonitoringConfig.status=ERROR`, while restart restoration accepts only RUNNING. The same-process reschedule masks the defect until restart; after restart, enabled ERROR rows are permanently skipped. Secondary causes are no failure threshold, no persisted retry/recovery state separate from lifecycle state, no automatic ERROR restoration, and the absence of an automatic capability re-probe for NOT_SUPPORTED.

The safe minimal fix is to separate eligibility from last outcome: keep enabled eligible configurations restorable/retryable while retaining the error detail separately, while continuing to exclude explicitly stopped and genuinely unsupported configurations. The exact status/schema compatibility approach requires implementation planning; no fix was made in this audit.

MONITORING CONFIG STATUS PURPOSE: Intended lifecycle/configuration state, currently conflated with latest poll outcome
ERROR REPRESENTS LIFECYCLE OR LAST OUTCOME: Last outcome in the current implementation
ONE TRANSIENT FAILURE CAN SET ERROR: YES
ERROR CONFIG RESCHEDULES IN SAME PROCESS: YES
ERROR CONFIG RESTORED AFTER RESTART: NO
ERROR CAN AUTO-RECOVER AFTER RESTART: NO
RUNNING-ONLY RESTORE CREATES ORPHAN RISK: YES
NOT_SUPPORTED SHOULD AUTO-POLL: NO
STALE NEXT_POLL_AT BEHAVIOR: Eligible RUNNING rows are moved to approximately now + 5 seconds and scheduled
24 ERROR ROWS SAFE TO BULK RESET: NO
PRIMARY ROOT CAUSE: ERROR status is excluded by the restart restore query even though enabled ERROR configs are rescheduled during the current process
SECONDARY ROOT CAUSES: Single-failure ERROR transition, no retry threshold, no automatic ERROR recovery, and no automatic NOT_SUPPORTED re-probe
SAFE MINIMAL FIX: Preserve enabled eligible configs as restart-restorable while separating last outcome/error detail from lifecycle eligibility
CODE CHANGED: NO
DB CHANGED: NO
SAFE FOR FIX IMPLEMENTATION: YES
