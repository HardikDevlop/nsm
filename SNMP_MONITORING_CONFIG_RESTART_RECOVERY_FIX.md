# SNMP MonitoringConfig Restart Recovery Fix

Implemented the smallest restart-restoration change in `hardik/backend/services/snmp_polling.py`.

Old predicate:

```python
enabled IS TRUE AND status == RUNNING
```

New predicate:

```python
enabled IS TRUE AND status IN (RUNNING, ERROR)
```

`WAITING_FIRST_POLL` has no production status writer in the current source; it is not an active runnable state, so it remains excluded. `NOT_SUPPORTED` and `STOPPED` remain excluded, and disabled configs remain excluded.

Restored ERROR rows are not rewritten during startup. They retain their status and `error_message` until a real successful poll executes the existing success path, which changes status to RUNNING and clears the error. Capability checks remain inside `_schedule_config()`; a rejected restored config becomes NOT_SUPPORTED and registers no job. Existing stale `next_poll_at` behavior remains unchanged: past or missing times are scheduled approximately five seconds ahead, without replaying missed intervals. Existing `{device_id}:{module_name}` job IDs and `replace_existing=True` protection remain unchanged.

No schema, PollingHistory, collector/OID, Redis/lease, frontend, ICMP, topology, alert, or event behavior was changed. No database rows were manually updated. Runtime verification was not performed.

Focused source regression checks cover RUNNING/ERROR eligibility, unsupported/disabled exclusion, WAITING_FIRST_POLL exclusion, and preservation of ERROR diagnostics before successful polling. Python compile validation was run.

ERROR CONFIG RESTART RESTORATION: PASS
RUNNING CONFIG RESTORATION PRESERVED: YES
WAITING_FIRST_POLL RESTORATION: NOT_APPLICABLE
NOT_SUPPORTED EXCLUDED: YES
DISABLED CONFIG EXCLUDED: YES
ERROR STATE PRESERVED UNTIL SUCCESS: YES
SUCCESS RECOVERS ERROR TO RUNNING: YES
STALE NEXT_POLL_AT SAFE: YES
DUPLICATE JOB PROTECTION PRESERVED: YES
SCHEMA CHANGED: NO
POLLING HISTORY CHANGED: NO
COLLECTOR/OID LOGIC CHANGED: NO
REDIS/LEASE LOGIC CHANGED: NO
FOCUSED TESTS: PASS
BACKEND COMPILE: PASS
