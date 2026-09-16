# Device Health and Freshness Fix Report

## Implementation

Added `hardik/backend/services/device_health.py` as the single derived health calculation. It correlates persisted ICMP liveness with independent SNMP configuration/history without overwriting `Device.status`.

Freshness uses the configured interval and a documented safe multiplier of **3×**. The result is additive and exposed from `POST /api/v1/monitoring/data` under `health`, preserving existing `status`, `timestamp`, and module fields.

Derived states:

- `online`: fresh reachable ICMP or fresh healthy monitoring evidence
- `offline`: recent explicit ICMP failure
- `degraded`: ICMP reachable while SNMP is failed/stale
- `stale`: expected ICMP evidence is too old
- `unknown`: no sufficient current evidence

SNMP states are independent: `healthy`, `failed`, `stale`, `unsupported`, `disabled`.

## Device.status writers found

The source audit found **10 writer groups**:

| Writer | Trigger / values | Conflict risk |
|---|---|---|
| `backend/services/monitoring.py:run_monitoring_check` | ICMP success/failure → online/offline | Yes, with discovery/realtime paths |
| `backend/services/realtime_monitor.py` | Background ICMP transitions → online/offline | Yes, competing ICMP authority |
| `backend/api/routes.py` add/discovery flows | Probe result → online/offline; last_seen on success | Yes |
| `backend/api/routes.py` restore/undelete flow | Explicit restore → online; last_seen | Yes; administrative action is not liveness evidence |
| `backend/api/discovery_routes.py` | Discovery/reconciliation → online and last_seen | Yes; discovery can be older than monitoring |
| `backend/api/snmp_device_routes.py` | SNMP device verification → online/offline and last_seen | Yes; SNMP must not prove ICMP liveness |
| `backend/services/snmp_polling.py` | `MonitoringConfig.status` only: running/error/not_supported | Separate state, not Device.status |
| `backend/api/overview_routes.py` | `monitoring_status` kill-all flag | Does not directly change Device.status |
| `backend/cmdb/service.py` | Copies operational status/last_seen into CMDB | Downstream representation |
| `backend/services/realtime_monitor.py` cache/SSE projection | Persists and publishes status | Can expose stale DB status |

`last_seen` is correctly not updated on failed probes in the optimized ICMP service path. Other discovery/verification paths can write it on successful discovery or SNMP verification and therefore remain semantically mixed; those were not changed because this step must preserve device-status behavior.

## Required summary

- DEVICE.STATUS WRITERS FOUND: **10 writer groups**
- HEALTH AUTHORITY: **UNIFIED for derived monitoring-data response; legacy Device.status writers remain PARTIAL**
- ICMP AUTHORITY: **PARTIAL** (multiple existing writers)
- SNMP HEALTH: **CLEAR** in new derived helper
- FRESHNESS RULE: **IMPLEMENTED** (configured interval × 3)
- STALE STATUS: **IMPLEMENTED** in derived API health; legacy `Device.status` is preserved
- LAST_SEEN SEMANTICS: **PARTIAL** due to legacy discovery/SNMP verification writers
- SNMP FAILURE MARKS DEVICE OFFLINE: **NO** in the new health contract
- STOPPED POLLING CAN REMAIN ONLINE FOREVER: **NO** in derived API health; legacy raw `Device.status` may still be online
- HEALTH STATES: **ONLINE / OFFLINE / DEGRADED / STALE / UNKNOWN**
- BACKWARD API COMPATIBILITY: **PASS** (additive `health` field)
- FOCUSED TESTS: **PENDING** (pytest is not installed in the environment)
- PYTHON COMPILE: **PASS**
- FRONTEND BUILD: **NOT CHANGED**
- RUNTIME VERIFICATION: **PENDING**

## P0 issues remaining

- Existing pages/API paths that read raw `Device.status` can still present stale `online` until they adopt the additive derived-health contract.
- Existing legacy timestamps/last_seen provenance remains mixed and was intentionally not migrated.

## P1 issues

- Migrate remaining device-list/detail/overview responses to the same derived health helper.
- Consolidate legacy status writers behind one liveness service in a later step.
- Add dedicated backend tests once the project test runner/dependencies are available.
- Add stale alerting only after confirming it cannot duplicate existing device-down alerts.

## Files changed

- `hardik/backend/services/device_health.py`
- `hardik/backend/api/monitoring_data_routes.py`
- `DEVICE_HEALTH_FRESHNESS_FIX_REPORT.md`

No scheduler observability, frontend refresh consolidation, page redesign, polling interval, OID, collector, or device-status transition changes were made.

