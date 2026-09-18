# SNMP Health UTC Timestamp Fix

The confirmed root cause was reader-side timestamp interpretation. The SNMP scheduler writes `PollingHistory.created_at` through legacy timezone-naive DateTime storage, with application semantics representing UTC. `derive_device_health()` used the generic `_aware()` helper, which interprets naive values as Asia/Kolkata. Fresh scheduler successes therefore appeared approximately 5h30m old and were classified stale.

Added `_snmp_utc_aware()` and `_snmp_age()` in `device_health.py`. Naive SNMP timestamps are now interpreted as UTC; aware timestamps are converted to UTC. SNMP success-age calculations and latest-attempt/latest-success ordering use this helper. The generic `_aware()` semantics remain unchanged for other timestamp domains, including the existing ICMP-specific handling.

No PollingHistory writer, scheduler, Redis, MonitoringConfig, ICMP, Device.last_seen, database schema, historical data, frontend, or health threshold/rule behavior changed. This is a reader-only contract correction.

Focused tests cover fresh naive UTC, aware UTC, aware non-UTC conversion, and genuinely stale naive UTC. Python compile validation was run. Runtime verification remains pending.

ROOT CAUSE CONFIRMED: YES
POLLING HISTORY STORAGE SEMANTIC: Legacy naive DateTime values semantically representing UTC
OLD NAIVE INTERPRETATION: Asia/Kolkata
NEW NAIVE INTERPRETATION: UTC
GENERIC _aware GLOBAL SEMANTICS CHANGED: NO
SNMP FRESHNESS THRESHOLD CHANGED: NO
HEALTH CLASSIFICATION RULES CHANGED: NO
POLLING HISTORY WRITER CHANGED: NO
HISTORICAL DATA MODIFIED: NO
DATABASE SCHEMA CHANGED: NO
SCHEDULER CHANGED: NO
REDIS CHANGED: NO
ICMP CHANGED: NO
DEVICE LAST_SEEN CHANGED: NO
FRONTEND CHANGED: NO
FOCUSED TESTS: PASS
BACKEND COMPILE: PASS
RUNTIME VERIFICATION: PENDING
SAFE FOR REAL RUNTIME RETEST: YES
