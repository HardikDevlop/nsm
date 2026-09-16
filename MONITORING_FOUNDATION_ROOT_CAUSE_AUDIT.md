# Monitoring Foundation Root-Cause Audit

**Scope:** Step 1 audit only. No monitoring semantics, collector behavior, or UI was changed. Findings below are from source inspection; no live NMS process/database was available in this workspace, so runtime claims are marked pending.

## Executive finding

The intermittent appearance that polling has stopped is plausibly explained by three competing foundations:

1. SNMP scheduling/polling state uses naive India-local timestamps (`now_ist()`), while the broader application uses naive UTC (`datetime.utcnow()`) and some collectors emit aware UTC ISO-8601 values. This makes comparisons, API interpretation, chart parsing, and freshness calculations ambiguous.
2. SNMP has persisted per-module jobs and polling history, but device health/status is not updated by the SNMP scheduler. Device status is primarily changed by the separate synchronous ICMP `run_monitoring_check()` path and by discovery/manual endpoints. A successful SNMP poll therefore does not establish the device `online` status, and a stopped poll does not automatically make it stale/offline.
3. Poll success/failure metadata is stored at module/config level, but there is no single device-level freshness/status authority with `last_success_at`, `last_failure_at`, and a computed stale state. Several APIs expose latest rows or `device.status` without an age guard.

## A. Lifecycle trace

| Stage | Evidence | Result |
|---|---|---|
| Device inventory | `hardik/backend/models/__init__.py` / device model; CRUD in `hardik/backend/api/routes.py` | Persisted device identity, `status`, `monitoring_status`, `last_seen`. |
| Enable monitoring | `hardik/backend/api/routes.py:1139`; SNMP routes around monitoring endpoints | Creates/updates `MonitoringConfig` and enables device/module polling. |
| Scheduler creation | `hardik/backend/services/snmp_polling.py:776-779` | Global `PollingScheduler`, APScheduler `AsyncIOScheduler`, worker count 8. |
| Scheduler startup | `hardik/backend/main.py` lifespan | Startup acquires `SchedulerLease`; only lease holder calls `get_polling_scheduler()`. |
| Job restoration | `snmp_polling.py:_load_jobs_from_db()` | Loads enabled configs whose status is `running`; reconstructs jobs after restart. |
| Job scheduling | `snmp_polling.py:_schedule_config()` | One DateTrigger job per `device_id:module_name`; `replace_existing=True`; next run persisted. |
| Job execution | `snmp_polling.py:_execute_poll_job()` | Semaphore limits concurrent jobs; synchronous worker path runs in `asyncio.to_thread`. |
| Duplicate protection | `hardik/backend/services/snmp_poll_guard.py`, called in `SNMPPoller.poll()` | Per device/module single-flight guard; scheduler job IDs also deduplicate. |
| SNMP collection | `snmp_polling.py:SNMPPoller.poll()` → `backend/snmp/collector.py:SNMPService.collect_domain` | Network collection runs in a thread; collector-specific timeout/retry behavior is delegated to SNMP implementation. |
| Normalization/persistence | `snmp_polling.py:_persist_*()` | Latest tables are updated and typed history rows are appended; `PollingHistory` records module outcome/duration/error. |
| Device status | `hardik/backend/services/monitoring.py:run_monitoring_check()` | ICMP result changes `Device.status` and `last_seen`; discovery endpoints also set status. SNMP scheduler does not appear to be the authority. |
| Alerts | `hardik/backend/services/alerting.py:create_offline_alert()` and SNMP threshold/interface alert calls | ICMP offline transitions create offline alerts; SNMP threshold/interface alerts are separate. Recovery exists for interface/alert paths, but no explicit polling-stale transition was found. |
| API | `hardik/backend/api/overview_routes.py`, `monitoring_data_routes.py`, `snmp_device_routes.py`, `routes.py` | APIs read device fields, latest tables, and polling history/config. Most timestamps are direct model serialization or `.isoformat()`. |
| Frontend | `figma design/src/hooks/useRealtimeData.ts` and page `useQuery` hooks | Shared hook uses `setInterval`; individual pages use React Query with inconsistent `staleTime`/refresh settings. Exact page-by-page runtime behavior remains pending. |

