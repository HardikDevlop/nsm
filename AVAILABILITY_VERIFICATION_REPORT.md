# Availability Verification Report

## Scope and Method

This verification inspected only the Availability implementation, its persisted-data dependencies, API routes, frontend wiring, and focused tests. No database writes, mock records, polling, or additional ICMP/SNMP collection were performed. Core NMS and CMDB were not modified.

## 1. Current Architecture

The module has two separate availability paths:

1. The dedicated Availability Reports path:
   - `POST /api/v1/availability/reports` calls `calculate_availability`.
   - The calculation reads `DeviceStatusHistory` and overlapping `ChangeRequest` maintenance windows.
   - A row is inserted into `availability_reports` and committed.
   - `GET /api/v1/availability/reports` returns persisted report rows.
   - CSV export reads the same persisted rows.
2. Existing overview/report-management paths calculate simplified availability dynamically from status-transition counts and current device state. They are not the dedicated Availability Reports workflow and use a different, non-duration-based formula.

The dedicated report path is therefore **manual/API-triggered and persisted**, not automatic, scheduled, startup-triggered, or frontend-generated.

## 2. Stage Matrix

| Stage | Status | Finding |
|---|---|---|
| Monitoring writes real device state | PASS | Monitoring services persist status transitions and current device status. |
| Persisted status history available to calculation | PASS | `device_status_history` is the primary source for dedicated reports. |
| Availability calculation | INCORRECT | It calculates duration for simple device cases, but has period, initial-state, overlap, and aggregate-entity correctness gaps. |
| Report persistence | PASS | `availability_reports` stores generated report summaries. |
| Automatic generation | NOT WIRED | No startup hook, scheduler job, or monitoring-triggered report generation exists. |
| API generation | PASS | Dedicated POST generation endpoint exists and is permission-protected. |
| API history/export | PASS | GET history and CSV export routes exist. |
| Frontend API wiring | PARTIAL | Frontend calls real GET history only; it does not generate reports or expose periods/entities/SLA. |
| Frontend report presentation | PARTIAL | It displays persisted values but lacks loading/error states, device names, period controls, outage detail, and SLA display. |
| Automatic refresh | NOT WIRED | React Query has no polling interval and disables focus refetch. |
| End-to-end automatic availability reporting | NOT WIRED | There is no complete monitoring -> calculation -> persisted report -> refreshed UI path. |

## 3. Data-Flow Diagram

```text
ICMP monitoring / realtime monitor
        |
        v
devices.status, last_seen, last_status_change
        |
        v
device_status_history (transition rows)
        |
        |  POST /api/v1/availability/reports
        v
calculate_availability()
        |
        +--> ChangeRequest maintenance windows
        |
        v
availability_reports (persisted summary)
        |
        +--> GET /api/v1/availability/reports
        |        +--> CSV export
        v
Availability.tsx
```

SNMP polling history, device metrics, alerts/events, and monitoring start/stop records are not inputs to `calculate_availability`.

## 4. Source Tables and Models

### `devices`

Relevant persisted fields include `id`, `hostname`, `ip_address`, `status`, `monitoring_status`, `created_at`, `last_seen`, `uptime_seconds`, `downtime_seconds`, and `last_status_change`. The dedicated calculation uses the device ID and, for site/business-service resolution, device relationships. It does not use device cumulative uptime/downtime counters or `created_at` to constrain the report period.

### `device_status_history`

Fields are `id`, `device_id`, `old_status`, `new_status`, `change_reason`, and `timestamp`. Monitoring services append a row only on a status transition, not on every successful/failed observation. The dedicated calculation reads all rows for each selected device with `timestamp < end`, ordered by timestamp.

### `device_metrics`

Contains latency, packet loss, CPU, memory, disk, temperature, bandwidth, and timestamp data. It is written by monitoring, but is not read by the dedicated availability calculation. It cannot by itself establish exact uptime/downtime intervals.

### `polling_history`

Contains SNMP poll attempts, collector, status, duration, error, and created time. It is not read by the dedicated availability service. It could support poll-observation coverage, but currently does not define availability semantics.

### Alerts/events

Alerts and events are persisted elsewhere and are used by overview/incident paths, but are not inputs to dedicated availability reports. Offline alerts are side effects of monitoring transitions, not authoritative availability intervals.

### Monitoring start/stop

`monitoring_configs` stores module enablement, running/stopped state, start/stop times, and poll times. The dedicated service does not read it. `devices.monitoring_status` is also not used to establish the report's monitored interval.

### `change_requests`

The calculation reads overlapping `maintenance_start`/`maintenance_end` windows and classifies their overlap as planned downtime. There is no explicit availability-policy or SLA model involved.

### `availability_reports`

The table stores `entity_type`, `entity_id`, `window_start`, `window_end`, `total_seconds`, planned and unplanned downtime seconds, availability percentage, downtime reasons, generator user, and generated timestamp. It does not store outage rows, SLA target, breach result, outage count, MTTR, or MTBF.

## 5. Exact Availability Formula Currently Used

