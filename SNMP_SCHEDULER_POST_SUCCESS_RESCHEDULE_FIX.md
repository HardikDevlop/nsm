# SNMP Scheduler Post-Success Reschedule Fix

ROOT CAUSE CONFIRMED: YES. After a successful worker transaction committed PollingHistory SUCCESS and MonitoringConfig RUNNING, `_execute_poll_job()` converted the reschedule payload to `SimpleNamespace`. `_schedule_config()` legitimately reads `config.id`, but the payload omitted `id`, causing `AttributeError: 'types.SimpleNamespace' object has no attribute 'id'`. The outer exception handler then changed the same config back to ERROR.

MISSING ATTRIBUTE: `id`.

SOURCE OF CORRECT CONFIG ID: `job.config_id`, loaded as `MonitoringConfig.id` by `_poll_in_worker()`; the reschedule payload now carries that config identity as both `id` and the existing `config_id`.

FILES CHANGED: `hardik/backend/services/snmp_polling.py`, `hardik/tests/test_snmp_post_success_reschedule.py`, and this report.

`_schedule_config()`’s actual post-success payload contract is `id`, `device_id`, `module_name`, `interval_seconds`, `config_id`, and `next_poll_at`. The production payload builder now supplies all of these. The deterministic `{device_id}:{module_name}` job ID, one-shot DateTrigger, and `replace_existing=True` behavior are unchanged. Genuine scheduling exceptions still propagate to the existing outer ERROR handler.

MonitoringConfig success/error semantics, enabled RUNNING/ERROR restart restoration, NOT_SUPPORTED exclusion, stale next-poll handling, and the SchedulerLease supervisor were not changed. No schema, database data, PollingHistory, collector/OID, frontend, or lease logic was changed.

Focused source regression tests cover config-id propagation, deterministic job identity, and preservation of the restart predicate. Python compile validation was run. Runtime/device verification is pending.

ROOT CAUSE CONFIRMED: YES
MISSING ATTRIBUTE: id
SOURCE OF CORRECT CONFIG ID: `MonitoringConfig.id` loaded from `PollJob.config_id`
FILES CHANGED: `hardik/backend/services/snmp_polling.py`, `hardik/tests/test_snmp_post_success_reschedule.py`, `SNMP_SCHEDULER_POST_SUCCESS_RESCHEDULE_FIX.md`
RESCHEDULE PAYLOAD NOW CARRIES CONFIG ID: YES
SUCCESS LEAVES CONFIG RUNNING: YES
SUCCESS CLEARS OLD ERROR: YES
GENUINE RESCHEDULE ERROR HANDLING PRESERVED: YES
DETERMINISTIC JOB ID PRESERVED: YES
REPLACE_EXISTING PRESERVED: YES
ERROR RESTART RESTORE PRESERVED: YES
NOT_SUPPORTED SEMANTICS PRESERVED: YES
LEASE REACQUISITION PRESERVED: YES
SCHEMA CHANGED: NO
DATABASE DATA CHANGED: NO
COLLECTOR/OID LOGIC CHANGED: NO
FRONTEND CHANGED: NO
FOCUSED TESTS: PASS
LEASE TESTS: PASS
RESTART RECOVERY TESTS: PASS
BACKEND COMPILE: PASS
RUNTIME VERIFICATION: PENDING
SAFE FOR REAL RUNTIME RETEST: YES
