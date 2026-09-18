# Dashboard Real-Data Root-Cause Audit

**Date:** 2026-09-17  
**Mode:** read-only audit. No code, database rows, service configuration, or runtime state was changed.

## Executive conclusion

The Dashboard has multiple data authorities and several stale/missing-data transformations. The most important confirmed source-level root cause is:

1. The main Dashboard page uses `/overview`, whose device counts are derived by `derive_device_health()` from ICMP/SNMP evidence.
2. The application sidebar uses `/dashboard/summary`, whose online/offline counts directly count `Device.status`.
3. `/dashboard/summary` also writes a Redis value, but the route itself reads the database; the sidebar can fall back to `/snmp/devices` and count raw `status` again.

This permits different visible “total/online/health” values for the same database state. It also explains why fixing the live ICMP worker does not automatically make every Dashboard value consistent: raw `Device.status`, derived health, cached overview data, and frontend zero fallbacks are separate paths.

Additional confirmed problems:

- “Latest” metric rows are selected by maximum surrogate `DeviceMetric.id`, not by measurement timestamp with an ID tie-breaker.
- Latest SNMP CPU/memory/interface records are loaded into dictionaries without an explicit ordering/latest-row query; duplicate rows can overwrite each other nondeterministically.
- Polling latest-per-device uses `ORDER BY created_at DESC` without `id DESC` and `setdefault`, so equal timestamps are not deterministic.
- Missing values are converted to numeric zero in multiple Dashboard calculations and visualizations, including availability, CPU/memory gauges, traffic, polling percentages, and several chart values.
- Backend `/overview` is cached for 10 seconds in-process and Redis; frontend requests use `cache: "no-store"`, but that does not bypass the backend cache.
- The Dashboard’s automatic refresh is a hand-written 30-second timer and can overlap with manual/range-triggered loads; there is no request sequence guard to prevent an older response from winning.

Live DB/API values were not queried in this audit environment, so current row counts, exact current timestamps, and the magnitude of duplicate historical pollution remain runtime-pending.

## End-to-end path

### Main Dashboard

`real ICMP/SNMP collectors` → `DeviceMetric / PollingHistory / Latest* / InterfaceStatistic / Alert / Event` → `GET /api/v1/overview` → `getOverview(hours)` with `cache: "no-store"` → `Dashboard.tsx` state → cards, gauges, charts, alerts, traffic, devices.

The endpoint explicitly performs PostgreSQL reads and does not poll devices.

### Sidebar summary

`Device.status / Alert / Event` → `GET /api/v1/dashboard/summary` → `Sidebar.tsx` request every 15 seconds. It first reads `sessionStorage` and then uses a raw-status fallback request to `/snmp/devices` if the summary request fails.

These are not the same health authority.

## Field-by-field audit matrix