For each resolved device:

```text
total = end - start
planned, unplanned = split each detected offline interval by maintenance overlap
down = min(total, sum(planned + unplanned across selected devices))
availability_percent = round((total - down) / total * 100, 3)
```

`_split()` calculates the interval duration, sums each maintenance-window overlap as planned time, and assigns the remainder to unplanned time.

This is a duration formula for a single device in straightforward data, but it is not a reliable multi-device aggregate formula because each device contributes downtime while the denominator remains one report-window duration.

## 6. Device 115 Calculation Capability

The code path accepts `entity_type=device` and `entity_id=115` without requiring new device-side configuration. If device 115 exists and has persisted status-transition history, the POST endpoint can generate and persist a report for it.

From code inspection alone, without querying the real host database, the following cannot be asserted for device 115:

- whether status-history rows actually exist;
- the first/last observation timestamps;
- whether the initial state is known;
- whether there are gaps, duplicate timestamps, or ongoing outages;
- whether maintenance windows overlap its report period.

Therefore device 115 is **PARTIAL / BLOCKED for factual runtime capability confirmation** in this restricted verification. No new polling or database access was attempted.

## 7. Supported Metrics

| Metric | Status | Reason |
|---|---|---|
| Current status | PARTIAL | Available from `devices.status`, but not returned by dedicated report API. |
| Monitoring period | PASS for requested window only | `start` and `end` are accepted and stored; actual monitored coverage is not validated. |
| Total monitored duration | PARTIAL | Stores `end-start`, not confirmed monitored time from start/stop or observations. |
| Uptime duration | PARTIAL | Only derivable indirectly as `total - downtime`; not stored or returned as uptime. |
| Downtime duration | PASS for simple single-device case | Planned + unplanned duration is stored. |
| Availability percentage | PARTIAL / INCORRECT for edge cases | Formula exists, but initial state, gaps, duplicates, overlap, and aggregate issues remain. |
| Outage count | NOT WIRED | No outage entity/count is calculated or stored. |
| Outage start/end/duration | NOT WIRED | Only aggregate downtime seconds are stored. |
| Last outage | NOT WIRED | No field or calculation exists. |
| MTTR | NOT WIRED | Requires outage start/end records and recovery semantics. |
| MTBF | NOT WIRED | Requires complete outage/recovery intervals and valid observation boundaries. |
| SLA target | PARTIAL | Accepted in POST request with default `99.0`, but not persisted or policy-backed. |
| SLA achieved/breached | PARTIAL | Returned only from POST response using the transient request target; absent from persisted GET rows and frontend. |

## 8. Calculation and Data-Quality Validation

### Unknown initial state

The algorithm does not explicitly model unknown initial state. It processes transitions before `end`; an offline transition starts downtime at its event time, while time before the first observation is not classified as unknown. Missing evidence is effectively excluded from downtime and can be treated as available by the denominator.

### Monitoring gaps

There is no gap detection based on poll cadence, `monitoring_configs`, `polling_history`, or `device_metrics`. A long interval between status transitions is treated as the previous state for duration purposes, even if monitoring was stopped or data collection was unavailable.

### First observation

The first observed offline state starts an outage at the offline event. The first observed online state does not establish how long the device was online before that observation. `devices.created_at`, monitoring start, and first poll are not used.

### Currently ongoing outage

An outage with no subsequent non-offline event is closed at `end`. This is supported for the simple device case.

### Returning online

A later status other than `offline` closes the outage. Any non-offline value, including `unknown`, is treated as recovery; that can falsely close an outage if `unknown` is not a confirmed online state.

### Duplicate status records

No deduplication is performed. Same-timestamp or repeated transition rows can create unstable ordering or incorrect interval transitions. Query ordering is only by timestamp, not timestamp plus deterministic ID.

### Missing history

Missing history does not cause an error for a valid device. The report becomes 100% availability because downtime is zero, even though the system has no evidence that the device was monitored for the full requested period.

### Partial periods and devices added mid-period

The requested window is accepted, but device creation time and monitoring start time are ignored. A device added midway can be scored over the entire earlier window. There is no explicit partial-coverage marker.

### Timezone handling

Database model fields are naive `DateTime`; the calculation uses `datetime.utcnow()` for generation. API payloads may contain timezone-aware ISO datetimes. There is no explicit normalization or validation that all values are in one timezone, so aware/naive comparisons can fail or produce ambiguous boundaries depending on the database/runtime behavior.

### Maintenance overlap

`_split()` sums overlaps for every maintenance window. Overlapping maintenance windows can double-count planned seconds. For multiple devices, downtime is summed and then capped by one window total, which does not represent device-service availability correctly.

## 9. SLA Behavior

- SLA target is a request-body field on POST, range `0..100`, default `99.0`.
- It is not stored in `availability_reports`.
- `achieved_sla` is simply the calculated availability percentage in the POST response.
- `breached` is calculated as `availability_percent < payload.sla_target`.
- GET history does not return target, achieved SLA, or breach state.
- CSV export hardcodes a `99.0` comparison rather than using a persisted or entity-specific target.
- No device/site/business-service SLA policy, inheritance, schedule, or calendar is present.

