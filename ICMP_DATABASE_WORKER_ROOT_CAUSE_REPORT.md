# ICMP / Database / Worker Offline Root-Cause Audit

**Date:** 2026-09-17 (Asia/Kolkata)  
**Mode:** verification only. No code, topology, device status, or database data was changed.

## Executive conclusion

The ICMP worker is not absent. Same-day logs show a continuously running 15-second monitor loop, repeated probes for the monitored set, and successful metric-batch flushes. The first confirmed broken stage is the production ICMP probe capability:

1. Native raw ICMP socket creation fails with `PermissionError: [Errno 1] Operation not permitted` in this execution environment.
2. Production code then enters the subprocess fallback.
3. Captured worker logs show repeated `observed=down`, `rtt_ms=None`, and `timeout_or_error` for reachable/SNMP-active targets, including `192.168.100.2` for hundreds of cycles.

Therefore the evidence supports **ICMP probe failure**, not “worker never restored.” The exact fallback-level reason is not fully determinable because PostgreSQL/FastAPI are unavailable and the host `ping` invocation returned exit code 2 without usable output in this sandbox. It must not be guessed as a device failure.

## Database and runtime access

| Check | Result | Evidence |
|---|---|---|
| Configured DB source | Identified without printing secrets | `hardik/backend/.env` is loaded by `backend/config/settings.py`; URL is redacted here |
| PostgreSQL connectivity | FAIL / blocked | `pg_isready -h localhost -p 5432`: no response |
| FastAPI connectivity | FAIL / blocked | localhost:8000 returned no connection |
| Expected database confirmed | NO / PENDING | No live SQL connection; cannot prove active process uses the configured DB |
| Migrations | PENDING | Application-managed migrations are defined and startup calls `run_migrations(engine)`, but `schema_migrations` could not be queried |
| Required monitoring tables | PENDING | No live schema query |

No passwords, communities, tokens, or credentials are included.

## Real device database audit

Direct device rows and counts could not be queried. The following are therefore **PENDING**, not zero:

- Total real devices
- Monitoring-enabled devices
- ICMP-expected devices
- SNMP-enabled devices
- Duplicate/soft-deleted/invalid-IP checks
- Current raw status, `last_seen`, and timestamps

Same-day logs do establish that device `192.168.100.2` was a real active SNMP target and an ICMP worker target. Its database ID, hostname, monitoring flags, raw status, and derived health require live DB/API access.

## Status authority

Source evidence identifies the current derived-health authority as `hardik/backend/services/device_health.py:derive_device_health`. It evaluates `device.monitoring_status`, `device.last_seen`, latest successful `DeviceMetric`, and SNMP freshness, and returns both derived `status` and `last_known_status`.

The ICMP worker maps in-memory `up/down/unknown` to persisted `online/offline/unknown` in `realtime_monitor.py`. Thus a repeated production probe failure can produce persisted offline state; the frontend/API’s exact displayed value for one live device could not be queried. The precise UI authority is **PENDING**, not assumed to be raw `Device.status`.

## FastAPI startup and restoration

Source path:

`backend/main.py lifespan()` → `get_engine().restore_enabled_devices()` → `MonitorEngine.restore_enabled_devices()` → query `Device.deleted_at IS NULL AND Device.monitoring_status IS TRUE` → `start_all()` → `_ensure_loop()`.

| Stage | Result |
|---|---|
| FastAPI lifespan entered | PENDING in current runtime; no process reachable |
| ICMP restore function called | PENDING directly; source wiring confirmed |
| Restore completed | PENDING directly; no current startup log |
| Restore selection condition | Confirmed source-level: not deleted + `monitoring_status=True` |
| Offline status blocks restoration | No; restore query does not filter on current status |
| Worker creation | YES in historical/current log evidence: `monitor_device_started` and repeated probe logs |

This rules out “offline status prevents restore” as the first broken stage based on the available evidence.

## ICMP worker registry and continuity

| Device/target | Expected monitor | Registered/running evidence | Last captured probe | State |
|---|---:|---|---|---|
| 192.168.100.2 | Yes by worker log activity | Yes; repeated 15-second probes | 2026-09-17 12:48:38.911, down, RTT null, failure 599 | Running in captured log window, probe failing |
| 192.168.100.10 | Yes by worker log activity | Yes; repeated probes | Same-day logs | Probe result requires separate correlation |
| 192.168.100.105 | Yes by worker log activity | Yes; repeated probes | Same-day logs | Probe result requires separate correlation |