| Dashboard Field | Frontend Source | API | DB Source | Current-State Logic | Freshness Rule | Real Data? | Problem | Severity | Required Fix |
|---|---|---|---|---|---|---|---|---|---|
| Total Devices | `Dashboard.tsx` `summary.total_devices`; Sidebar `totalDevices` | `/overview`; `/dashboard/summary` | `Device`, `deleted_at IS NULL` | Main overview counts non-deleted devices; sidebar same raw count | No device-state freshness | Yes, persisted | Two endpoints/cache paths; sidebar can show session-cached value | P1 | Establish one dashboard summary authority and shared query contract |
| Online | Main `summary.online_devices`; Sidebar `onlineCount` | `/overview`; `/dashboard/summary`; fallback `/snmp/devices` | Main: `Device` + `derive_device_health`; sidebar: `Device.status` | Main derived health; sidebar raw status | Main health uses ICMP/SNMP freshness; sidebar none | Yes, but inconsistent | Derived vs raw status split | P0 | Make all Dashboard surfaces consume derived health |
| Offline | Main `summary.offline_devices`; Sidebar raw status | Same as Online | Same | Same split | Same split | Yes, but inconsistent | Old/raw offline status can remain visible after fresh ICMP | P0 | Remove raw status from summary display authority |
| Degraded | `health_counts.degraded` used by main page | `/overview` only | `Device`, `MonitoringConfig`, `PollingHistory` | `derive_device_health` | Per enabled config, 3× interval | Yes | Not represented in sidebar summary; users can see contradictory totals | P1 | Expose same health counts to all summary consumers |
| Stale | `health_counts.stale` | `/overview` | `Device.last_seen`, `PollingHistory` | Derived health | 3× configured interval | Yes | No direct stale count in `/dashboard/summary`; missing evidence can become unknown/zero UI | P1 | Share health response and explicit stale semantics |
| Unknown | Main health pie | `/overview` | Same derived inputs | Derived when no fresh evidence | 3× interval / no evidence | Yes | Several cards default absent values to 0, visually hiding unknown | P1 | Preserve null/unknown in presentation |
| Device status | Device list/alerts sections in `Dashboard.tsx` | `/overview` | `Device.status` plus `device.health` | Raw status is returned alongside derived health | No raw-status freshness | Yes | API exposes both; consumers may choose wrong one | P0 | Label raw status as last-known only and use health |
| ICMP status | Device health fields are returned but Dashboard mostly uses counts | `/overview` | `Device.monitoring_status`, `Device.status`, `Device.last_seen` | `icmp_health` in `derive_device_health` | `last_seen <= interval × 3` | Yes | Requires current DB `last_seen`; no per-card explicit ICMP display in main Dashboard | P1 | Surface one explicit ICMP authority/status |
| SNMP status | Device health and normalized polling | `/overview` | `MonitoringConfig`, `PollingHistory` | Healthy/failed/stale/unsupported | Last success <= module interval × 3 | Yes | Dashboard counts polling history over selected window, not current per-device SNMP state | P1 | Separate current health from historical poll totals |
| Availability | Gauge computed as `health.online / summary.total_devices * 100` | `/overview` | Derived health + Device inventory | Online percentage, not stored availability | Current response only | Yes, derived | Missing/empty becomes 0%; degraded/stale excluded without labeling | P1 | Return explicit availability/null when no current evidence |
| RTT / latency | Device/metric sections use normalized/metric values; `fmt` handles null | `/overview` | Latest `DeviceMetric.latency`, `created_at` | Max `DeviceMetric.id` row per device | No age cutoff on latest metric | Yes | Latest ID may be old/wrong relative to timestamp; no freshness gate | P1 | Select by `created_at DESC, id DESC` and expose metric age |
| Packet loss | Device metric fields / normalized data | `/overview` | Latest `DeviceMetric.packet_loss` | Max metric ID | No explicit freshness | Yes | Missing packet loss often rendered as zero in downstream pages; current Dashboard not consistently N/A | P1 | Preserve null and expose timestamp |
| CPU | `perf`, `avgCpu`, device cards | `/overview` `normalized.devices` then `d.cpu_usage` fallback | `LatestCPU.utilization_percent`; fallback `DeviceMetric.cpu_usage` | LatestCPU dictionary row; then latest DeviceMetric | No explicit stale rule in UI | Yes if persisted | Duplicate latest rows can overwrite; gauge computes 0 when no samples | P1 | Deterministic latest query + null/age-aware UI |
| Memory | `perf`, `avgMem`, device cards | `/overview` normalized + device fallback | `LatestMemory.utilization_percent`; fallback DeviceMetric | Same as CPU | No explicit stale rule | Yes if persisted | Same duplicate/zero issues | P1 | Same |
| Interface traffic current | Live Traffic cards, top devices/interfaces | `/overview` normalized traffic | `LatestInterface.rx_mbps/tx_mbps`, `polled_at` | Sums all returned latest-interface rows | No age filter | Yes if rows real | Null becomes 0 in sums; stale latest rows look current; duplicate interface rows are summed | P0 | Deterministic one-row-per-device/interface query, freshness gate, null preservation |
| Interface traffic history | `traffic_history` chart, minute buckets | `/overview` | `InterfaceStatistic.created_at`, rx/tx | Last 5000 rows over selected time window; sums per minute | `created_at >= since_24h` (variable `hours` is used in since) | Yes if persisted | Null channels initialized as 0; all rows aggregated, possible duplicate samples inflate traffic | P1 | Deduplicate by sample identity/interval and preserve missing channel |
| Interface up/down | Interface summary cards | `/overview` | `Interface.status`, LatestInterface | Counts all interface records | No freshness rule | Yes | Status table may include stale interfaces; `interface_summary` does not use polled_at | P1 | Tie status to current latest SNMP observation |
| Alerts | Alert cards/chart/list | `/overview` | `Alert` | Open/acknowledged, max 50 rows; severity counts over returned rows | No time window for alerts; capped at 50 | Yes | Critical/severity counts are capped to 50 recent active alerts, while labels imply totals; no tie-breaker on created_at | P1 | Define bounded vs total semantics and deterministic ordering |
| Events | Recent events section | `/overview` | `Event.timestamp` | Last 24h (relative to current UTC), limit 20 | Timestamp >= `utcnow - hours` | Yes | Order lacks `id DESC` tie-breaker; timezone-naive rows may shift window/order | P1 | Normalize timestamps and add deterministic tie-breaker |
| Monitoring status | Services/status panels | `/overview` services; Sidebar separate | Runtime engine state + `MonitoringConfig` | Runtime state is process-local; active jobs count is config count | Runtime snapshot/cache | Yes for runtime/config | Configured jobs can be mistaken for successful polls; Dashboard auto-starts SNMP polling if service says not running | P1 | Display configured vs running vs fresh-success separately |
| Last seen | Device cards/detail | `/overview` | `Device.last_seen` | Persisted successful ICMP marker | Derived health uses freshness; display itself does not | Yes | Raw display can be stale while still shown; timezone conversion needs contract | P1 | Show age/freshness beside timestamp |
| Last poll | Device detail sections | `/overview` normalized `last_poll` | Latest `PollingHistory.created_at` | `setdefault` after descending query | No per-module current rule | Yes | No id tie-break; “latest” is per device, not necessarily relevant collector/module | P1 | Select latest per device/module deterministically |
| Uptime | Device data and radar/overview details | `/overview` | `Device.uptime_seconds` | Stored cumulative counter | No freshness | Yes if persistence correct | Can reflect raw status transition history, not current availability; duplicate restart period may inflate | P2 | Clarify cumulative vs current-window uptime |
| Polling success/failure | Poll KPI cards | `/overview` normalized polling | `PollingHistory` | Counts every row in selected hours | `created_at >= since` | Yes | Duplicate backend period can inflate counts; no device/module dedupe; unsupported/no_data treatment differs | P0 | Correlate/dedupe poll attempts and separate unsupported/no-data |
| Active/critical alerts | Cards | `/overview` summary | `Alert` | Active rows limited to 50; critical count among rows | No time window, active status only | Yes | Critical count can be incomplete after 50-row cap | P1 | Count in SQL independently from display page |

