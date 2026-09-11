# SNMP Step 2 Regression Verification

## Verdict

**FAIL.** Static inspection shows that Step 2 is narrowly placed around physical SNMP calls and does not alter protocol, scheduler, collector, normalization, persistence, alert, or API logic. However, the existing non-database SNMP regression suite exposes a compatibility regression: `SNMPService.__init__()` now unconditionally passes `device_id=` to the `SNMPClient` constructor, including when it is `None`. Existing client-compatible factories/test doubles using the previous constructor signature consequently raise `TypeError`. No implementation code was changed during this verification.

## Diff verification

The Step 2 implementation changes are limited to:

- two cache configuration settings;
- a dedicated raw cache/single-flight helper;
- an optional `device_id` constructor argument in `SNMPClient` and `SNMPService`;
- wrapping the existing physical GET and WALK execution in `_cached()`;
- passing the scheduled job device ID from `SNMPPoller` to `SNMPService`;
- focused cache tests and the Step 2 report.

The following paths have no Step 2 logic changes:

- SNMP v2c `CommunityData` construction;
- SNMP v3 `UsmUserData` construction and protocol selection;
- GET request construction and response formatting;
- GETBULK loop, 25-row batching, subtree termination, and 2,000-row cap;
- GETNEXT fallback after GETBULK error;
- request timeout, retry count, operation deadline, and cancellation handling;
- scheduler intervals, APScheduler configuration, worker count, and semaphore;
- collector implementations and collector outputs;
- normalization and OID registry logic;
- latest/history persistence, polling history, transaction behavior, and models;
- threshold/alert/notification integration;
- API routes and response construction.

The cache is an optimization wrapper around the existing `_run_in_thread()` physical GET/WALK operations. A cache miss calls the previous network path. A cache hit returns a deep copy without changing downstream normalization or collection.

## Cache isolation and behavior

Cache key inspection and focused tests confirm isolation by:

- stable database device ID;
- target IP;
- SNMP port;
- normalized SNMP version;
- exact GET OID tuple or normalized WALK root;
- HMAC-SHA256 fingerprint covering credential configuration, including community, username, auth/privacy protocols and secrets, security level, version, and port.

Calls without a stable `device_id` bypass the cache and directly execute the physical request. Different devices, credentials, versions, ports, GET OID tuples, and WALK roots cannot share a key.

Only successful dictionary results are stored. Exceptions, timeouts, cancellations, transport/authentication errors, and malformed non-dictionary results are not entered into the completed cache. Concurrent waiters receive the in-flight failure, while later calls create a new request. Successful empty dictionaries are cached and returned as empty dictionaries, preserving previous semantics.

## Concurrency review

- Duplicate in-flight requests: prevented by a lock-protected per-key `_Flight` and `Event`.
- Deadlock: no lock is held while physical SNMP work or waiter result processing runs. No deadlock was observed in concurrent focused tests. A recursively re-entered request for its own identical key would self-wait, but the current SNMP call graph does not recurse.
- Stale flight: the flight is removed and its event signaled in `finally` on success, ordinary exceptions, cancellation, and other `BaseException` paths.
- Cache growth: completed entries are bounded by `snmp_raw_cache_max_entries` (default 2,048); expired entries are purged on access. In-flight entries are bounded operationally by current scheduler/executor concurrency, rather than retained after completion.
- Expiry race: entry lookup/purge/insertion is protected by one mutex and monotonic time.
- Exception propagation: waiting callers receive the owner exception; failed results are not subsequently cached. Focused failure tests pass.
- Result mutation: completed results and returns are deep-copied. Mutation-isolation tests pass.

## Runtime tests

### Full non-PostgreSQL attempt

The selected non-PostgreSQL suite collected 205 tests. It reached 171 passing tests (through 83%) before hanging in the pre-existing `tests/test_snmp_poll_worker.py::test_poll_worker_keeps_blocking_persistence_off_loop_and_closes_sessions`; the command was terminated by its explicit 180-second timeout. That hang produced no assertion result and is reported as incomplete, not passed.

### Reproducible regression subset

Command:

```text
.venv/bin/pytest -q tests/test_snmp_regression_matrix.py tests/test_snmpv3_timeout_exploration.py tests/test_snmp_endpoint_optimization.py tests/test_snmp_raw_cache.py
```

Result: **23 passed, 10 failed**. All 10 failures are caused by the same Step 2 constructor-compatibility issue:

```text
TypeError: ...make_agent() got an unexpected keyword argument 'device_id'
```

Nine parameterized domain-dispatch cases and one full-poll orchestration case fail in `tests/test_snmp_regression_matrix.py` when its previous-signature `SNMPClient` factory is installed.

### Focused transport/cache subset

The focused cache, bulk-walk/fallback, port, and poll-guard run completed with **15 passed, 0 failed**. This verifies cache semantics, concurrency, GETBULK behavior, GETNEXT fallback, configured port behavior, and poll guarding in that subset.

### PostgreSQL-dependent tests

The two concrete tests in `tests/test_snmpv2c_preservation.py` could not initialize because PostgreSQL at `localhost:5432` was inaccessible (`sqlalchemy.exc.OperationalError`). Per verification requirements they are marked **RUNTIME VERIFICATION PENDING**, not failed.

The optional real-device integration test was not enabled, so no live-agent result is claimed.

## Regression found

1. `backend/snmp/collector.py:SNMPService.__init__()` unconditionally forwards `device_id=device_id` to `SNMPClient`, changing compatibility with factories, substitutes, and test doubles that implement the prior constructor signature. This is directly demonstrated by 10 non-database test failures. The production `SNMPClient` accepts the new argument, so this does not prove an on-device v2c/v3 protocol failure; it does prove Step 2 has not met the no-functional-regression test gate.

Step 3 should not start until this compatibility regression is corrected and the non-database suite completes successfully.
