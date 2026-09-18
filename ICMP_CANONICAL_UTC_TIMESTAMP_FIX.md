# ICMP Canonical UTC Timestamp Fix

The runtime root cause was confirmed. Realtime ICMP wrote `Device.last_seen` using naive UTC, while the health reader interpreted every naive timestamp as Asia/Kolkata. Fresh evidence therefore appeared approximately 5h30m old. The second observed inconsistency came from transition `DeviceMetric` rows omitting `created_at`; the shared `DeviceMetric` default is the model’s naive IST helper, while steady-state batch rows carried an explicit timestamp from the ICMP writer.

New realtime ICMP timestamps now use the existing canonical `utc_now()` helper and are converted to naive UTC only at the legacy `DateTime` storage boundary. Both batched and transition-created `DeviceMetric` rows receive the same explicit canonical timestamp. The ICMP health reader uses a dedicated UTC interpretation for `Device.last_seen`; SNMP/PollingHistory timestamp interpretation remains unchanged. Historical rows are untouched.

The ping implementation, interval, executor, batching interval/size, transition semantics, Device.status meaning, freshness multiplier, SNMP, scheduler, Redis, frontend, schema, alerts, and events were not changed. Batching behavior remains the same; queued timestamps are explicit and the existing queue/commit retry behavior is preserved. The batch writer now advances `last_seen` only when a queued successful timestamp is not older than the durable value, preventing out-of-order completion from regressing fresh evidence. No new historical migration was performed.

Focused tests cover canonical timestamp generation, fresh naive-UTC health age, and preservation of old evidence age. Python compile validation was run. Host runtime verification remains pending.

ROOT CAUSE RUNTIME CONFIRMED: YES
DEVICE_LAST_SEEN ACTUALLY FRESH BEFORE FIX: YES
DEVICE_METRIC FUTURE TIMESTAMP CAUSE: Transition DeviceMetric inserts used the shared naive-IST model default because they omitted `created_at`; steady rows used explicit ICMP timestamps
CANONICAL ICMP TIME CONTRACT: UTC application semantics, stored as naive UTC at legacy DateTime boundaries
LAST_SEEN WRITER FIXED: YES
HEALTH READER ALIGNED: YES
DEVICE_METRIC TIMESTAMP FIXED: YES
5H30 ARTIFICIAL HEALTH AGE REMOVED: YES
HISTORICAL ROWS MODIFIED: NO
BATCHING BEHAVIOR PRESERVED: YES
OLDER BATCH CANNOT REGRESS LAST_SEEN: YES
PING IMPLEMENTATION CHANGED: NO
HEALTH CLASSIFICATION SEMANTICS CHANGED: NO
FRESHNESS THRESHOLD CHANGED: NO
SNMP/SCHEDULER CHANGED: NO
REDIS CHANGED: NO
DATABASE SCHEMA CHANGED: NO
FRONTEND CHANGED: NO
FOCUSED TESTS: PASS
BACKEND COMPILE: PASS
RUNTIME VERIFICATION: PENDING
SAFE FOR REAL RUNTIME RETEST: YES
