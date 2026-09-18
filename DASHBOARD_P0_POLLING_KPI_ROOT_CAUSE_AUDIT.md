# Dashboard P0.3 Polling KPI Root-Cause Audit

**Date:** 2026-09-17  
**Mode:** read-only source audit. No code, labels, scheduler behavior, or database rows were changed.

## Executive conclusion

`PollingHistory` is an audit table for individual persisted collector outcomes, but it does not contain a reliable logical poll-cycle identity. It has no scheduler run ID, process/backend ID, start/completion pair, attempt ID, or uniqueness constraint that can distinguish a legitimate close-together poll from a duplicate caused by two backend schedulers.

The current Dashboard `/overview` KPI is therefore truthfully an **historical row/attempt outcome count within the selected window**, not a deduplicated current scheduler-health metric and not a device-level success count. Historical duplicate-backend rows cannot be safely removed or heuristically collapsed from the existing schema.

## PollingHistory schema

Model: `hardik/backend/models/snmp.py:PollingHistory`  
Table: `polling_history`

| Field | Meaning |
|---|---|
| `id` | Integer primary key; stable insertion tie-breaker only |
| `created_at` | Inherited `SNMPBase` timestamp; India-local naive timestamp by model helper |
| `updated_at` | Inherited audit timestamp |
| `device_id` | Real device foreign key, indexed |
| `collector` | Module/collector name, indexed |
| `status` | String result status, indexed |
| `duration_ms` | Duration of collector execution when available |
| `error` | Failure/unsupported description |

Absent fields:

- no `started_at`
- no `completed_at`
- no scheduler execution ID
- no poll cycle/run ID
- no backend process ID
- no host/instance ID
- no retry/attempt sequence
- no scheduled interval snapshot
- no uniqueness constraint

Existing indexes include device + created time and device + status + created time. These improve queries but do not provide deduplication identity.

## Production writers and one-row semantics

### Central scheduler writer

`hardik/backend/services/snmp_polling.py` runs one `PollJob` per `device_id + module_name`. APScheduler job IDs use that same pair and use `replace_existing=True`, `max_instances=1`, `coalesce=True`, and misfire handling within a single scheduler instance.

After a collector result is persisted, `_persist_results()` calls `_persist_history()`, which inserts exactly one `PollingHistory` row for that collector result:

- supported collector result → `status = "success"`
- unsupported collector result → `status = "not_supported"`
- `created_at = now_utc()` from the persistence operation
- duration/error stored when applicable

Collector exceptions before `_persist_results()` do not create a history row in this path; they are logged and returned as failed scheduler execution state. A poll guard prevents same-key overlap within one process only.

### Manual/discovery writer

Manual/discovery collection also constructs `PollJob`-shaped objects and calls `_persist_results()` for each collector payload. Therefore one discovery operation can legitimately create one history row per collector/module. These rows cannot be confused with duplicate scheduler rows solely by timestamp.

### API monitoring actions

Monitoring start/update APIs configure or reschedule `(device_id, module_name)` jobs; they do not create a separate poll-cycle identity. A poll only creates history when the collector result reaches `_persist_results()`.

### Retries and skipped work

- The process-local `poll_guard` returns a skipped/in-progress result when the same device/module is already active; skipped work does not create a `PollingHistory` row through the normal persistence path.
- A retry/restarted scheduler execution can legitimately create another row for the same device/module.
- Multiple modules for one device are legitimate distinct rows.
- Multiple backend processes have independent in-memory guards and scheduler instances, so they can produce duplicate logical attempts for the same configured device/module/time.

## Status semantics

Defined `PollStatus` values are:

| Status | Meaning | Current writer behavior |
|---|---|---|
| `success` | Collector returned supported data/result | Persisted by `_persist_history()` |
| `not_supported` | Collector/module is unsupported | Persisted when collector returns `supported=False` |
| `no_data` | Explicit no-data result | Enum supported; not emitted by the normal `_persist_history()` mapping examined |
| `timeout` | SNMP timeout | Enum supported; not directly emitted by `_persist_history()` mapping |
| `authentication_failed` | Authentication failure | Enum supported; not directly emitted by `_persist_history()` mapping |
| `device_unreachable` | Target unreachable | Enum supported; not directly emitted by `_persist_history()` mapping |
| `oid_not_supported` | OID unsupported | Enum supported; not directly emitted by `_persist_history()` mapping |
| `error` | Generic failure | Enum/config state supported; not directly emitted by `_persist_history()` mapping |

The persisted production writer inspected here collapses every non-supported collector result to `not_supported`; it does not preserve finer-grained timeout/authentication/no-data status in `PollingHistory`.

## Current Dashboard KPI calculation

`hardik/backend/api/overview_routes.py` loads all `PollingHistory` rows where:

