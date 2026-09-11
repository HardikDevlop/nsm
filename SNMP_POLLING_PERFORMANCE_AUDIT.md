# SNMP Polling Performance Audit

## Scope and method

This is a static, read-only audit of the current scheduled SNMP polling and persistence path. No code, API, schema, frontend, or scheduler behavior was changed. Counts below distinguish a **logical operation** (one call to `SNMPClient.get()` or `walk()`) from SNMP protocol requests. One logical walk issues repeated GETBULK PDUs (up to 25 returned rows per request), or repeated GETNEXT PDUs after a GETBULK error, until the subtree ends, 2,000 rows are reached, or the 120-second operation deadline is reached. Therefore an exact wire-PDU count is data- and agent-dependent and cannot be a fixed static number.

## 1. Exact current flow

1. A per-device/per-module `MonitoringConfig` row is loaded by `PollingScheduler._load_jobs_from_db()` and registered as a one-shot APScheduler `DateTrigger` job named `<device_id>:<module>`.
2. APScheduler calls `PollingScheduler._execute_poll_job()`. Its process-wide asyncio semaphore admits at most 8 scheduled jobs in the actual singleton configuration.
3. `_execute_poll_job()` sends `_poll_in_worker()` to asyncio's default thread pool. That worker creates a DB session and runs `SNMPPoller.poll()` in another event loop via `asyncio.run()`.
4. `SNMPPoller.poll()` queries device, credential, and capability rows; closes the DB session before network I/O; acquires a process-local `(device,module)` single-flight guard; creates `SNMPService`; and invokes `collect_domain()` through another `asyncio.to_thread()`.
5. `SNMPService.collect_domain()` always makes one six-OID identity GET, detects vendor/type, then walks the roots assigned to that module sequentially. Collectors do not perform SNMP themselves; they consume the accumulated raw dictionary.
6. Every `SNMPClient.get()` creates a coroutine, submits it to the dedicated eight-thread `_snmp_executor`, creates a fresh event loop, `SnmpEngine`, authentication object, UDP target and context, executes one GET, cancels remaining loop tasks, and closes the loop. Every logical walk repeats that entire construction and uses one engine only for the successive GETBULK/GETNEXT PDUs within that root.
7. `NormalizationLayer.normalize()` converts the raw OID dictionary to `RawDevice`; `build_registry()` maps available OIDs; the selected collector produces a normalized `CollectorResponse`.
8. A fresh SQLAlchemy session runs `_persist_results()`: capability-detail update; module-specific latest/history work for CPU, memory, storage, interfaces, or environment; alert evaluation; one `PollingHistory` insert; and one commit.
9. Back in `_execute_poll_job()`, another session reads the newest polling-history row, updates its duration and the monitoring config, commits, calculates the next run, and `_schedule_config()` commits the next-poll timestamp again before adding the next one-shot job.
10. APIs such as `api/monitoring_data_routes.py:get_monitoring_data()` read the latest/history tables and cached `DeviceCapabilities.capability_detail`; they do not initiate this scheduled live poll.

## 2. SNMP operation inventory

Every module invocation includes **1 logical GET containing 6 identity scalar OIDs**. The additional logical walks are:

| Module | GET calls | Logical WALK calls | Walk roots |
|---|---:|---:|---|
| system | 1 | 0 | — |
| cpu | 1 | 1 | hrProcessorTable |
| memory | 1 | 1 | hrStorageTable |
| storage | 1 | 1 | hrStorageTable |
| interfaces | 1 | 2 | ifTable, ifXTable |
| environment | 1 | 2 | ENTITY-MIB, ENTITY-SENSOR-MIB |
| vlan | 1 | 1 | static VLAN table |
| lldp | 1 | 1 | LLDP remote table |
| cdp | 1 | 1 | CDP cache table |
| routing | 1 | 1 | IPv4 route table |
| arp | 1 | 1 | ipNetToMediaTable |
| mac_table | 1 | 3 | BRIDGE FDB, Q-BRIDGE FDB, bridge-port map |
| inventory | 1 | 1 | ENTITY-MIB |
| topology | 1 | 6 | LLDP, ARP, BRIDGE FDB, ifTable, ifXTable, routes |
| health | 1 | 0 | — |
| firewall | 1 | 0 | — |
| wireless | 1 | 0 | — |

