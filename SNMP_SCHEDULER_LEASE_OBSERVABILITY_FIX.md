# SNMP Scheduler Lease Observability Fix

## Root cause

`app.state.scheduler_lease_owned` was correctly initialized and updated by the FastAPI lifespan and lease supervisor. However, `_get_service_states(request=None)`, which is used by `GET /api/v1/overview`, imported `backend.main.app` to read scheduler state but hardcoded `lease_owned` to false whenever no request object was supplied:

```python
bool(request is not None and getattr(request.app.state, "scheduler_lease_owned", False))
```

Thus Redis/supervisor ownership could be true while `/overview` reported false. The request-backed service endpoint already read the correct app state.

## Fix

The service-state helper now reads `scheduler_lease_owned` from the same authoritative `app.state` in both request and no-request paths. It does not query Redis, infer ownership from scheduler activity, or introduce another ownership algorithm. Shutdown explicitly marks the app state false before scheduler teardown.

Lease acquisition, renewal, reacquisition timing, scheduler startup/shutdown, job restoration, MonitoringConfig recovery, rescheduling, Redis semantics, and all polling behavior are unchanged.

Focused observability tests cover true ownership, false ownership, and the case where a running scheduler does not imply lease ownership. Existing lease, reschedule, and restart-recovery test sources remain unchanged. Python compile validation was run; pytest/runtime verification is pending because pytest is unavailable in this environment.

ROOT CAUSE: No-request overview path hardcoded lease ownership false even when `backend.main.app.state.scheduler_lease_owned` was true
AUTHORITATIVE OWNERSHIP STATE: FastAPI app state maintained by the SchedulerLease supervisor
FALSE LEASE REPORTING FIXED: YES
REDIS LEASE SEMANTICS CHANGED: NO
LEASE ACQUISITION CHANGED: NO
LEASE RENEWAL CHANGED: NO
LEASE REACQUISITION CHANGED: NO
SCHEDULER START/STOP CHANGED: NO
POLLING JOB LOGIC CHANGED: NO
MONITORING CONFIG LOGIC CHANGED: NO
COLLECTOR/OID LOGIC CHANGED: NO
DATABASE CHANGED: NO
FRONTEND CHANGED: NO
LEASE TESTS: PENDING
RESCHEDULE TESTS: PENDING
RESTART RECOVERY TESTS: PENDING
BACKEND COMPILE: PASS
RUNTIME VERIFICATION: PENDING
SAFE FOR REAL RUNTIME RETEST: YES
