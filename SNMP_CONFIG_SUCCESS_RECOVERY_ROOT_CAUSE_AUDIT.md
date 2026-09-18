# SNMP Config Success-Recovery Root-Cause Audit

Read-only source audit based on the supplied runtime facts. No code, database, scheduler, Redis, collector, or frontend state was changed.

## Scheduler execution path

The restored APScheduler job is keyed by `{device_id}:{module_name}` and invokes `PollingScheduler._execute_poll_job()`.

`_execute_poll_job()` builds a `PollJob`, runs `_poll_in_worker()` in a thread, extracts `_reschedule`, calls `_schedule_config()` for the next one-shot trigger, and records process-local job timestamps.

`_poll_in_worker()` creates a worker-owned SQLAlchemy session and `SNMPPoller`. It calls `poller.poll(job, commit=False)`. The poll method performs collection, opens a replacement `SessionLocal()` after the network round trip, and calls `_persist_results()`.

`_persist_results()` writes latest/history data and calls `_persist_history()`, which inserts:

```python
PollingHistory(
    device_id=device_id,
    collector=module,
    status="success" if supported else "not_supported",
    ...,
)
```

With `commit=False`, that history insert is pending in `poller.db`. `_poll_in_worker()` then chooses that same session as `transaction_db`, reloads `MonitoringConfig` by `MonitoringConfig.id == job.config_id`, updates the config, and commits the transaction. On a successful result it executes:

```python
config.last_poll_at = now_utc()
config.status = MonitoringStatus.RUNNING.value
config.error_message = None
config.next_poll_at = now_utc() + timedelta(seconds=config.interval_seconds)
transaction_db.commit()
```

Only after that commit does `_execute_poll_job()` call `_schedule_config()` for the next job. The reschedule uses the same `{device_id}:{module_name}` key and `replace_existing=True`.

## Where SUCCESS history can originate

There are two materially different production paths:

1. Scheduler path: `poll()` → `_persist_results(commit=False)` → `_persist_history()` → same worker session reloads config by `config_id` → config update and history commit together.
2. Live/API or discovery path: `snmp_device_routes._persist_collect_result()` creates an `SNMPPoller` and calls `_persist_results()` with the default `commit=True` for each collector. This writes a successful `PollingHistory` row, but `_persist_results()` itself does not load or update `MonitoringConfig.status`.

Therefore a successful `PollingHistory` row is not by itself proof that the scheduler’s config-recovery update ran. The live endpoint can commit history independently of config status.

## Transaction and lookup findings

The scheduler success path looks up the exact `MonitoringConfig` using `job.config_id`, not by a loose device/module query. The config ID is captured when the job is registered from the config row. `device_id` and `module_name` are carried in the `PollJob`; `_persist_results()` uses them for collector persistence and history, while the status update uses the config primary key.

The scheduler’s deferred-commit path uses the same replacement `poller.db` session for history/latest writes and the config reload/update, then commits once. If persistence or config update fails before commit, `_poll_in_worker()` rolls back and the success history should not be committed from that transaction. If an exception occurs after this commit, the outer `_execute_poll_job()` handler opens a separate session and can write the same config back to ERROR.

The live/API path uses its own session and commit, and has no corresponding config status update. There is no evidence in source of a detached config object causing the scheduler success update to be skipped.

## Post-success exception hypothesis

This hypothesis is possible in source, but not proven from the supplied facts. After the config/history commit, `_execute_poll_job()` calls `_schedule_config()` with a `SimpleNamespace` and no DB session. That path still calculates the next trigger and calls APScheduler `add_job()`. If it raises, control enters `_execute_poll_job()`’s exception handler, which opens another session, sets the config to ERROR, stores the exception, advances `next_poll_at`, commits, and attempts scheduling again.

Thus a successful history/config commit followed by a post-commit scheduling exception can produce the observed combination of SUCCESS history and ERROR config. The relevant log to confirm it is `Poll job <device>:<module> failed: <exception>` after the success timestamp, plus APScheduler scheduling errors. No source evidence alone proves that this occurred.

## Multiple collector operations

The normal scheduler job is one module per `MonitoringConfig` and one `PollingHistory` insert per execution. It does not run all eight device-283 modules in one scheduler execution. A full `SNMPService.collect_domain()` call performs identity and the selected domain collection, then returns one module result.

The discovery/live aggregate path can process multiple collector payloads and call `_persist_collect_result()` for each. Those successful history rows can therefore appear for many modules without changing their MonitoringConfig rows. This is another reason the history sequence must be mapped to the scheduler job/config ID and request path before concluding recovery failed.

## Identity mapping

The authoritative mapping is:

