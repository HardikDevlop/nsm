# Final NMS Performance Report

**Validation date:** 2026-08-29  
**Repository commit inspected:** `beb29b48470dab7bc4e090356fa5f036a7659472`  
**Scope:** Existing NMS only. No application code or production behavior was changed for this validation.

## Executive Summary

- The existing bounded scalability harness completed simulated SNMP workloads at **100, 500, 1,000, 2,500 and 5,000 operations**.
- The 5,000-operation simulator run completed with **5,000/5,000 successes**, simulated SNMP p50 **1.554 ms**, p95 **1.637 ms**, p99 **17.452 ms**, and simulated backlog peak **4,950**.
- These are **simulated operation measurements**, not proof that the NMS can poll 5,000 real devices. No real-device SNMP, live scheduler, database, API, flow receiver or browser runtime test was possible.
- Frontend unit tests and production build passed. PostgreSQL, Redis, backend API and frontend dev server were not listening on their expected local ports.

## Evidence and Commands

| Area | Command / evidence | Result |
|---|---|---|
| Simulated scale | `hardik/.venv/bin/python -m tools.progressive_scalability --api-path '' --output /tmp/final-scalability-results.json` | Passed all five points; zero simulated failures |
| Simulator resource envelope | `/usr/bin/time -v` around the command above | 0.50 s wall time, 0.30 s user CPU, 0.01 s system CPU, 36,400 KB maximum RSS |
| Backend performance/regression coverage | `hardik/.venv/bin/python -m pytest tests/test_loadtest_framework.py tests/test_flow_ingestion.py tests/test_sflow_ingestion.py tests/test_vendor_flow_compatibility.py tests/test_scheduler_lifecycle.py tests/test_snmp_devices_performance.py tests/test_latest_metrics_query_count.py -q` | **23 passed in 1.25 s** |
| Frontend regression coverage | `npm test -- --run` | **16 passed, 0 failed** |
| Frontend production build | `/usr/bin/time -f ... npm run build` | Passed in 0.499 s Vite build time; `dist` 2.4 MB, 98 asset files; timed process max RSS 781,320 KB |
| PostgreSQL | `pg_isready -h 127.0.0.1 -p 5432` | No response |
| Redis | `pg_isready -h 127.0.0.1 -p 6379` | No response; Redis telemetry unavailable |
| API | `curl --max-time 3 http://127.0.0.1:8000/api/v1/health` | Connection refused |
| Frontend runtime | `curl --max-time 3 http://127.0.0.1:5173/` | Connection refused |

## Progressive Simulated Workload

The harness uses `SimulatedSNMPWorkload`; it does not call collectors or devices. It runs 50 concurrent simulated workers with a configured 1 ms operation time and zero configured failure rate.

| Simulated devices/operations | Success | Duration | Throughput | p50 | p95 | p99 | Peak simulator backlog | Process RSS after |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 100/100 | 0.005 s | 21,875.381/s | 1.737 ms | 1.812 ms | 1.842 ms | 50 | 22.4 MiB |
| 500 | 500/500 | 0.022 s | 22,619.077/s | 1.539 ms | 2.392 ms | 2.411 ms | 450 | 23.5 MiB |
| 1,000 | 1,000/1,000 | 0.045 s | 22,192.677/s | 1.564 ms | 3.387 ms | 3.404 ms | 950 | 24.8 MiB |
| 2,500 | 2,500/2,500 | 0.115 s | 21,657.615/s | 1.564 ms | 1.631 ms | 9.370 ms | 2,450 | 28.6 MiB |
| 5,000 | 5,000/5,000 | 0.234 s | 21,343.878/s | 1.554 ms | 1.637 ms | 17.452 ms | 4,950 | 35.5 MiB |

**Interpretation:** The simulated harness remained stable through 5,000 operations. The increasing queued-operation count is expected from submitting all operations at once and is not the production scheduler backlog. The validated real-device target count is therefore **not established**.

## Required Metric Status

| Metric | Status | Measurement |
|---|---|---|
| API p50/p95/p99 | **Blocked** | No backend process was reachable at `127.0.0.1:8000`; no latency samples were counted as API results. |
| Database query count | **Blocked** | PostgreSQL was unavailable; no live query-count or `pg_stat_statements` delta could be collected. The query-count regression test passed as code-level coverage only. |
| Database connections/load | **Blocked** | PostgreSQL was unavailable. |
| Real SNMP polling | **Untested** | No production or lab devices were contacted. The simulator is explicitly not a collector test. |
| Flow ingestion throughput/backlog | **Untested** | Parser and bounded-queue tests passed, but no live UDP/TCP receiver or database persistence workload was running. |
| Scheduler backlog | **Blocked** | Backend/database/Redis were unavailable. The simulator backlog must not be substituted for persisted monitoring-job backlog. |
| Frontend load time | **Partially measured** | Production bundle built successfully; no browser runtime was available, so navigation, network waterfalls, dashboard render time and interaction latency were not measured. |
| Resource usage | **Partially measured** | Simulator and build-process RSS/CPU were measured. NMS API, worker, scheduler, PostgreSQL and Redis resource usage was not measurable while services were down. |

## Regression Results

The focused validation suite passed **23 tests**, covering:

- load-runner percentile and throughput calculations;
- bounded simulated SNMP workload behavior;
- NetFlow/IPFIX/sFlow parsing and ingestion queue behavior;
- vendor flow compatibility;
- scheduler singleton/restart and HA lease fail-closed behavior;
- SNMP device pagination/performance and latest-metrics query-count expectations.

Frontend validation passed **16 tests** covering the existing dashboard/module regressions. The Vite production build completed successfully.

## Limitations and Required Live Validation

This report does not claim production scalability or disaster-recovery success. To complete the blocked measurements, run the existing NMS in an isolated validation environment with PostgreSQL, Redis, backend and frontend started, then:

1. configure a lab SNMP simulator or approved test devices for v2c and v3;
2. run the API workload against authenticated endpoints and record p50/p95/p99 by route;
3. collect PostgreSQL query deltas, connection count, CPU, memory and query plans during the same window;
4. run NetFlow/IPFIX/sFlow traffic into the configured receiver and record accepted, dropped, queued and persisted flows;
5. observe scheduler persisted-job backlog and duplicate-poll protection during progressive fleet steps;
6. use a browser performance run for first load, dashboard load, route transitions and refresh behavior;
7. stop at the first instability and record the failing scale point and bottleneck.

Until those steps are run, the highest defensible result is: **the bounded simulator passed 5,000 simulated operations; the NMS validated real-device capacity remains unknown.**