Worker loop evidence: repeated probe lines at 15-second cadence and `ICMP_METRIC_BATCH_FLUSHED` entries approximately every cycle. No worker-exit, executor-shutdown, or batch-failed entry was found in the inspected current log tail.

## Production probe and host comparison

| Check | Result | Evidence |
|---|---|
| Target | 192.168.100.2 | Same-day SNMP and ICMP logs |
| Native production ICMP | FAIL | Creating `AF_INET/SOCK_RAW/IPPROTO_ICMP` raises `PermissionError(1)` |
| Required capability | Missing in current execution environment | Raw socket denied; consistent with missing `CAP_NET_RAW`/sandbox privilege |
| Fallback reached | YES by source design; current log has prior `ICMP_ENGINE_UNAVAILABLE` evidence | `_ping()` switches permanently to `_subprocess_ping()` after native failure |
| Fallback result | FAIL in captured worker behavior | Repeated `timeout_or_error`, null RTT, stable down |
| OS ping from NMS host | NOT TESTABLE / FAIL | `/usr/bin/ping` exists but returns exit code 2 with no usable output in this sandbox |
| Device blamed | NO | SNMP root polls succeed for the same network and prior discovery logs report ICMP UP for 192.168.100.2 |

The exact confirmed failure is raw ICMP permission denial. The fallback needs a privileged real-host test to determine whether its exit-2 behavior is caused by host policy, namespace/network restriction, command invocation/environment, or another OS-level condition.

## Three ICMP probes

For `192.168.100.2`, the captured worker sequence is:

| Probe | Timestamp | Result | RTT | Worker |
|---|---|---|---|---|
| 1 | 12:48:08.911 | down / timeout_or_error | null | still emitting cycles |
| 2 | 12:48:23.902 | down / timeout_or_error | null | still emitting cycles |
| 3 | 12:48:38.911 | down / timeout_or_error | null | still emitting cycles |

Continuity passes; success does not. This is not evidence that the device is unreachable.

## ICMP persistence and batch writer

The worker queues one metric per ping and flushes through `DeviceMetric` persistence. Current logs show repeated `ICMP_METRIC_BATCH_FLUSHED` with low durations and no inspected `ICMP_METRIC_BATCH_FAILED`. This proves the batch writer is active at log level, but direct latest-row/timestamp queries are blocked by PostgreSQL unavailability.

| Check | Result |
|---|---|
| Probe → metric buffer | PASS from worker design/log cadence |
| Metric buffer → batch writer | PASS from repeated flush logs |
| Batch writer → DB commit | PENDING; flush log is not a SQL commit receipt |
| ICMP DB timestamps advancing | PENDING; no SQL query |
| Persisted success/last_seen | PENDING; captured probes are failures |

## Database error audit

No direct current DB error query was possible. Historical `availability_percent` NULL violations are not sufficient to label current behavior active. Classification: **PENDING**. No inspected current log line proves that the availability failure is poisoning ICMP writes; the ICMP batch flush path reports success in the available logs.

## SNMP cross-check

SNMP is a strong cross-check against blaming the devices: same-day `snmp.log` records successful root queries for `192.168.100.2` and other targets, including six roots succeeded and no timeouts. Therefore:

**DEVICE NETWORK/SNMP REACHABLE; ICMP PIPELINE FAILURE SUSPECTED.**

No SNMP code was changed.

## Time and API/frontend checks

Backend source has mixed timestamp handling: ICMP display state uses an IST-aware formatted string, while DB persistence uses `datetime.utcnow()`. Full worker → DB → API → frontend instant comparison is blocked. No live API/frontend access was available to verify stale query ordering, negative age, future last-seen, or status badge behavior.

| Check | Result |
|---|---|
| Health derivation | PENDING |
| DB/API consistency | PENDING |
| Frontend status consistency | PENDING |
| Timezone/freshness | PENDING |

## Demo/random-data isolation

Startup/service import search found no production import of:

- `hardik/continuous_monitoring.py` — DEMO/UNUSED in inspected startup wiring
- `hardik/simple_monitor.py` — DEMO/UNUSED in inspected startup wiring
- `hardik/setup_monitoring.py` — DEMO/UNUSED standalone setup script