## Backend query defects and risk areas

### Current-state versus historical data

- Current device health is derived per device by `derive_device_health()`.
- Current metric selection is not uniformly timestamp-based. `DeviceMetric` explicitly selects `MAX(DeviceMetric.id)`.
- `LatestCPU`, `LatestMemory`, `LatestInterface`, and `LatestEnvironment` are queried without an explicit “latest row” predicate or ordering. If these tables are truly one-row-per-key by schema, that should be enforced and audited; if not, dictionary construction is nondeterministic.
- Historical traffic and polling data are aggregated across all rows in the selected window. These are not current-state queries and can be inflated by duplicate-backend records.

### Timestamp and timezone risks

- `/overview` uses `datetime.utcnow()` and `created_at >= since` for history.
- `derive_device_health()` converts naive timestamps as Asia/Kolkata before comparing in UTC, which is intentional but depends on all legacy naive values actually being India-local.
- Dashboard traffic parses samples with `parseISTDate()` and then buckets in epoch milliseconds. A mixed naive/UTC payload can shift bucket membership.
- `events` and `alerts` order only by one timestamp column; equal timestamps are nondeterministic.

### Caching and refresh

- `getOverview()` uses `cache: "no-store"`, bypassing the generic frontend request cache.
- Backend `/overview` still has a 10-second in-process cache and 10-second Redis cache.
- Dashboard refreshes every 30 seconds and also reloads on range changes/manual refresh.
- `load()` has no abort controller, request generation number, or mounted guard. A slower earlier request can call `setData()` after a newer request and replace newer state.
- The Dashboard automatically calls `startPollingService()` when the overview reports SNMP polling not running, then fetches overview again. This is a side effect inside a read/refresh path and may create extra API requests or race with service startup.
- Sidebar uses a 15-second timer, sessionStorage bootstrap, an independent `/dashboard/summary` request, and a fallback `/snmp/devices` request. It has an in-flight guard, but it is a separate cache/authority from the main Dashboard.

