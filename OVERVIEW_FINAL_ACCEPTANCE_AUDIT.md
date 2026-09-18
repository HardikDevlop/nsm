# Overview Final Acceptance Audit

Source/contract audit only. No code, database, scheduler, Redis, SNMP, or ICMP state was changed.

## Overview data and visible sections

Dashboard fetches `getOverview(hours)` from `/api/v1/overview`. The backend returns `summary`, `devices`, `alerts`, `events`, `normalized`, `services`, and `fetched_at`. Dashboard assigns `n=data.normalized` and renders the following visible sections:

| Section | API/source | Fallback/empty semantics | Real data and assessment |
|---|---|---|---|
| Device KPI cards | `summary.total_devices`, `online_devices`, `offline_devices`, `normalized.polling.failure`, alert counts, interface summary | Numeric nullish values fall back to 0 | Real persisted overview data; health card online/offline fields are summary-derived and current runtime verified |
| System Vitals | `normalized.devices` CPU/memory/load and latest normalized readings | Missing readings render N/A/zero gauge presentation according to component | Real latest persisted metric data; missing metric values are generally null-preserving |
| Live Traffic | `normalized.traffic.rx_mbps/tx_mbps` | Null traffic is displayed as unavailable/N/A in current traffic presentation | Real current fresh interface rows; stale rows excluded by backend aggregation |
| Health Radar | summary health/availability plus interface, SNMP, traffic derived values | Empty denominators render 0 gauge values | Derived presentation of real persisted health/current evidence; zero means no measurable denominator in the chart, not fabricated traffic |
| Status Share | `summary.health_counts` | Zero-count states filtered from radial data | Real derived health categories |
| Network Traffic/history | `normalized.traffic_history`, interface summary | Empty history shows no stored data; null current traffic remains unavailable | Real persisted interface history and current rows; deterministic latest selection and fresh-only current aggregate |
| Top devices/interfaces | `normalized.traffic.top_devices/top_interfaces` | Empty arrays produce empty state | Real fresh interface evidence; no mock traffic |
| Device Type Map / Types | `device_types` | Empty classification shows no device types | Real inventory classification |
| Alerts | `summary.critical_alerts`, `normalized.alerts_by_severity` | Missing counts fall back to 0; empty chart is empty | Real persisted alerts |
| Traffic Trend | `normalized.traffic_history` | No samples displays awaiting/no-history text | Real persisted history |
| Interfaces | `normalized.interface_summary` and `interfaces` | Counts fall back to 0; missing metric values remain N/A | Real latest interface state |
| SNMP Monitoring / Polling KPI | `normalized.polling` | Counts nullish-fallback to 0; success gauge shows N/A when no eligible denominator | Real PollingHistory classification; unsupported/no-data excluded from genuine failure rate |
| Network Information/topology | `normalized.network` | Null unsupported entries remain null; counts display available inventory | Real persisted topology/inventory summaries |
| Recent device/activity table | `devices`, `events`/device fields | Empty arrays show no devices/activity | Real device and event data |

The Dashboard type and consumer agree on `normalized.polling`. The backend’s polling object contains successful, unsupported, no-data, failed, unknown, total, rate, timestamps, compatibility counts, and job counts.

## Polling labels

The backend exposes `active_jobs`, `configured_jobs`, and `enabled_jobs` as counts of enabled `MonitoringConfig` rows for compatibility/summary purposes. The Dashboard panel displays `configured_jobs` under the label `CONFIGURED POLLING JOBS`; it does not display `active_jobs` as an active APScheduler count. Live scheduler registration is exposed separately by the service status as `registered_jobs` and `registered_job_ids`.

Given 26 enabled configs, 24 RUNNING configs, and 2 NOT_SUPPORTED configs, the value 26 is honest only when labeled configured/enabled polling jobs. It must not be interpreted as 26 executing APScheduler jobs. Current UI labeling is therefore acceptable with a semantic distinction, though the presence of legacy `active_jobs` in the API is a potential contract-label hazard for future consumers.

## Read side effects and duplicate requests

There is a proven Dashboard read-path side effect. `Dashboard.load()` calls `getOverview()`, and if `snapshot.services.snmp_polling.running` is false, calls `startPollingService()` (`POST /monitoring/polling/start`) and then calls `getOverview()` again. This remains in source and violates strict side-effect-free Overview loading, although current runtime is healthy and the branch is not normally taken.