They remain untouched and are not used as evidence.

## Required summary

- **POSTGRESQL:** FAIL
- **EXPECTED DATABASE CONFIRMED:** NO / PENDING
- **MIGRATIONS:** PENDING
- **TOTAL REAL DEVICES:** PENDING
- **MONITORING ENABLED:** PENDING
- **ICMP EXPECTED DEVICES:** PENDING
- **ICMP ACTIVE WORKERS:** PENDING exact count; worker activity confirmed
- **FASTAPI LIFESPAN:** PENDING
- **ICMP RESTORATION:** PENDING direct startup proof; worker creation evidenced
- **WORKER REGISTRY:** PASS for observed active loop; exact registry count pending
- **HOST OS PING:** NOT TESTABLE
- **PRODUCTION ICMP PROBE:** FAIL (raw socket permission denied; fallback yields failures)
- **3 ICMP PROBES:** FAIL (three consecutive failures, worker continuous)
- **ICMP DB PERSISTENCE:** PENDING direct DB; batch flush logs PASS
- **ICMP TIMESTAMPS ADVANCING:** PENDING
- **BATCH WRITER:** PASS at log level
- **CURRENT DB WRITE ERRORS:** PENDING
- **AVAILABILITY NULL ERROR:** PENDING
- **SNMP CROSS-CHECK:** PASS (same-day successful SNMP roots)
- **HEALTH DERIVATION:** PENDING
- **DB/API CONSISTENCY:** PENDING
- **FRONTEND STATUS CONSISTENCY:** PENDING
- **TIMEZONE/FRESHNESS:** PENDING
- **DEMO DATA IN PRODUCTION PATH:** NO in inspected wiring

## Pipeline result

- **DB DEVICE INTENT → ICMP RESTORE:** PENDING (live DB/startup unavailable; source query is appropriate and does not require online status)
- **ICMP RESTORE → WORKER:** PASS from captured worker activity; direct startup invocation pending
- **WORKER → PROBE:** FAIL (probe execution returns repeated failures)
- **PROBE → DB:** PENDING direct SQL; batch flush evidence PASS
- **DB → HEALTH:** PENDING
- **HEALTH → API:** PENDING
- **API → UI:** PENDING

## Root cause

**FIRST BROKEN STAGE:** Production ICMP probe capability, at native raw-socket creation / fallback execution—not worker restoration.

**PRIMARY CONFIRMED TECHNICAL CAUSE:** `socket.socket(AF_INET, SOCK_RAW, IPPROTO_ICMP)` is denied with `PermissionError: [Errno 1] Operation not permitted`. The worker then records repeated failed probes (`timeout_or_error`) and stable `down` for targets that have successful SNMP evidence.

**FALLBACK ROOT CAUSE:** Not fully proven in this environment. The fallback path returns failure in worker logs, but the underlying OS-level reason requires a test on the actual NMS host/service namespace with usable ping diagnostics.

**SECONDARY ISSUES:**

- PostgreSQL/FastAPI are unavailable, preventing direct device, persistence, health, and API confirmation.
- The fallback catches `OSError` and converts it to `(False, None)` without logging the executable/return code/stderr, which obscures the exact fallback failure.
- Historical availability NULL errors remain unverified as current.

**FILES/FUNCTIONS INVOLVED:**

- `hardik/backend/services/realtime_monitor.py`: `_native_ping`, `_subprocess_ping`, `_ping`, `MonitorEngine.restore_enabled_devices`, `_ensure_loop`, `_loop`, `_ping_one`, `_flush_metric_batch`, `_persist_ping_result`
- `hardik/backend/main.py`: `lifespan`
- `hardik/backend/services/device_health.py`: `derive_device_health`

## Fix priority / recommendation

**P0:** Restore a permitted, diagnostically verifiable ICMP probe path for the production service namespace. The smallest safe first fix is operational: run the NMS service with the required raw-ICMP capability or validate/configure the subprocess ping fallback on the actual host. Do not force status online or alter DB state.

**P1:** After probe capability is restored, verify direct `DeviceMetric`/`last_seen` updates and derived-health/API output; separately audit availability NULL writes.

**P2:** Improve fallback error observability and remove ambiguity between unavailable probe capability and device-down results.

**SAFE TO FIX P0:** YES, after confirming the deployment permission model and actual service namespace. No fix was implemented in this audit.

Stopped here as requested.