## Mock/random/static data reachability

The Dashboard source inspected here reads `/overview` and does not import the previously identified random-monitoring modules. No direct production Dashboard path to `continuous_monitoring.py`, `simple_monitor.py`, or `setup_monitoring.py` was found. This is source-level evidence; deployment runtime wiring remains outside this read-only audit.

## Historical duplicate-backend period

The code does not isolate records by backend instance, process ID, or poll cycle. Therefore historical rows created during the duplicate-backend/restart-loop period remain eligible for:

- `DeviceMetric` max-ID latest selection;
- `PollingHistory` success/failure totals;
- `InterfaceStatistic` traffic aggregation;
- alert/event counts and charts.

The current healthy ICMP stream does not by itself remove those historical rows from selected-window totals. The exact impact requires a live SQL duplicate/timestamp audit.

## Root causes

### P0

1. **Conflicting status authorities:** `/overview` uses derived `health_counts`, while `/dashboard/summary` and its fallback count raw `Device.status`. This can show online/offline disagreement after current ICMP recovery.
2. **Traffic/current interface aggregation does not establish one fresh deterministic row per interface:** null values become zero, stale/duplicate latest rows can be summed, and `polled_at` is not used as a current freshness filter.
3. **Polling KPIs count historical rows without deduplicating duplicate-backend attempts:** counts can remain inflated after the runtime issue is fixed.

### P1

1. Latest metric/normalized SNMP records are not consistently selected with timestamp + ID ordering.
2. Missing values are frequently rendered as `0`, including CPU/memory/traffic/availability and chart calculations, hiding unavailable data.
3. Backend and frontend caches/refresh paths can keep a 10-second overview snapshot or allow an older Dashboard request to overwrite a newer one.
4. Alerts/events and history queries lack complete deterministic tie-breakers and have differing caps/windows.

### P2

1. Raw `Device.status` is returned beside derived health without a strong consumer-facing distinction.
2. Cumulative uptime is presented alongside current health without an explicit period/age label.
3. Dashboard refresh invokes a service-start mutation as a side effect of a read path.

## Required fix matrix

| Fix area | Required change | Scope |
|---|---|---|
| Health authority | Make Dashboard and Sidebar consume the same derived health summary | P0 |
| Current interface/traffic | Enforce deterministic latest-row selection and freshness; preserve null | P0 |
| Polling KPIs | Deduplicate/correlate attempts and separate success/failure/no-data/unsupported | P0 |
| Metric latest rows | Order by measurement timestamp then ID, or enforce one-row-per-key constraints | P1 |
| Missing values | Render N/A/unknown rather than numeric zero when source is absent | P1 |
| Refresh/cache | Add request cancellation/generation protection and explicit cache invalidation/versioning | P1 |
| Historical pollution | Audit and classify duplicate-backend rows before any cleanup | P1 |

## Final assessment

**ROOT CAUSES:** conflicting raw/derived status paths, nondeterministic/stale latest-data selection, historical row aggregation, and missing-value coercion to zero. The current ICMP runtime can be healthy while the Dashboard remains incorrect because the Dashboard is primarily a persisted snapshot consumer with multiple authorities and caches.

**SAFE TO FIX DASHBOARD:** NO for implementation in this audit step. The issues are sufficiently identified for a narrowly scoped next fix, but no code or data changes were authorized in this pass.
