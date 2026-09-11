# SNMP Step 2: Single-Flight Raw Cache Report

## Result

Implemented only the short-lived per-device raw SNMP result cache and single-flight optimization. API contracts, database schema, frontend, scheduler intervals/concurrency, collector output, SNMP protocol behavior, retries, timeouts, persistence, and alert integration are unchanged.

## Implementation

- Added `backend/snmp/raw_cache.py`, a process-local, thread-safe TTL cache with per-key single-flight coordination.
- The default TTL is 10 seconds and is configurable with `SNMP_RAW_CACHE_TTL_SECONDS`.
- Cache size is bounded at 2,048 completed entries and configurable with `SNMP_RAW_CACHE_MAX_ENTRIES`.
- Expired entries are removed during access; capacity eviction removes the entry nearest expiry.
- Only dictionary results returned successfully are cached. Exceptions, cancellations, timeouts, authentication/transport failures, and malformed non-dictionary results are not cached. Successful empty dictionaries remain cacheable, preserving empty-table behavior.
- Every stored and returned result is deep-copied, preventing one normalization/collector path from corrupting another caller's raw result.
- Waiting callers share the outcome of an in-flight request. Failed in-flight work is removed immediately, so a later call performs a new network operation.

## Key and isolation

The cache key contains:

- database `device_id`;
- target IP;
- SNMP port;
- normalized SNMP version;
- operation identity (`get` plus exact OID tuple, or `walk` plus normalized root);
- an HMAC-SHA256 credential fingerprint.

The fingerprint covers community, username, auth/privacy protocols and passwords, security level, version, and port. It is HMAC-keyed with a random process-local key, and plaintext credentials are neither stored in cache keys nor logged. Any covered credential change produces a different key. Calls without a stable `device_id` bypass the cache, which preserves discovery/ad-hoc behavior and prevents ambiguous device sharing.

## Integration

`SNMPPoller` supplies the scheduled job's device ID to `SNMPService`, which supplies it to `SNMPClient`. The cache wraps only the existing physical `get()` and `walk()` execution. The existing GET implementation, GETBULK loop, GETNEXT fallback, engine lifecycle, retry/timeout configuration, vendor detection, registry building, normalization, collectors, database writes, and scheduling remain on their prior code paths.

Debug-level events are emitted without key or credential content:

- `SNMP_CACHE_HIT`
- `SNMP_CACHE_MISS`
- `SNMP_SINGLEFLIGHT_WAIT`
- `SNMP_NETWORK_REQUEST`
- `SNMP_CACHE_EXPIRED`

## Verification and performance proof

Focused tests cover TTL reuse, simultaneous coalescing, expiry, device isolation, actual client credential/version fingerprint isolation, failure non-caching, successful empty results, deep-copy mutation safety, concurrent access, and bounded call-count proof.

The proof test invokes an identical physical operation twice without the cache and observes two calls; it then invokes the same device/operation key twice through the cache and observes one physical call. No synthetic timing or benchmark claim is made.

Test command:

```text
.venv/bin/pytest -q tests/test_snmp_raw_cache.py tests/test_snmp_bulk_walk.py tests/test_snmpv2c_preservation.py tests/test_snmp_port_configuration.py tests/test_snmp_poll_guard.py
```

Result at implementation time: cache/bulk-walk/port/poll-guard tests passed. Two existing v2c preservation tests could not initialize because PostgreSQL at localhost:5432 was unavailable (`sqlalchemy.exc.OperationalError`); they did not fail on SNMP behavior assertions. Python compilation and `git diff --check` passed.
