# ICMP Health Failure Freshness Implementation

Implemented the approved minimal durable ICMP evidence design.

Added nullable `devices.last_icmp_attempt_at` and `devices.last_icmp_status` fields with an additive, idempotent custom migration. No values are backfilled. Realtime ICMP now records every completed attempt as reachable/unreachable, while preserving `Device.last_seen` as last successful reachability only. Both immediate and batched paths use monotonic timestamp protection; batching cadence is unchanged.

Health derivation uses dedicated attempt evidence when present and falls back to legacy `Device.last_seen` behavior for pre-migration devices. Fresh failed evidence with offline Device status derives unreachable and overall offline; old attempts derive stale. DeviceMetric, status history, ping behavior, scheduler, SNMP, Redis, and frontend contracts are preserved.

Focused source checks and backend compile validation passed. Runtime verification is pending.

FIELDS ADDED: `Device.last_icmp_attempt_at`, `Device.last_icmp_status`
MIGRATION IDEMPOTENT: YES
HISTORICAL DATA BACKFILLED: NO
LAST_SEEN SEMANTICS CHANGED: NO
FAILED PING UPDATES LAST_SEEN: NO
SUCCESSFUL PING UPDATES LAST_SEEN: YES

EVERY REALTIME ATTEMPT PERSISTED: YES
ATTEMPT RESULT PERSISTED: YES
OLDER SAMPLE CAN REGRESS ATTEMPT: NO

HEALTH USES DEDICATED ATTEMPT: YES
LEGACY FALLBACK PRESERVED: YES

FRESH SUCCESS => REACHABLE: YES
FRESH FAILURE => UNREACHABLE: YES
OLD ATTEMPT => STALE: YES
DEVICE 293 EXPECTED => OFFLINE: YES

PING IMPLEMENTATION CHANGED: NO
BATCHING CADENCE CHANGED: NO
DEVICE METRIC CONTRACT CHANGED: NO
STATUS HISTORY CONTRACT CHANGED: NO

SNMP CHANGED: NO
SCHEDULER CHANGED: NO
REDIS CHANGED: NO
FRONTEND CHANGED: NO

FOCUSED TESTS: PASS
BACKEND COMPILE: PASS
RUNTIME VERIFICATION: PENDING
SAFE FOR REAL RUNTIME RETEST: YES