For one run of all 17 configured modules, this is **17 logical GETs and 22 logical walks**. It repeatedly retrieves the same six identity OIDs 17 times. Shared roots are independently recollected: hrStorage twice; ENTITY twice; LLDP twice; ARP twice; BRIDGE FDB twice; ifTable twice; ifXTable twice; and routes twice. This is duplication between module jobs, not within collector classes. Jobs for different modules of the same device may overlap because the guard conflicts only on the same module (or `__full__`).

Walk roots inside one `collect_domain()` are strictly sequential (`for ...: client.walk(...)`). Different scheduled jobs can run concurrently, including different modules for the same device.

Wire-level request count per successful bulk walk is approximately `ceil(returned_rows / 25)` plus a possible terminating/out-of-subtree request; exact behavior depends on the agent response. A GETBULK error switches that root to GETNEXT, potentially making the remainder one request per returned row. The hard limit is 2,000 accepted rows, but the 120-second operation timeout is normally the effective limit.

### Runtime construction and concurrency

- `backend/snmp/client.py:_run_in_thread()` creates and closes a new asyncio event loop for every logical GET and every root walk.
- `SNMPClient.get()` creates a new `SnmpEngine`, auth object, UDP target, and context per GET.
- `SNMPClient.walk()` creates the same objects per root, reusing them only across requests within that single root.
- There is no engine, transport, target, session, or event-loop reuse across roots or module polls.
- `_snmp_executor` has 8 threads. Separately, asyncio's default executor is used twice in the scheduler/poller nesting and has no explicit project setting here.
- `get_polling_scheduler()` explicitly constructs `PollingScheduler(worker_count=8)`. The class constructor default is 4, but it is not the active singleton value.
- The active scheduler semaphore limit is 8 jobs. Each admitted logical operation subsequently competes for the separate eight-thread SNMP executor.
- Duplicate prevention is process-local only. It prevents the same `(device,module)` and full-vs-module overlap, but permits different modules on one device to run concurrently and duplicate roots. APScheduler job IDs prevent two registered jobs with the same device/module in one scheduler. The Redis scheduler lease aims to select one scheduler process, but the poll guard itself is not distributed.

### Timeout and retry behavior

- Per SNMP request timeout: 3 seconds.
- Retries: 1, so a nonresponsive protocol request may consume roughly two request-timeout windows.
- Per logical GET or root walk deadline: 120 seconds, enforced both in the worker coroutine and on the future.
- Root walks are sequential, so worst-case domain duration is additive: roughly 120 seconds per root, plus the identity GET. Topology has six roots and can therefore occupy a scheduler slot for roughly 12 minutes in the worst case; MAC table about 6 minutes; two-root modules about 4 minutes. Individual request retry delays amplify each walk, while the outer deadline bounds each root rather than the whole domain poll.
- `future.cancel()` cannot stop a thread that is already executing; the internal asyncio timeout is the primary cancellation mechanism.

## 3. Persistence and query behavior

### Commits per normal successful scheduled poll

There are normally **3 `COMMIT`s**:

1. `SNMPPoller._persist_results()` commits capability/latest/history/alerts/polling-history.
2. `PollingScheduler._execute_poll_job()` commits the corrected polling duration plus monitoring status/timestamps.
3. `PollingScheduler._schedule_config()` commits `next_poll_at` again before registering the next date job.

The third commit persists a value already set before commit 2 in the normal success path, so it is redundant. Alert helper functions use flushes but do not independently commit; their changes join commit 1. Unsupported polls still write capability and polling history and commit. Early failures before `_persist_results()` produce no polling-history row.

### Write shapes

- CPU/memory: query-or-insert one latest row, optionally insert one statistic row, plus one polling-history row.
- Storage: per volume, query latest row then add/update it and add one history row. This is row-by-row ORM work and an N+1 SELECT pattern; SQLAlchemy may executemany some flushes, but the code does not issue an explicit bulk upsert/insert.
- Interfaces: related interfaces, previous statistics, and latest rows are preloaded in set queries, which avoids the older primary persistence N+1. It then adds/updates ORM objects row-by-row and inserts one history row per interface. `flush()` is required to obtain IDs. However alert evaluation subsequently queries `Interface` once per returned interface, recreating an N+1 read; each up interface may also make one or two alert-resolution queries.
- Environment: per sensor, query latest row then add/update latest and add history. This is an N+1 SELECT and row-by-row ORM path.
- All modules: query capability and add exactly one `PollingHistory` row per persisted module poll.
- Only CPU, memory, storage, interfaces, and environment have dedicated latest/statistic writes. Other module data lives in `DeviceCapabilities.capability_detail` plus polling history.
- Alerts: each threshold candidate queries for an existing active alert. A new alert flushes, may invoke incident processing, queries recipients when not configured, creates notifications, and can synchronously perform SMTP work inside the persistence worker. Interface recovery performs alert and incident-related queries. These add latency before commit 1.

