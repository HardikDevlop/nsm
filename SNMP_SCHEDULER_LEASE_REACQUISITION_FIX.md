# SNMP Scheduler Lease Reacquisition Fix

The previous lifecycle attempted `SchedulerLease.acquire()` once during FastAPI lifespan. If another backend still held the 30-second Redis lease, the new process stored `lease_owned=False`, did not create a scheduler, and did not start the renewal task. When the old lease expired, the new process never retried.

The lifecycle now starts one process-local async supervisor task regardless of initial acquisition. A non-owner retries acquisition every `max(1, lease.ttl // 3)` seconds. On success it sets `app.state.scheduler_lease_owned=True` and obtains the existing process-global scheduler through `get_polling_scheduler()`, which preserves singleton startup and existing MonitoringConfig RUNNING/ERROR restoration. Repeated successful iterations do not create another scheduler.

An owner renews at the same bounded interval. If renewal fails, ownership is marked false, the app state scheduler reference is cleared, and the existing singleton scheduler is shut down so the process does not continue polling without leadership. The supervisor remains alive and can reacquire later. Temporary Redis failures therefore leave the backend alive and retrying.

Shutdown cancels the single supervisor, shuts down the existing scheduler singleton, and invokes the existing token-checked `SchedulerLease.release()`. Release never blindly deletes another process’s lease. No Redis lease semantics, scheduler implementation, MonitoringConfig predicate, collectors, database schema/data, frontend, ICMP, topology, or alerts/events were changed.

Focused tests cover delayed reacquisition, single scheduler startup, lease-loss shutdown, and truthful app ownership state. Python compile validation was run. Real Redis/systemd/device runtime verification remains pending.

INITIAL LEASE ACQUISITION PRESERVED: YES
FAILED INITIAL ACQUIRE RETRIED: YES
