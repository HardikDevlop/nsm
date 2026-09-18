# Device Health Remaining Semantics Audit

Read-only audit of the frozen scheduler/ICMP foundation. No code or database state was changed.

## ICMP failure evidence

Every failed `_ping_one()` increments in-memory failure counters and produces a `down` observation. After the configured consecutive-failure threshold, the in-memory device becomes `down`; `_persist_ping_result()` maps that to `Device.status = "offline"` and writes a `DeviceStatusHistory` row for a confirmed transition. A failed sample writes `DeviceMetric(packet_loss=100.0, latency=NULL)` when the transition path inserts immediately, or queues the same values in the steady-state batch path.

Failed pings do not update `Device.last_seen`. That field is intentionally the last successful reachability timestamp. It must not advance on failure, because advancing it would make an unreachable device appear to have fresh successful liveness evidence.

`DeviceMetric.created_at` is the durable latest-attempt timestamp for realtime ICMP samples, but `DeviceMetric` is shared: other production paths (`services/monitoring.py` and discovery code) also write it. It is therefore an existing possible attempt source, not an unambiguous ICMP-only source without additional provenance. `DeviceStatusHistory` records confirmed transitions, not every failed attempt, so it cannot represent every fresh failure by itself.

## Current ICMP health reader

`derive_device_health()` uses `Device.last_seen`, `Device.status`, and `Device.monitoring_status` for ICMP. It computes freshness from `Device.last_seen` using the minimum enabled MonitoringConfig interval, defaulting to 60 seconds, multiplied by `STALE_MULTIPLIER=3`. A fresh last_seen plus `Device.status=online` gives `reachable`; a fresh last_seen plus `offline` gives `unreachable`; otherwise enabled monitoring with a non-null old last_seen gives `stale`; missing evidence gives `unknown`.

It does not query `DeviceMetric` for ICMP freshness, does not inspect `packet_loss=100`, and does not inspect `DeviceStatusHistory` for recent failures. Therefore fresh failed ICMP attempts are currently ignored by the ICMP branch of health derivation.

## Device 293

The supplied facts are consistent with the current contract: realtime memory is DOWN, `Device.status=offline`, `Device.last_seen` is old, and a recent `DeviceMetric` has packet loss 100. Since health considers only old `last_seen` for ICMP freshness, it classifies ICMP as `stale`, not `unreachable`; the overall status becomes `stale` with the configured stale-evidence reason.

This is not fixed by advancing `last_seen` on failures. `last_seen` represents successful reachability and should remain old for device 293. The missing concept is a durable latest-attempt/latest-failure evidence source that health could use separately from last successful reachability.

## SNMP stale semantics for devices 283/284

For each enabled MonitoringConfig, health selects the latest `PollingHistory` row by `created_at DESC, id DESC`, and the latest successful row by the same order. It computes success freshness from `PollingHistory.created_at` against `config.interval_seconds * 3`. It uses config status and latest history status to classify SNMP as healthy, failed, stale, unsupported, or disabled.

`MonitoringConfig.last_poll_at`, `next_poll_at`, and `error_message` are returned/diagnostic fields but are not used as the primary SNMP success freshness timestamp. `last_success_at` in the returned health object is the latest successful `PollingHistory.created_at`; `last_attempt_at` is the latest history row timestamp.

The same naive/aware mismatch remains in this SNMP health path. Scheduler `now_utc()` produces aware UTC values, and `PollingHistory.created_at` is a legacy `DateTime` column without `timezone=True`; after persistence it can be a naive value semantically representing UTC. `derive_device_health._aware()` interprets every naive timestamp as Asia/Kolkata before converting it to UTC. Thus a fresh naive-UTC polling timestamp appears approximately 5h30m old, producing stale SNMP evidence. The same issue applies conceptually to naive `MonitoringConfig` timestamps, although those fields do not drive the success freshness test here.

The supplied fresh scheduler success timestamps therefore can coexist with reported SNMP stale: the source writer and health reader still disagree about naive timestamp semantics. No SNMP timestamp fix was made in this audit.

## Separation of root causes

ICMP root cause: health has no durable latest-attempt/latest-failure input and intentionally relies on last successful reachability, so fresh failed evidence is ignored. Device 293 consequently returns stale when last successful reachability is old.

SNMP root cause: `PollingHistory` freshness uses the general `_aware()` helper, which treats naive values as IST, while scheduler-written timestamps are semantically UTC. This creates the observed 5h30m stale age for otherwise fresh scheduler successes.

These are separate issues and should receive separate surgical fixes. The realtime ICMP process-memory UP/DOWN summary is not itself the derived-health authority.

## Existing sources and required evidence

`DeviceMetric` is the best existing candidate for latest ICMP attempt/failure evidence because realtime ICMP writes latency and packet loss, but it is shared with other monitoring/discovery writers and has no source column. It is therefore not proven safe as an ICMP-only authority. `DeviceStatusHistory` is durable for confirmed transitions but is not sufficient for every failed attempt and does not carry a per-ping attempt timestamp in the health contract.

No safe existing ICMP-only source is proven by the current schema. A future fix should preserve `last_seen` as last successful reachability and explicitly distinguish attempt/failure evidence rather than repurposing it.

SNMP and scheduler state are frozen and healthy; no scheduler, Redis, lease, or polling lifecycle issue was found in this audit.

DEVICE 293 REALTIME DOWN: YES
DEVICE 293 FRESH FAILED METRIC: YES
DEVICE 293 LAST_SEEN OLD: YES
LAST_SEEN SEMANTIC: Last successful ICMP reachability timestamp
HEALTH CURRENTLY USES FRESH ICMP FAILURE EVIDENCE: NO
WHY DEVICE 293 RETURNS STALE: ICMP freshness is computed only from old Device.last_seen; fresh DeviceMetric packet_loss=100 and realtime DOWN are ignored
SHOULD LAST_SEEN ADVANCE ON FAILED PING: NO
EXISTING DURABLE ICMP ATTEMPT SOURCE: DeviceMetric.created_at, but shared with monitoring/discovery writers
EXISTING DURABLE ICMP FAILURE SOURCE: DeviceMetric.packet_loss=100 plus DeviceStatusHistory for confirmed transitions; neither is an ICMP-only health input
SAFE EXISTING SOURCE FOR HEALTH: UNPROVEN

DEVICE 283/284 ICMP FRESH: YES
DEVICE 283/284 SNMP REPORTED STALE: YES
SNMP LAST_SUCCESS ACTUALLY FRESH: YES
SNMP HEALTH TIMESTAMP SEMANTICS CONSISTENT: NO
SNMP 5H30 OFFSET FOUND: YES
SNMP STALE ROOT CAUSE: Naive UTC PollingHistory timestamps are interpreted as Asia/Kolkata by derive_device_health._aware()

ICMP HEALTH ROOT CAUSE: No durable latest-attempt/failure evidence is consumed by ICMP health; health uses last successful reachability only
SNMP HEALTH ROOT CAUSE: Naive-UTC versus naive-IST interpretation mismatch in PollingHistory freshness

SCHEDULER CHANGED: NO
REDIS CHANGED: NO
ICMP PING IMPLEMENTATION CHANGED: NO
DATABASE CHANGED: NO
FRONTEND CHANGED: NO
CODE CHANGED: NO
SAFE FOR SURGICAL FIX: YES
