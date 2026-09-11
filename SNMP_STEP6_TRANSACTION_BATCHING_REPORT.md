# SNMP Step 6 Transaction Batching Report

## Result

Step 6 consolidates the normal successful scheduled SNMP poll from approximately three commits to one worker-owned transaction. No SNMP, cache, root concurrency, worker runtime, scheduler configuration, schema, API, frontend, or alert-rule behavior changed.

## Previous successful-poll call flow

1. `SNMPPoller.poll()` collected SNMP data, opened its replacement persistence session, and `_persist_results()` updated capability detail, latest rows, metric history, alerts, and polling history.
2. `_persist_results()` committed those writes.
3. `PollingScheduler._execute_poll_job()` used a second session to re-query the newest polling-history row and monitoring config, updated duration/status/timestamps, and committed.
4. `_schedule_config(config, db)` set the same next-poll timestamp and committed again before adding the next one-shot APScheduler job.

Alert helpers used `flush()` for generated IDs but did not commit. Interface persistence also used `flush()` after adding missing interface identities. Rollback existed in `_persist_results()`, but its exception was previously swallowed, allowing `poll()` to report success after persistence failure.

## New successful-poll call flow

The session owned by the polling worker now remains open after network collection:

```text
BEGIN
  capability detail
  latest metric rows
  metric history rows
  alert evaluation/creation/resolution
  polling history
  monitoring status, last_poll_at, next_poll_at
COMMIT
```

`SNMPPoller.poll(commit=False)` defers the final commit only for the scheduler-owned workflow. The default remains `commit=True`, preserving standalone/discovery caller compatibility. `_poll_in_worker()` then updates `MonitoringConfig` in the same replacement session and performs one commit. It returns detached scheduling values; `_execute_poll_job()` registers the next one-shot job without a database session or commit.

The redundant newest-polling-history query/update was removed. The already measured poll duration is written when `PollingHistory` is created.

## Flush and transaction behavior

- Existing alert flushes remain so alert IDs are available to incident/notification logic.
- Existing interface flush remains so newly created interface IDs are available to latest/history rows.
- No per-row flush or commit was added.
- Helpers still called independently use their default committing behavior.
- A persistence exception rolls back and is re-raised to `poll()`, which reports the poll failure.
- A final commit failure rolls back and propagates to scheduler error handling.
- Failed/unsupported early paths use a separate status transaction as needed; they are not falsely treated as a normal successful persistence transaction.
- Each `_poll_in_worker()` creates and owns its own SQLAlchemy sessions; sessions are not shared across concurrent workers and are closed by the owning worker.

## Deterministic proof

Mock-session transaction tests verify:

- normal successful poll: 1 commit, 0 rollbacks;
- final commit failure: 1 attempted commit, 1 rollback, exception propagated;
- required persistence-helper failure: 0 commits, 1 rollback, exception propagated;
- scheduling metadata is produced only after the successful commit.

Focused Step 6 plus Steps 2–5 regression tests: **40 passed, 0 failed**.

Broader non-database SNMP suite: **222 passed, 0 failed, 1 skipped**. The skipped test is the opt-in real-device integration test. Python compilation and `git diff --check` passed.

PostgreSQL is unavailable in the current environment, so live transaction/constraint verification is **RUNTIME VERIFICATION PENDING**. No live database result is claimed.

The next recommended optimization is to limit the interface previous-counter query to the latest history row per interface instead of loading all matching history.