## B. Scheduler audit

| Check | Source evidence / conclusion |
|---|---|
| Created/started | `main.py` lifespan; `get_polling_scheduler()` creates and starts `AsyncIOScheduler`. |
| Silent stop | `_execute_poll_job()` catches errors and reschedules; however scheduler health is not persisted/heartbeated. A process/event-loop failure is only externally visible through service endpoint/runtime logs. **Partial.** |
| Restart survival | Enabled configs with `status == running` are restored on startup. Jobs themselves are in-memory and rebuilt. **Source PASS; runtime pending.** |
| Multiple workers | `SchedulerLease` is intended to ensure one lease holder, but deployment configuration and actual multi-worker behavior were not runtime verified. **Pending.** |
| Job IDs | `device_id:module_name`; replacement prevents duplicate in one scheduler. |
| Interval | `MonitoringConfig.interval_seconds`; defaults include 15s interfaces, 30s ARP/MAC, 60s CPU/memory/firewall, etc. |
| `max_instances` | Not explicitly configured on `add_job`; APScheduler default applies. The application semaphore is 8, but this is not equivalent to per-job `max_instances`. **Gap.** |
| Coalesce | Not explicitly configured. **Gap.** |
| Misfire grace | Explicitly 300 seconds. |
| Executor/thread limits | Application semaphore 8 plus `to_thread`; APScheduler executor settings are not explicitly configured. **Partial.** |
| Long-running poll | Guard prevents same device/module overlap; no explicit per-job timeout at scheduler layer. **Partial.** |
| DB sessions | Worker creates/closes sessions; poll releases the initial session before network I/O and opens a replacement for persistence. Broad exception paths rollback/close. **Source looks sound, runtime pending.** |
| Poll result table | Job/last-run fields exist in `MonitoringConfig`; duration/error exists in `PollingHistory`; no persisted `running` attempt/start/end duration row was found. Last run/next run cannot be fully reconstructed from one table. **Partial.** |

**Required runtime table:** `JOB, DEVICE, INTERVAL, LAST RUN, NEXT RUN, RUNNING, SUCCESS/FAIL, DURATION, ERROR` — **RUNTIME VERIFICATION PENDING**. The service endpoint in `overview_routes.py` exposes scheduler running/job counts, but no executed runtime snapshot was captured.

## C. SNMP vs ICMP reliability

| Dimension | SNMP | ICMP |
|---|---|---|
| Execution | APScheduler persisted module jobs → `SNMPPoller.poll()` → `SNMPService.collect_domain`. | `ICMPMonitor.check_many()` uses bounded `ThreadPoolExecutor`; separate `run_monitoring_check()` uses `_ping` sequentially over devices. |
| Timeout/retry | Collector-owned; not consistently surfaced by scheduler metadata. | `ICMPMonitor` has configured timeout and ping count; `run_monitoring_check()` has timeout_ms. |
| Concurrency | Semaphore 8 plus per device/module guard. | Bounded pool in `ICMPMonitor`; synchronous API monitoring path is sequential. |
| Latest/history | Module latest tables plus typed history and `PollingHistory`. | `DeviceMetric` rows; `last_seen` and `DeviceStatusHistory` on status changes. |
| Failure persistence | Config status/error and polling history; collector exception itself is returned as job failure but no device-level stale status. | Metric failure is persisted by `run_monitoring_check`; `last_seen` is only updated on success. |
| Single authority | None for device health: SNMP config status is module state, not device state. | Changes device status when this path runs, but it is not proven to be the only writer. |

## D. Device status authority and stale protection

Current observed authority is **CONFLICTING**:

- `Device.status` is changed by ICMP `run_monitoring_check()` (`online`/`offline`) and discovery/add-device paths.
- SNMP monitoring uses `MonitoringConfig.status` (`running`, `error`, `not_supported`, etc.) and `PollingHistory`, but does not appear to update `Device.status`.
- SNMP API health fields derive from `device.status` in `snmp_device_routes.py`, while module pages derive freshness from `polled_at`/`last_poll_at`.
- Overview APIs count `Device.status` directly and return latest persisted values.

No common age-based rule was found that changes `online` to `stale`/`unknown` when `last_seen` or latest poll is older than the monitoring interval. Thus a device can remain `online` in the database after monitoring stops. **STALE STATUS PROTECTION: FAIL.**

## E. Time/timezone matrix

| Field/path | DB format | API format | Frontend/parser | Finding |
|---|---|---|---|---|
| SNMP `MonitoringConfig` times | Naive `DateTime`; `now_ist()` strips tzinfo | `.isoformat()` without offset | Browser/parser cannot know it is IST | **Wrong/ambiguous.** |
| SNMP latest/history `created_at`, `polled_at` | Model default `snmp.py:now()` stores naive IST | `.isoformat()` without offset | Native Date parsing may treat as local time | **Wrong/ambiguous.** |
| Device `last_seen`, status history | Migration/model timestamps; writers use `datetime.utcnow()` in several paths | Direct Pydantic or `.isoformat()` | Browser conversion may apply local timezone | **Mixed.** |
| ICMP sample `timestamp` | JSON sample, not necessarily DB | Aware UTC ISO-8601 (`Z`/`+00:00`) | Native parser can convert correctly | **Correct in isolation.** |
| Overview `fetched_at` and many API fields | `datetime.utcnow()` naive | ISO string without offset | Refetch can replace displayed value | **Ambiguous.** |
| Knowledge/change/incident/APM/QoS routes | Naive `datetime.utcnow()` | Serialized without canonical offset | Shared frontend parsing | **Mixed.** |

Search confirms mixed use of `datetime.now(timezone.utc)`, `datetime.utcnow()`, and naive IST helpers. `Asia/Kolkata` is used in SNMP models/scheduler, but no universal API normalization layer was found. The reported “initially correct, later changes” symptom is consistent with endpoint refetch replacing an ambiguous timestamp that the browser parses under a different assumption. **DOUBLE TIMEZONE CONVERSION: PENDING** — source shows ambiguity, but no browser/runtime trace proves a double conversion.

## F. Freshness/staleness

Available: `MonitoringConfig.last_poll_at`, `next_poll_at`, `status`, `error_message`; `PollingHistory.created_at/status/duration/error`; latest metric `polled_at`; device `last_seen`.

Missing as a unified device contract: `last_success_at`, `last_failure_at`, `next_poll_at` at device level, explicit freshness enum, and a server-enforced stale age. APIs can return old latest values as if current. `PollingHistory` records not-supported as an outcome but normal exceptions are primarily config/error state. **FRESHNESS: PARTIAL/UNSAFE.**

## G. Frontend refresh audit

`figma design/src/hooks/useRealtimeData.ts` contains a recurring `setInterval(fetchData, refreshInterval * 1000)` and cleanup, while pages use React Query with differing `staleTime`, mount/focus options, and some explicit polling. Existing tests also assert `staleTime: 0` for topology refresh behavior. This creates a verified risk of duplicate fetch paths where both shared polling and page queries are active; exact affected pages and response race behavior require browser runtime capture. **FRONTEND REFRESH: PARTIAL; runtime race/old-response overwrite PENDING.**

## H. Database/history audit

Latest SNMP tables are separate from history tables, and interface history selects deterministic latest prior samples using `created_at` plus `id`. `PollingHistory` has device/collector/status/duration/error and indexed created time. However timestamps are mixed naive IST/UTC; no general unique poll ID, attempt start/end pair, or global ordering invariant was found. DeviceMetric history is queried by `created_at`; direct metric creation endpoints also exist. Duplicate timestamps are possible for concurrent/module writes, while id tie-breaking is not consistently visible in all APIs. **DB HISTORY: PARTIAL.**

## I. Alert dependency audit