Classification: **PARTIAL**. A one-request comparison exists, but there is no durable or configurable SLA behavior.

## 10. Report-Period Behavior

Supported at API calculation level: arbitrary `start` and `end` datetimes are accepted, provided `end > start`.

Not supported in the frontend: no controls or presets for last 24 hours, 7 days, 30 days, or custom range; the page never calls the POST route.

The backend does not expose a period-specific calculation in GET. GET only returns previously persisted reports, optionally filtered by entity, with pagination. The calculation is not constrained to `timestamp >= start`; it loads all earlier history and only clamps an active downtime interval when it begins.

## 11. Frontend Wiring

`figma design/src/pages/Availability.tsx`:

- uses the real `listAvailabilityReports()` API helper;
- calls `GET /availability/reports` through the authenticated API client;
- renders actual persisted report rows, not mock/static report data;
- has permission gating for `availability:read`;
- displays entity type/ID, availability, planned seconds, unplanned seconds, and JSON downtime reasons.

Missing or incomplete frontend behavior:

- no report-generation POST call;
- no period filter or entity/device selector;
- no device-name lookup, so rows are ID-oriented;
- no uptime/downtime duration presentation beyond planned/unplanned seconds;
- no outage list/history details or click-through;
- no SLA target/status display;
- no explicit loading state;
- no explicit error state;
- empty state can render while the query is still unresolved because it checks `query.data?.items` without a loading branch;
- no automatic refresh because `refetchOnWindowFocus` is false and no `refetchInterval` is configured.

The route is registered at `/availability` and protected by the same frontend permission gate. The API helper contract omits several POST response fields and generated metadata, reinforcing that the page is history-only.

## 12. Performance Risks

### Dedicated availability calculation

- For a site, the service first loads all devices, then executes one status-history query per device: an N+1 query pattern.
- Business-service resolution performs relationship and CI queries, then can also execute one history query per resolved device.
- Each history query loads all rows before `end`, without a lower timestamp bound or a database-level limit.
- Maintenance windows are loaded once per report, but overlap checks are performed in Python for every outage interval.
- Repeated manual generation inserts another report row each time; there is no idempotency key for entity and period.

### Frontend

- The list query is bounded by the API default/response limit, but the page has no explicit pagination or report-period filter.
- Query caching is present, but there is no refresh and no device-name enrichment query.

These are reported risks only; no optimization was performed.

## 13. Exact Missing Pieces

1. A defined source-of-truth policy for availability: transition history, poll observations, or a combined state model.
2. Explicit monitoring coverage boundaries using device creation and monitoring start/stop data.
3. A period-bounded, timezone-normalized calculation with unknown/uncertain coverage represented separately from uptime.
4. Deterministic deduplication and handling for same-state, duplicate, and same-timestamp records.
5. Correct interval union logic for overlapping maintenance windows and multi-device aggregates.
6. Persisted outage intervals with start, end, duration, reason, and ongoing state.
7. Outage count, last outage, MTTR, and MTBF calculations based on those intervals.
8. Persisted/configurable SLA policy and report-level target, achieved, and breach fields.
9. Automatic generation or refresh trigger, if reports are intended to be continuously available.
10. API support for period presets/custom ranges, entity/device selection, and detailed outages.
11. Frontend generation controls, period filters, actual device names, SLA status, loading/error states, and outage drill-down.
12. Query strategy that avoids per-device history queries and unbounded history loads.

## 14. Minimum Implementation Required

To make automatic, accurate device availability reports possible without changing core NMS or CMDB behavior, the minimum isolated Availability implementation would be:

1. Define monitored coverage and status semantics, including how unknown/gaps are classified.
2. Add a period-bounded calculation that normalizes timezone, seeds state from the last observation before the period, handles first observation and ongoing outages explicitly, and unions intervals safely.
3. Add deterministic duplicate handling and tests for gaps, partial periods, mid-period device creation, recovery, and overlapping maintenance.
4. Persist or derive outage intervals and add supported metrics for outage count, last outage, MTTR, and MTBF only when the data is sufficient.
5. Add a persisted SLA policy/target model or an explicit report target field; return the same SLA data from POST, GET, and export.
6. Add an isolated scheduled/startup/manual generation policy with idempotent period/entity keys, if automatic reports are required.
7. Extend the Availability API and frontend with real period/entity controls, generation/refresh behavior, device labels, outage details, SLA status, and proper loading/error/empty states.
8. Replace per-device unbounded history reads with bounded/aggregated queries while preserving real persisted data only.

## Final Classification

The current module can generate and persist a basic, manually requested single-device downtime summary from real status-transition history. It cannot currently generate automatically refreshed, period-accurate, SLA-complete Availability Reports with outage/MTTR/MTBF detail. Overall classification: **PARTIAL**, with the automatic end-to-end path **NOT WIRED** and several edge cases **INCORRECT**.
