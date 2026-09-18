# ICMP Health Failure Freshness Design

Design/source audit only. No code, database, schema, or frontend changes were made.

## DeviceMetric writers

The production writers found are:

1. `backend/services/realtime_monitor.py:MonitorEngine._persist_ping_result()` and `_flush_metric_batch()` write realtime ICMP samples with `latency` and `packet_loss` (`0.0` for success, `100.0` for failure), plus explicit canonical timestamp values. These are the intended realtime ICMP rows.
2. `backend/services/monitoring.py:run_monitoring_check()` performs a separate synchronous ICMP check and writes latency/packet loss with the same general pattern. It also updates status and last successful reachability.
3. `backend/api/discovery_routes.py` writes `DeviceMetric` for discovery/device-add aggregate CPU, memory, and temperature data; these rows generally do not carry ICMP latency/packet loss.

`DeviceMetric` has no source, collector, probe-type, or result-origin column. A row with non-null packet loss and ICMP-shaped latency is strong evidence of an ICMP-style check, but it is not formally ICMP-only because `run_monitoring_check()` is another writer and the model cannot prove which writer produced a row. The tuple is therefore not an unambiguous durable authority for derived health.

`DeviceMetric.created_at` is a legacy naive DateTime with a model default from the shared model helper. Realtime ICMP now supplies its own canonical UTC-naive timestamp explicitly; a future dedicated field should use the same ICMP writer contract.

## Existing Device fields

`Device` has `last_seen`, `status`, `monitoring_status`, and `last_status_change`, but no `last_check`, `last_attempt`, `last_failure`, or monitoring-updated timestamp. `last_seen` is already intentionally the last successful reachability timestamp and must not be repurposed. `last_status_change` records only a confirmed online/offline transition, not every probe attempt.

## DeviceStatusHistory

`DeviceStatusHistory` stores `device_id`, `old_status`, `new_status`, `change_reason`, and `timestamp`. Realtime ICMP writes it only when the stable state transitions; repeated failures while already offline do not create rows. It can prove when the device entered offline, but cannot prove that it continued to be checked or remained offline on each subsequent attempt. It is insufficient for continuous failure freshness.

## Current health semantics

The current ICMP derivation uses `monitoring_status`, `last_seen`, and `Device.status`. It does not read `DeviceMetric` or `DeviceStatusHistory` for freshness. Consequently:

- recent successful evidence plus `status=online` → reachable/online;
- recent successful evidence plus `status=offline` → unreachable/offline;
- old successful evidence with monitoring enabled → stale;
- no successful evidence → unknown or existing stale/unknown branch depending on available state.

Fresh failed attempts are not consumed. Device 293 is therefore stale because its last successful reachability is hours old, even though a fresh shared metric has packet loss 100 and the realtime process says DOWN. Advancing `last_seen` on failure would be semantically wrong and would make failed monitoring look like successful reachability.

## Minimum safe source decision

Option A, reusing an existing unambiguous attempt field, is unavailable. Option B, using `DeviceMetric`, is not formally safe because the table is shared and has no source discriminator. Option B can be useful as corroborating evidence, but it should not become the sole health authority without a provenance guarantee.

Option C is the smallest semantically correct design: add dedicated durable ICMP evidence fields, for example:

```text
last_icmp_attempt_at  DateTime nullable
last_icmp_status      String nullable   # reachable | unreachable
```

`last_icmp_attempt_at` is the timestamp of every completed realtime ICMP attempt, stored using the established canonical UTC-naive legacy-column boundary. `last_icmp_status` records the result of that same attempt. A separate `last_icmp_success_at` is optional because `Device.last_seen` already supplies last successful reachability, but adding it could make the contract explicit; it is not required for the minimum design.