ICMP offline transitions call `create_offline_alert`; alerting contains duplicate suppression and interface recovery helpers. SNMP threshold/interface alerts are generated during persistence and notification delivery is post-commit in the worker. There is no documented/common `MONITORING STALE` or `POLLING FAILED` device condition, and scheduler failure does not necessarily create an alert or resolve/recover device state. A stopped poll can therefore silently retain the last healthy device status. **ALERT TRANSITIONS: PARTIAL/FAIL for polling stoppage.**

## J. Runtime observability

The `/api/v1/monitoring/services` implementation exposes scheduler running state and job count, and per-module status APIs expose config timestamps/error. Logs include job IDs and failure text. Operators still cannot reliably answer, from one authoritative record: last successful device poll across modules, last failed attempt with start/end/duration, persistence success, or freshness state. No runtime capture was available. **POLLING OBSERVABILITY: PARTIAL.**

## Required final summary

| Area | Result |
|---|---|
| SCHEDULER | PARTIAL |
| SNMP POLLING | PARTIAL |
| ICMP POLLING | PARTIAL |
| POLL RESTORE AFTER RESTART | PASS (source only; runtime pending) |
| DUPLICATE POLL PROTECTION | PASS (source only; runtime pending) |
| DEVICE STATUS AUTHORITY | CONFLICTING |
| STALE STATUS PROTECTION | FAIL |
| DATABASE TIMESTAMPS | MIXED |
| API TIMESTAMPS | MIXED |
| IST DISPLAY | PARTIAL |
| DOUBLE TIMEZONE CONVERSION | PENDING |
| FRONTEND REFRESH | PARTIAL |
| DB HISTORY | PARTIAL |
| ALERT TRANSITIONS | PARTIAL |
| POLLING OBSERVABILITY | PARTIAL |

## Root causes

1. No canonical UTC timestamp contract: naive IST, naive UTC, and aware UTC coexist.
2. No single device health/freshness authority; ICMP device status and SNMP module status are separate state machines.
3. Scheduler/config/history metadata is not a complete poll-attempt ledger and has no server-enforced stale-status transition.
4. Shared frontend interval polling and page-level React Query refresh policies can overlap; runtime race impact is not yet measured.

## P0 issues

- A stale device can remain `online` after polling stops; operators may receive a false healthy state.
- Mixed timestamp semantics can make freshness, ordering, and IST display incorrect.

## P1 issues

- Add explicit scheduler heartbeat and a single poll-attempt observability view.
- Define and enforce per-job `max_instances`/coalescing policy and capture actual start/end/failure metadata.
- Consolidate frontend refresh ownership and verify race/visibility behavior.
- Add explicit polling-failed/stale alert transition and recovery semantics.

## Files/functions responsible

- `hardik/backend/main.py:lifespan()` — startup/shutdown and scheduler lease.
- `hardik/backend/services/snmp_polling.py:PollingScheduler`, `SNMPPoller.poll()`, `_persist_*()` — SNMP scheduling, collection, persistence, and rescheduling.
- `hardik/backend/services/snmp_poll_guard.py` — single-flight protection.
- `hardik/backend/services/monitoring.py:run_monitoring_check()` — ICMP device status authority currently in use.
- `hardik/monitoring_modules/icmp_monitor.py:ICMPMonitor` — bounded ICMP sample collection.
- `hardik/backend/models/snmp.py:now()` — naive IST SNMP timestamp default.
- `hardik/backend/api/overview_routes.py`, `monitoring_data_routes.py`, `snmp_device_routes.py`, `routes.py` — latest/status/history API projections.
- `hardik/backend/services/alerting.py` and `hardik/backend/incidents/service.py` — alert/recovery/incident coupling.
- `figma design/src/hooks/useRealtimeData.ts` and page `useQuery` definitions — frontend refresh behavior.

## Safe to start page-by-page verification

**NO.** First establish the canonical timestamp and freshness/status contract, or page verification will produce misleading results. Runtime scheduler/database/browser verification is also still pending.