```text
created_at >= utcnow - selected_hours
```

and orders by `created_at DESC`.

The normalized KPI logic is:

```text
success = count(status == "success")
failure = count(status != "success")
last_success = first success timestamp in descending rows
last_failure = first non-success timestamp in descending rows
collector_failures = count(status not in {"success", "no_data"})
```

The Dashboard labels these as “Successful polls”, “Failed polls”, “Poll Success”, and “SNMP failed”.

### Actual meanings

| Displayed value | Actual meaning | Label truthful? |
|---|---|---|
| Successful polls | Number of persisted `success` history rows in the selected window | Yes if called successful attempts, not devices |
| Failed polls / SNMP failed | Number of persisted rows whose status is anything other than `success` | No: includes `not_supported`, and potentially `no_data`/other statuses |
| Poll Success percentage | `success rows / (success rows + all non-success rows)` | No as a current health metric; it is a historical row ratio |
| Last success | Newest success row across all devices/modules | Partially; not a current per-device health timestamp |
| Last failure | Newest non-success row across all devices/modules | Partially; includes unsupported/no-data depending on stored status |
| Active jobs | Count of enabled `MonitoringConfig` rows | No if interpreted as currently executing jobs; it is configured enabled jobs |
| Unsupported OIDs | Count of unsupported OID cache rows | Yes as inventory/coverage count, not poll failures |

The KPI does not calculate successful devices, successful modules per scheduled cycle, current polling health, or deduplicated attempts.

## Duplicate-backend incident impact

Each backend process initializes its own scheduler from enabled `MonitoringConfig` rows. APScheduler job IDs and `max_instances=1` protect only that process’s scheduler. The process-local `poll_guard` also protects only one process.

During the duplicate-backend/restart-loop incident, two processes could therefore run the same `(device_id, module_name)` job and each insert a `PollingHistory` row. Those rows are indistinguishable from legitimate close-together retries or manual/discovery collection using the existing columns.

Classification of possible close-together rows:

- **A. Duplicate backend schedulers:** plausible and technically possible; no persisted process identity proves it row by row.
- **B. Different modules:** legitimate; `collector` differs.
- **C. Different scheduled cycles:** legitimate; same device/module can run repeatedly at configured intervals.
- **D. Manual/discovery polls:** legitimate; same persistence path can be used.
- **E. Unsupported/no-data:** legitimate outcome categories, not duplicates.

No historical row is classified as duplicate based only on timestamp proximity.

## Safe deduplication key availability

No safe historical key exists. A heuristic such as `(device_id, collector, timestamp bucket)` could merge:

- legitimate 15-second interface cycles,
- legitimate retries,
- manual collection,
- two distinct polls with close completion times,
- or rows created with timezone/clock differences.

The `id` column identifies insertion order, not logical poll identity. Existing timestamps are persistence timestamps and cannot prove scheduler start or cycle membership. No process IDs should be invented for historical rows.

## Runtime status

The live PostgreSQL database was not queried in this environment. Therefore:

- exact duplicate row counts: **RUNTIME PENDING**
- per-device/module historical distributions: **RUNTIME PENDING**
- actual current Dashboard KPI values: **RUNTIME PENDING**
- confirmation of rows from the duplicate-backend period: **RUNTIME PENDING**

This audit does not delete, update, or rewrite historical rows.

## Recommended minimal P0.3 fix

Do not deduplicate existing history destructively. The smallest safe fix should be a KPI semantics/read fix:

1. Name existing counts explicitly as historical **poll attempts/outcomes**.
2. Count `success`, `not_supported`, `no_data`, and other statuses separately rather than folding all non-success into “failed”.
3. Keep unsupported/no-data out of failure counts unless the product explicitly defines them as failures.
4. Keep current health separate from historical activity; current health remains the existing derived-health contract.
5. For future true deduplicated KPIs, add a writer-generated poll-cycle/attempt identity (and ideally scheduler instance identity) before changing the read query.

Until a reliable future identity exists, existing history can support truthful attempt-based KPIs only. No safe historical deduplication key is available from the current schema.

## Scope confirmation

No ICMP, SNMP polling behavior, scheduler intervals, health authority, P0.2 traffic logic, topology, alerts/events, systemd, frontend design, IP Scan, or database rows were changed.

POLLING HISTORY SEMANTICS UNDERSTOOD: YES
ONE LOGICAL POLL ID AVAILABLE: NO
SAFE HISTORICAL DEDUPE KEY AVAILABLE: NO
UNSUPPORTED/NO_DATA SEMANTICS VERIFIED: YES
CURRENT KPI LABELS TRUTHFUL: NO
HISTORICAL ROW DELETION REQUIRED: NO
LIVE DUPLICATE COUNTS: RUNTIME PENDING
SAFE TO IMPLEMENT P0.3 FIX: YES