```text
MonitoringConfig.id  <- APScheduler job argument config_id
MonitoringConfig.device_id + module_name
PollingHistory.device_id + collector
```

For scheduler-generated history, `collector == PollJob.module_name`. For API/discovery-generated history, `collector` also receives the module name, but no config update is performed. Comparing only device 283 and a successful collector name is insufficient; compare the config ID/job execution and timestamps.

The observed 23 ERROR and 2 NOT_SUPPORTED rows may include configs whose corresponding success history came from live/API persistence, configs whose scheduler success commit was followed by a post-success exception, or configs whose history belongs to a different execution source. The supplied facts do not establish which one.

## Later status writers and race ordering

All production `MonitoringConfig.status` assignments found are:

- `_schedule_config()`: `NOT_SUPPORTED` when capability map rejects a module.
- `_poll_in_worker()`: `RUNNING` on success, `NOT_SUPPORTED` for explicit unsupported result, `ERROR` for other unsuccessful results.
- `_execute_poll_job()` exception handler: `ERROR` after any exception escaping the worker/reschedule path.
- `add_job()`: creates or explicitly recovers a config to `RUNNING`.
- `stop_job()`: explicitly sets disabled configs to `STOPPED`.

The key ordering possibility is `_poll_in_worker()` commits SUCCESS + RUNNING, then `_schedule_config()` or another post-success operation raises, and `_execute_poll_job()` commits ERROR afterward. A concurrent explicit stop/start or another scheduler/API operation could also overwrite status, but the source does not prove such a race. There is no later unconditional ERROR writer after a successfully completed `_execute_poll_job()` except the outer exception handler.

## What is proven vs unproven

Proven: the ERROR→RUNNING code path exists; scheduler success history and config update share a transaction in the normal deferred-commit path; live/API history writes can occur without config recovery; and post-commit exceptions can write ERROR.

Unproven: whether the supplied successful rows were produced by scheduler jobs, whether the exact config IDs were found and updated, whether those updates committed, and whether a later exception overwrote them. Those questions require correlated host-side DB/log evidence.

Use this single read-only PostgreSQL command on the real host, replacing `283` if needed:

```bash
psql "$DATABASE_URL" -x -c "SELECT c.id AS config_id,c.device_id,c.module_name,c.status,c.error_message,c.last_poll_at,c.next_poll_at,h.status AS history_status,h.created_at AS history_created_at,h.error AS history_error FROM monitoring_configs c LEFT JOIN LATERAL (SELECT ph.status,ph.created_at,ph.error FROM polling_history ph WHERE ph.device_id=c.device_id AND ph.collector=c.module_name ORDER BY ph.created_at DESC,ph.id DESC LIMIT 1) h ON TRUE WHERE c.device_id=283 ORDER BY c.id;"
```

Correlate the result with backend logs containing `Poll job 283:<module> failed`, `Loaded ... polling jobs`, and scheduler execution timestamps. A latest history SUCCESS with no matching scheduler failure log may still be API-originated; the query alone identifies the same device/module but not the writer path.

## Conclusion

The most likely source-level explanation is an observability/provenance mismatch: successful history rows are being treated as proof of scheduler config recovery, although API/discovery persistence also creates those rows without updating MonitoringConfig. A second plausible mechanism is a post-commit scheduling exception that causes the outer handler to write ERROR again. The current source audit cannot distinguish these without host logs and correlated latest rows. No fix was implemented.

POLLING HISTORY SUCCESS CONFIRMED FROM RUNTIME: YES
CONFIG ERROR->RUNNING CODE PATH EXISTS: YES
SUCCESS PATH ACTUALLY UPDATES SAME CONFIG: UNPROVEN
SUCCESS UPDATE COMMITTED: UNPROVEN
SUCCESS LATER OVERWRITTEN TO ERROR: UNPROVEN
POST-SUCCESS EXCEPTION CAN SET ERROR: YES
MODULE IDENTITY MISMATCH FOUND: NO
TRANSACTION/SESSION ISSUE FOUND: NO
CONCURRENCY/RACE FOUND: NO
OBSERVABILITY ISSUE FOUND: YES
PRIMARY ROOT CAUSE: Successful PollingHistory rows do not uniquely prove scheduler execution; live/API persistence writes SUCCESS without updating MonitoringConfig
SECONDARY ROOT CAUSES: Post-commit rescheduling exception can overwrite a committed RUNNING state to ERROR; possible unverified concurrent writer
LIVE DB COMMAND REQUIRED: YES
CODE CHANGED: NO
DB CHANGED: NO
SAFE FOR FIX IMPLEMENTATION: YES
