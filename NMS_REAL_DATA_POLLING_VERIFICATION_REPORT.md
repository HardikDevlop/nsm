# NMS Real-Data, Polling, and Data-Consistency Verification Report

**Date:** 2026-09-17 (Asia/Kolkata)  
**Scope:** verification only; no production code or topology architecture was changed.  
**Evidence rule:** source inspection is reported separately from runtime proof. Historical logs are not treated as current runtime evidence.

## Executive result

The requested end-to-end chain cannot be verified in this workspace because the runtime is not running. No `uvicorn`, frontend, or polling process was present and no listening application port was available at audit time. PostgreSQL/API/frontend freshness and device identity therefore remain **RUNTIME PENDING**.

Source inspection confirms that the backend has a centralized SNMP scheduler, database-backed monitoring-data APIs, ICMP restoration during application lifespan, Linux monitoring restoration, and a shared frontend topology builder. It does not prove that those components are currently executing against real devices.

Historical artifacts show prior ICMP activity and prior backend errors, but they do not satisfy the requested three-cycle proof. No credentials, community strings, tokens, or passwords are included here.

## Runtime evidence boundary

| Check | Evidence | Classification |
|---|---|---|
| Backend process | No running `uvicorn`/backend process observed | RUNTIME PENDING |
| Frontend process | No running Vite/npm frontend process observed | RUNTIME PENDING |
| Listening ports | No application listener observed | RUNTIME PENDING |
| PostgreSQL | No live connection or query evidence obtained | RUNTIME PENDING |
| Real monitored-device baseline | Cannot safely identify current devices from live DB/API | RUNTIME PENDING |
| Current scheduler jobs | Source exists; no live scheduler instance | RUNTIME PENDING |
| Three consecutive cycles | No new observation possible | RUNTIME PENDING |
| Historical logs | ICMP starts exist on 2026-08-29; historical only | PARTIAL |

## Device baseline

No current device rows were printed because the database/API was unavailable. Consequently device id, IP, hostname, MAC, type, vendor, monitoring intent, ICMP/SNMP configuration, SNMP version, and latest health state are all **RUNTIME PENDING**. Fixture/sample devices were not used as evidence.

## Polling and persistence matrix

`hardik/backend/snmp/poll_scheduler.py` declares intervals for interfaces (15s), CPU/memory (60s), environment (300s), LLDP (600s), routing (600s), and inventory (86400s). `hardik/backend/main.py` starts the centralized polling scheduler during application lifespan and restores persisted ICMP intent and enabled Linux servers. These are configured paths, not proof of execution.

| Module | Real source | Polling | DB fresh | API fresh | UI data | Cross-page consistent | Status | Issue / evidence |
|---|---|---|---|---|---|---|---|---|
| ICMP | ICMP engine + persisted device intent | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | Historical ICMP logs only; no current cycle |
| SNMP System | SNMP system collector | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | Collector exists; no live result |
| Interfaces | SNMP interfaces collector/latest/history paths | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No current persisted timestamp |
| Inventory | SNMP inventory collector | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No live device association |
| VLAN | VLAN collector/capability response | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | Runtime unsupported/data state unknown |
| LLDP/CDP | LLDP/CDP collectors | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No fresh link evidence |
| ARP | ARP collector/capability response | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No fresh table evidence |
| MAC/FDB | MAC-table collector/capability response | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No fresh table evidence |
| Routing | Routing collector | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No fresh route evidence |
| Topology | Shared evidence + `buildLogicalTopologyGraph()` | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | PARTIAL | RUNTIME PENDING | Shared builder is present in both topology pages; runtime equality not proven |
| Alerts | Alert/event persistence and API | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | No current API/DB comparison |
| Packet Analysis | Monitoring/interface data path | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | Source uses polled timestamps; live source unavailable |
| Linux Server Monitoring | SSH/SNMP Linux service + metric history | RUNTIME PENDING | RUNTIME PENDING | RUNTIME PENDING | PARTIAL | RUNTIME PENDING | RUNTIME PENDING | Scheduler/API/UI paths exist; no configured server evidence |

## Three-cycle proof

No current cycles were observed. The required sequence `T1 < T2 < T3` cannot be established. Historical ICMP log entries demonstrate that a prior process emitted repeated probe starts, but not that current collectors completed successfully, persisted rows, served fresh API data, or rendered it in the frontend.

| Cycle | Timestamp | Device/module | Completion | DB/API timestamp | Result |
|---|---|---|---|---|---|
| 1 | Not observed | — | — | — | RUNTIME PENDING |
| 2 | Not observed | — | — | — | RUNTIME PENDING |
| 3 | Not observed | — | — | — | RUNTIME PENDING |

## Database, API, and time consistency

The backend source contains timestamp-bearing fields such as `last_seen`, `polled_at`, and `updated_at`; the frontend uses local India formatting in several views. A live DB-to-API comparison, null/future/ordering check, age calculation, and refresh-jump check could not be performed. Therefore timezone consistency is **RUNTIME PENDING**, not PASS.

## Frontend page matrix

