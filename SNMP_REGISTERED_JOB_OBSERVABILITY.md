# SNMP Registered Job Observability

The existing `/overview` service-status path reads the live scheduler singleton from `app.state.snmp_polling.scheduler`. `registered_jobs` and `job_count` remain `len(scheduler.get_jobs())`.

Added read-only `registered_job_ids` and `registered_job_details`. Details are extracted directly from each live APScheduler job’s ID, `next_run_time`, and the existing safe positional arguments used by `_schedule_config()` (`device_id`, `module_name`, interval, and `config_id`). Entries are sorted by `job_id`. Job kwargs are not exposed.

No database query, scheduler mutation, lease operation, job creation/removal, rescheduling, or configuration update was added. Lease observability remains sourced from the authoritative app state. No secrets are returned.

Focused checks cover live job count/ID correspondence, deterministic ordering, safe metadata filtering, no scheduling mutation, and unchanged lease observability. Python compile validation was run. Runtime verification is pending.

OBSERVABILITY ONLY: YES
SCHEDULER BEHAVIOR CHANGED: NO
LEASE BEHAVIOR CHANGED: NO
MONITORING CONFIG CHANGED: NO
DATABASE CHANGED: NO
JOB IDS SOURCE: LIVE APSCHEDULER
REGISTERED JOB IDS EXPOSED: YES
REGISTERED JOB DETAILS EXPOSED: YES
SECRETS EXPOSED: NO
FOCUSED CHECKS: PASS
BACKEND COMPILE: PASS
RUNTIME VERIFICATION: PENDING
SAFE FOR REAL RUNTIME RETEST: YES