### Duplicate queries and API path

- Device is queried once in `poll()`; credentials and capabilities are separate queries. Capability is queried again in `_persist_results()`.
- `_execute_poll_job()` re-queries newest `PollingHistory` and `MonitoringConfig`; `_schedule_config()` re-queries capability and performs another commit.
- The monitoring API issues separate queries for device, capabilities, configs, and each requested latest/history module. This is query-per-module rather than a relational N+1 over rows, but query count grows with requested modules. It also repeatedly opens and parses `/tmp/snmp_sample_data.json` once for each of several modules; this is an API-side inefficiency, not polling network latency.

## 4. Bottlenecks and safe optimizations

### HIGH

1. **Duplicated full-root collection across module schedules**
   - File/function: `backend/snmp/collector.py:_DOMAIN_WALKS`, `SNMPService.collect_domain()`; `backend/services/snmp_polling.py:PollingScheduler`.
   - Current behavior: independently scheduled modules always repeat identity GET and overlapping roots; modules on the same device can overlap.
   - Why slow: duplicate device packets, repeated table transfer/parsing, engine creation, and timeout exposure; topology is especially duplicative.
   - Safest optimization: add a short-lived per-device raw-poll cache/single-flight keyed by root and credential generation so due module collectors share one recent identity/root result without changing collector/API contracts.

2. **Sequential root walks with a per-root 120-second deadline**
   - File/function: `backend/snmp/collector.py:collect_domain()`.
   - Current behavior: roots are walked one after another.
   - Why slow: latency and timeouts add linearly; topology has six roots.
   - Safest optimization: execute the already independent roots concurrently with a small per-device bound, then merge their dictionaries in deterministic root order.

3. **Fresh engine/event loop/transport for every GET and root**
   - File/function: `backend/snmp/client.py:_run_in_thread()`, `SNMPClient.get()`, `SNMPClient.walk()`.
   - Current behavior: every logical operation constructs and tears down an event loop, `SnmpEngine`, auth, UDP target, context, dispatcher state, and tasks.
   - Why slow: substantial setup/teardown and thread handoff overhead, especially for empty/fast tables and frequent module polls; no SNMPv3 engine/session state reuse.
   - Safest optimization: give each dedicated SNMP worker a long-lived event loop and engine, with serialized ownership and explicit shutdown, while keeping current synchronous client signatures.

4. **Timeout amplification**
   - File/function: `backend/snmp/client.py:SNMPClient.walk()`; `backend/snmp/collector.py:collect_domain()`.
   - Current behavior: 3-second request timeout with one retry occurs repeatedly inside a 120-second deadline independently for every sequential root.
   - Why slow: unsupported or lossy roots can monopolize one of eight scheduler slots for minutes and push short-interval jobs late.
   - Safest optimization: impose one domain-poll deadline and divide its remaining budget among roots, preserving the current request timeout/retry defaults initially.

5. **Persistence N+1 paths for storage, environment, and interface alerts**
   - File/function: `SNMPPoller._persist_storage()`, `_persist_environment()`, `_evaluate_alerts()`.
   - Current behavior: one latest-row SELECT per volume/sensor and one interface SELECT per interface during alert evaluation, followed by alert lookups.
   - Why slow: database round trips grow linearly with row count every poll.
   - Safest optimization: preload latest storage/sensor/interface and active-alert rows into dictionaries with set-based queries, then retain the existing ORM writes and transaction.

### MEDIUM