The fields should be written by the realtime ICMP persistence path for both success and failure, in the same transaction as the corresponding metric/state persistence. If steady samples remain batched, the queued item must carry attempt timestamp and result, and the existing monotonic protection must prevent an older queued attempt from regressing the durable attempt timestamp. Transition writes remain immediate as today. The fields are durable across restart and safe with multiple workers because the database transaction plus timestamp ordering is authoritative.

This requires a schema migration and a narrow health-reader/writer change. It does not require changing ping implementation, intervals, batching cadence, scheduler, SNMP, or frontend presentation. The API can continue returning the existing health contract; only its persisted evidence source changes.

## Proposed future rules

- Reachable: monitoring enabled, a recent `last_icmp_attempt_at` within the existing freshness window, `last_icmp_status=reachable`, and the existing persisted status is online.
- Unreachable: monitoring enabled, a recent `last_icmp_attempt_at` within the existing freshness window, `last_icmp_status=unreachable`, and `Device.status=offline`.
- Stale: monitoring enabled, no recent attempt, but historical ICMP evidence exists (including old last success or old attempt).
- Unknown: no ICMP evidence exists, or monitoring is not enabled according to the existing contract.

The existing overall precedence should be preserved until a separate implementation task explicitly decides how fresh ICMP failure interacts with SNMP degraded/unsupported/disabled states. For device 293, with a fresh failed attempt, offline status, old last success, and SNMP disabled, the expected future ICMP result is unreachable/offline—not stale.

## Scope and risks

No existing DeviceMetric source can be safely promoted to an authoritative ICMP attempt field without provenance. Reusing `DeviceStatusHistory` would incorrectly leave persistent failures stale after the transition ages. The dedicated fields are the minimum reliable source, but require schema expansion and a migration; no migration should rewrite historical data. The future implementation must preserve last_seen semantics and monotonic batching.

LAST_SEEN MEANS LAST SUCCESSFUL REACHABILITY: YES
FAILED PING SHOULD UPDATE LAST_SEEN: NO

DEVICE_METRIC WRITERS FOUND: `realtime_monitor.py` realtime ICMP, `services/monitoring.py` synchronous ICMP checks, `discovery_routes.py` discovery/device-add metrics
DEVICE_METRIC ICMP-ONLY: NO
DEVICE_METRIC CAN UNAMBIGUOUSLY IDENTIFY ICMP SAMPLE: NO

EXISTING DEDICATED ICMP ATTEMPT FIELD: NO
EXISTING DEDICATED ICMP RESULT FIELD: NO
DEVICE_STATUS_HISTORY SUFFICIENT FOR CONTINUOUS FAILURE FRESHNESS: NO

RECOMMENDED SOURCE: New dedicated durable `last_icmp_attempt_at` plus `last_icmp_status`; retain `Device.last_seen` for last successful reachability
SCHEMA CHANGE REQUIRED: YES
IF YES, MINIMUM FIELDS REQUIRED: `last_icmp_attempt_at` and `last_icmp_status`

PROPOSED REACHABLE RULE: Recent dedicated ICMP attempt, result reachable, and existing Device status online
PROPOSED UNREACHABLE RULE: Recent dedicated ICMP attempt, result unreachable, and existing Device status offline
PROPOSED STALE RULE: Historical ICMP evidence exists but no recent attempt
PROPOSED UNKNOWN RULE: No ICMP evidence or monitoring is not enabled under the existing contract

DEVICE 293 EXPECTED HEALTH AFTER FUTURE FIX: Unreachable/offline while the failed attempt remains fresh; not stale solely because last successful reachability is old

ICMP PING BEHAVIOR CHANGE REQUIRED: NO
BATCHING BEHAVIOR CHANGE REQUIRED: NO
SCHEDULER CHANGE REQUIRED: NO
REDIS CHANGE REQUIRED: NO
SNMP CHANGE REQUIRED: NO
FRONTEND CHANGE REQUIRED: NO

CODE CHANGED: NO
DATABASE CHANGED: NO
SAFE FOR SURGICAL IMPLEMENTATION: YES
