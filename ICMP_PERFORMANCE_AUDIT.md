# ICMP Performance Audit

## Current flow

Stored devices (or an explicit discovery-monitoring request) enter `MonitorEngine` through `discovery_routes.py`. `get_engine()` returns a process-local singleton. `MonitorEngine._ensure_loop()` starts one daemon thread; `_loop()` snapshots registered IPs every 15 seconds, creates a `ThreadPoolExecutor(max_workers=min(len(ips), 20))`, and submits one `_ping_one` job per IP. `_ping_one()` calls the system `ping` executable, parses stdout/return code into reachability and RTT, updates the in-memory `MonitoredDevice`, then calls `_persist_ping_result()` when a database device id exists. Persistence writes `DeviceMetric`, updates `Device.last_seen/status/cumulative uptime/downtime`, optionally writes `DeviceStatusHistory`, and on an offline transition calls `create_offline_alert()`. The API exposes JSON status and an SSE stream (`discovery_routes.py`); SSE waits in `run_in_executor` on the monitor event, so it does not directly block the async loop.

There is also a separate synchronous manual path: `routes.py` → `run_monitoring_check()` → `services/monitoring.py` → `services.discovery._ping()` for each selected device → one `DeviceMetric` per device and status handling → route-level commit. It is not the realtime loop.

## Ping execution

- Implementation: `subprocess.run`, not raw sockets or a persistent ping library (`realtime_monitor._ping`; the manual path has a duplicate helper in `services/discovery.py`).
- Every sample launches a new OS `ping` process, with one packet (`-c 1` Linux/macOS, `-n 1` Windows).
- Default timeout is 1,000 ms. The subprocess timeout is `timeout_s + 2`, therefore up to 3 seconds for the realtime helper; platform ping timeout is at least one second.
- Realtime interval is 15 seconds (`PING_INTERVAL`), one cycle waits for all submitted jobs and then sleeps the remaining interval.
- Concurrency is bounded per cycle at 20 threads, but the executor is created and destroyed on every cycle. There is no global semaphore across processes or across the separate manual endpoint.
- A cycle does not overlap itself inside one `MonitorEngine` because `_loop()` waits on all futures. Multiple application processes can each have an independent singleton and loop.

## Persistence and alerts

For each realtime ping with a `device_id`, `_persist_ping_result()` opens a fresh SQLAlchemy `SessionLocal` session, performs one `Device` lookup, adds one `DeviceMetric`, and commits once. On a confirmed status transition it additionally adds a `DeviceStatusHistory`, updates device counters/status, and for offline transitions `create_offline_alert()` performs one active-alert lookup, may flush a new alert and incident work, then the outer helper commits once. Warm-up samples with in-memory status `unknown` still commit the metric/device update and return. Exceptions rollback and close the session.

Thus the normal per-sample baseline is approximately one SELECT plus one commit, with one extra alert SELECT and alert-side work on an offline transition. Metrics are row-per-ping and can grow at `devices × (60/15)` rows per minute. The manual path queries all monitored devices once, performs one ping per device serially, adds metrics/status changes, flushes, and its API caller commits once; it has no per-device commit inside the loop.

## Lifecycle

`start_device()` and `start_all()` deduplicate by IP under a lock; `discovery_routes.py` also has an in-flight start set for the single-device endpoint. `stop_device()`/`stop_all()` remove registry entries, but do not join the daemon thread or set `_stop_event`; an empty engine thread remains alive waiting in two-second intervals. `get_engine()` is process-local. There is no startup restoration of persisted monitoring devices, no durable task identity, and no cross-process duplicate prevention. Application restart therefore loses the in-memory registry and does not restore realtime monitors automatically. `kill-all` clears the registry but does not terminate the loop thread.

## Bottlenecks

### HIGH

1. `hardik/backend/services/realtime_monitor.py`, `_ping()` — launches a new blocking OS process for every sample. Process creation plus executable startup dominates short ICMP probes and consumes a thread while waiting; timeout can reach three seconds. Safest optimization: use a bounded, reusable ping executor/process strategy while preserving packet, timeout, and status semantics.
2. `hardik/backend/services/realtime_monitor.py`, `_persist_ping_result()` — one synchronous database session/query/commit for every ping and one metric row per sample. This adds transaction latency and connection churn at 15-second cadence. Safest optimization: batch metric writes in a bounded persistence interval while keeping status transitions transactional.
3. `hardik/backend/services/realtime_monitor.py`, `_loop()` — constructs a new `ThreadPoolExecutor` each cycle. Repeated worker creation/destruction adds overhead and can amplify resource churn with many devices. Safest optimization: retain one bounded executor for the engine lifecycle.

### MEDIUM

4. `hardik/backend/services/realtime_monitor.py` + `services/alerting.py` — status transitions perform a device read and offline alert lookup in the ping worker; synchronous DB/alert work increases tail latency and can hold monitor threads. Safest optimization: preload/serialize status persistence or move it to a bounded persistence worker without changing alert dedup rules.
5. `hardik/backend/services/realtime_monitor.py` and `discovery_routes.py` — process-local singleton prevents duplicates only within one process. Multi-worker deployments can run overlapping loops for the same device; restart restoration is absent. Safest optimization: add an explicit deployment-wide lease/ durable ownership check before starting loops.

### LOW

6. `_ping()` duplicates parsing/execution logic with `services/discovery._ping()`, increasing maintenance and making timeout behavior diverge. Safest optimization: consolidate behind one compatible helper after tests establish identical semantics.
7. Empty monitor registries leave the daemon thread alive, consuming a thread and periodic wakeups. Safest optimization: stop/join the loop when the registry becomes empty, with careful restart synchronization.

## Suspected findings

- OS process per ping: **TRUE**.
- DB write per sample: **TRUE** (`DeviceMetric`, normally committed immediately).
- Synchronous DB operations in async workflow: **PARTIAL**. Realtime persistence runs in a background thread; the SSE wait is offloaded. The manual monitoring route is synchronous. It is not an async database call path, but it is blocking work in monitor worker/API threads.
- Duplicate/overlapping ping loops: **POSSIBLE** across processes/restarts; prevented for duplicate IPs within one process.
- Status/alert DB queries per sample: **TRUE/PARTIAL**. Device lookup is per persisted sample; active-alert lookup occurs on each confirmed offline transition (deduplicated by query), not every successful sample.

## Conclusion

The first safe Python optimization is to reuse a bounded ping executor (and keep the current one-packet/timeout/status contract), followed by explicitly bounded metric persistence batching. A Go migration is not needed now.