The Dashboard also installs one `setInterval` per mount/range effect at 30 seconds, with cleanup. There is no React Query Overview request in this page and no second Overview interval found in the audited Dashboard source. When the scheduler is reported stopped, one Dashboard load intentionally produces two Overview GETs plus one start POST; when running, it produces one GET per interval. This is a proven conditional duplicate request, tied to the side-effect recovery branch. No separate duplicate scheduler/service request was found.

## Cache and refresh

Backend overview caching has a 10-second process-local cache and Redis cache key `nms:overview:v1:hours:{hours}`. Redis cache helpers are fail-open; cache reads/writes do not start polling or mutate database state. The frontend API client has a 30-second GET cache and sessionStorage backing for GET responses. Dashboard refreshes every 30 seconds while visible and refetches on range changes.

Displayed data can therefore lag current runtime by roughly the backend cache window plus frontend cache window, depending on cache hits. A stale response schema is not preserved indefinitely: cache entries have TTLs, though an already cached old response can remain until expiry or explicit client/server cache invalidation. The source contract is understandable but browser acceptance should verify cache invalidation/deployment behavior.

## Acceptance matrix

| SECTION | SOURCE | REAL DATA | SEMANTICS CORRECT | SIDE EFFECT FREE | STATUS | REMAINING ISSUE |
|---|---|---:|---:|---:|---|---|
| Device health | derived `summary.health_counts`/device health | PASS | PASS | PASS | PASS | Browser confirmation |
| Realtime ICMP | service state from live engine | PASS | PASS | PASS | PASS | None source-level |
| SNMP scheduler status | live app scheduler/lease state | PASS | PASS | PASS | PASS | None source-level |
| Polling KPI | `PollingHistory` → `normalized.polling` | PASS | PASS | PASS | PASS | Configured-vs-registered label distinction |
| Current traffic | fresh deterministic LatestInterface rows | PASS | PASS | PASS | PASS | None source-level |
| Traffic history | InterfaceStatistic history | PASS | PASS | PASS | PASS | Cache lag possible |
| Alerts/events | persisted alert/event queries | PASS | PASS | PASS | PASS | None source-level |
| Topology/network | persisted normalized summaries | PASS | PASS | PASS | PASS | Browser confirmation |
| Overview loading/recovery | Dashboard GET plus conditional start POST | PASS | PASS | FAIL | FAIL | Read path has scheduler-start side effect |
| Cache/refresh | backend + frontend TTLs and interval | PASS | PASS WITH LABEL ISSUE | PASS | PASS WITH LABEL ISSUE | Possible short-lived stale/schema cache |

## Acceptance conclusion

The source contract is complete for the verified health, ICMP, scheduler, traffic, and polling KPI data. The remaining source issue is the Dashboard’s conditional `/monitoring/polling/start` mutation during a read, plus the need to preserve the configured-versus-registered job label distinction. These are not current scheduler failures. Browser acceptance remains required for rendered values, cache behavior, and absence/presence of the conditional recovery request in the healthy state.

OVERVIEW SOURCE CONTRACT COMPLETE: YES
REAL DEVICE HEALTH SOURCE: YES
REAL ICMP SOURCE: YES
REAL SNMP POLLING SOURCE: YES
REAL TRAFFIC SOURCE: YES
POLLING KPI POPULATED: YES
POLLING KPI CORRECT PATH: normalized.polling
POLLING KPI FAILURE SEMANTICS CORRECT: YES

OVERVIEW READS SIDE-EFFECT FREE: NO
SIDE-EFFECTING READ FOUND: `Dashboard.tsx:Dashboard.load()` conditionally calls `startPollingService()` (`POST /monitoring/polling/start`) when Overview reports scheduler stopped
DUPLICATE REQUEST ISSUE FOUND: YES

26 ENABLED VS 24 REGISTERED EXPLAINED: YES
ACTIVE JOB LABEL HONEST: YES
LABEL FIX REQUIRED: NO

CACHE CONTRACT ACCEPTABLE: YES

SOURCE ACCEPTANCE: PASS WITH ISSUES
REMAINING SOURCE ISSUES: Conditional Dashboard start mutation during Overview loading; conditional duplicate GET/POST sequence when scheduler is reported stopped; configured/enabled counts must not be interpreted as registered APScheduler jobs
RUNTIME/BROWSER ACCEPTANCE REQUIRED: YES
SAFE TO FREEZE AFTER BROWSER ACCEPTANCE: YES

CODE CHANGED: NO
DATABASE CHANGED: NO
SCHEDULER CHANGED: NO
REDIS CHANGED: NO
SNMP CHANGED: NO
ICMP CHANGED: NO