| Page | Real data | Refresh | Timestamp | Empty/error/stale handling | Status |
|---|---|---|---|---|---|
| Overview | API-backed source present | Source/API refresh path; runtime unavailable | Source fields present | UI paths present; runtime unavailable | RUNTIME PENDING |
| Network Topology | API requests + shared graph builder | Timers/refetch paths present | `last_seen`/topology timestamps present | Loading/error paths present | RUNTIME PENDING |
| Manual Topology | API/manual persistence + shared graph builder | Discovery/automatic sync timers present | Evidence fields present | Toast/error paths present | RUNTIME PENDING |
| IP Scan | Page not found under the expected `IPScan` filename | Cannot verify | Cannot verify | Cannot verify | RUNTIME PENDING |
| SNMP Devices | API feature modules present | Query/polling paths present | Poll fields present | Status/waiting states present | RUNTIME PENDING |
| Device Monitoring | API-backed device data | `setInterval` refresh path present | Monitoring timestamps present | Loading/no-data/error paths present | RUNTIME PENDING |
| Packet Analysis | Monitoring API + interface rows | Manual fetch/refresh path present | Uses `polled_at`/fetch timestamp | Loading/error paths present | RUNTIME PENDING |
| Linux Server Monitoring | Linux server/metrics/security APIs | Refresh timer and manual refresh present | `collected_at` displayed locally | No-data/error paths present | RUNTIME PENDING |

The frontend source includes explicit N/A/no-data handling in inspected areas. That is source evidence only; it does not establish that production responses are real rather than stale or empty.

## Cross-page and topology consistency

Both `Topology.tsx` and `ManualTopology.tsx` import `buildLogicalTopologyGraph` from the shared topology builder. This supports preservation of a shared graph authority at source level. Runtime comparison of node IDs, link pairs, ports, confidence, evidence, and repeat-discovery deduplication was not possible. No topology refactor was performed.

## Interface, health, packet, and Linux checks

- Interface fields and latest/history API paths are present, but no real device row or fresh sample was available to verify ifIndex, status, speed, MAC, counters, or utilization.
- Health derivation and freshness paths exist in backend/frontend source, but no same-device cross-page contradiction can be established without live responses.
- Packet Analysis maps interface polling data and `polled_at`; no live flow/sFlow/IPFIX evidence was available. A current assertion that packet widgets are real cannot be made.
- Linux monitoring exposes detection, SSH/SNMP validation, current metrics, history, security events, and scheduler status in source. No configured real server was verified.

## Error and static-data audit

Historical logs contain repeated availability persistence errors for a device (null `availability_percent` violating a database NOT NULL constraint) and historical ICMP timeout/down observations. These are P1 investigation items because they indicate prior persistence/availability failures, but their current state is unknown.

Source audit also found standalone/demo-risk modules:

- `hardik/continuous_monitoring.py` generates random CPU, memory, disk, latency, bandwidth, temperature, packet-loss, and event values.
- `hardik/simple_monitor.py` generates random monitoring metrics.
- `hardik/setup_monitoring.py` defines sample devices and sample alerts and documents running the continuous monitor.

Their active production reachability was not proven. They are nevertheless a **source-level mock/static-data risk** and must be excluded from any real-data verification until deployment wiring is confirmed.

## Final classification

- **REAL DEVICE DATA VERIFIED:** NO — RUNTIME PENDING
- **POLLING ACTUALLY RUNNING:** PENDING
- **3 CONSECUTIVE POLL CYCLES VERIFIED:** PENDING
- **DB DATA FRESH:** PENDING
- **API DATA FRESH:** PENDING
- **FRONTEND SHOWING REAL DATA:** PARTIAL (source paths only)
- **TIME/TIMEZONE CONSISTENT:** PENDING
- **CROSS-PAGE DEVICE DATA CONSISTENT:** PENDING
- **DUPLICATE POLLING FOUND:** NO current runtime evidence; source-level singleton/lease protections exist
- **STALE DATA FOUND:** YES in the sense that historical data is not current proof; current runtime staleness is PENDING
- **MOCK/STATIC PRODUCTION DATA FOUND:** YES (source-level modules listed above; active deployment use unverified)
- **FABRICATED VALUES FOUND:** YES in standalone random/demo modules; active production use unverified
- **TOPOLOGY SHARED AUTHORITY PRESERVED:** YES at source level; runtime not verified

### P0 issues

- None proven from the inactive runtime.

### P1 issues

- Runtime verification blocked: start the real PostgreSQL, backend, frontend, and device access path, then capture three completed cycles with DB/API timestamps.
- Historical availability persistence failures for null `availability_percent` require investigation before claiming availability freshness.
- Exclude or clearly isolate random/sample monitoring modules from production execution and verification.

### P2 issues

- Expected IP Scan page filename/component could not be located under `figma design/src/pages`; map the route to its actual component before page-level verification.
- Perform live audit of API query ordering, cache behavior, query keys, timer cleanup, and response races once services are running.

## Release decisions

- **SAFE TO FREEZE TOPOLOGY RUNTIME:** NO — runtime evidence is pending.
- **SAFE TO MOVE TO IP SCAN:** NO — the requested end-to-end real-data proof is incomplete and the expected IP Scan page was not located.

## Verification stop condition

Stopped after creating this report, as requested. No fixes, broad refactors, topology changes, fixture insertion, or credential exposure were performed.