6. **Three commits per successful scheduled poll**
   - File/function: `SNMPPoller._persist_results()`, `PollingScheduler._execute_poll_job()`, `_schedule_config()`.
   - Current behavior: persistence, status/duration, and scheduling commit separately.
   - Why slow: three transaction/fsync boundaries and extra session/query work; history duration is immediately rewritten.
   - Safest optimization: pass the measured duration already available in `poll()` and persist result, history, and config scheduling metadata in one owning session/transaction; as the smallest first step, remove `_schedule_config()`'s redundant commit when its caller already committed the same `next_poll_at`.

7. **Nested default-thread-pool handoffs around an eight-thread SNMP pool**
   - File/function: `_database_worker`, `_execute_poll_job()`, `_poll_in_worker()`, `SNMPPoller.poll()`, `_run_in_thread()`.
   - Current behavior: scheduler → default executor → new event loop → default executor → dedicated SNMP executor → new event loop.
   - Why slow: excess scheduling, thread occupancy, and harder cancellation/backpressure.
   - Safest optimization: flatten poll execution so each admitted scheduler task delegates once to a session-owning worker, with the SNMP loop owned by the dedicated executor.

8. **Unbounded table-history reads for previous interface counters**
   - File/function: `SNMPPoller._persist_interfaces()`.
   - Current behavior: queries all matching `InterfaceStatistic` rows ordered descending, then keeps only the first per interface in Python.
   - Why slow: history volume grows continuously, so transferred/scanned rows increase over time.
   - Safest optimization: query only the latest row per interface using a window function/distinct-on/subquery while preserving schema.

9. **Synchronous alert/notification work in the poll persistence critical path**
   - File/function: `_evaluate_alerts()` and `backend/services/alerting.py:create_threshold_alert()`, `_notify()`.
   - Current behavior: deduplication, incident work, recipient lookup, notification creation, and possible SMTP happen before poll persistence commits.
   - Why slow: database and external mail latency extend poll slot occupation and transaction duration.
   - Safest optimization: persist alert/notification intent in the same transaction and deliver notification asynchronously after commit.

### LOW

10. **Repeated capability/config/history queries and duration rewrite**
    - File/function: `SNMPPoller.poll()`, `_persist_results()`, `PollingScheduler._execute_poll_job()`, `_schedule_config()`.
    - Current behavior: capability is read multiple times; the just-created history row is looked up and updated; config is reloaded.
    - Why slow: fixed extra database round trips per poll.
    - Safest optimization: carry already-loaded state and final measured duration through one persistence unit.

11. **Collector/registry/normalizer reconstruction per module**
    - File/function: `SNMPService.__init__()`, `collect_domain()`.
    - Current behavior: a service, normalizer, detector and registry are rebuilt for every module job.
    - Why slow: modest CPU/allocation overhead compared with network waits.
    - Safest optimization: reuse immutable detector/normalizer instances and cache vendor registry metadata per device with invalidation.

## 5. Verification of supplied audit findings

| Finding | Verdict | Evidence |
|---|---|---|
| Repeated `SnmpEngine`/event-loop construction | **TRUE** | Both are created once per GET and once per root walk in `client.py`. |
| Sequential OID-root walks | **TRUE** | `collect_domain()` loops synchronously over roots. |
| Duplicated module/device walks | **TRUE** | Independently scheduled modules share many roots and identity GETs; no per-device/root cache exists. |
| Only 4 concurrent scheduler workers | **FALSE for the active singleton** | Constructor default is 4, but `get_polling_scheduler()` passes 8; active semaphore is therefore 8. |
| Timeout amplification | **TRUE** | Retry cost accumulates inside each walk and 120-second deadlines accumulate sequentially per root. |
| Multiple ORM commits | **TRUE** | Normal successful scheduled poll has three commits; alert helpers flush within the first transaction. |

## 6. Conclusions

The collectors themselves are CPU-only consumers of one raw dictionary and are not the main bottleneck. The dominant costs are architectural: independently scheduled module jobs recollect shared OIDs, roots are sequential, and every logical operation rebuilds the async SNMP runtime. Persistence then adds growing history reads/N+1 queries and three transaction commits. A Go migration is not warranted before eliminating these algorithmic and lifecycle costs in the current implementation.

The first safe optimization should be: **reuse one per-device, short-lived identity/root collection result across module jobs due in the same polling window, keyed by device, root OID, and credential generation, while leaving collector outputs and persistence contracts unchanged.** This directly removes the largest amount of network work and makes later concurrency tuning safer.
