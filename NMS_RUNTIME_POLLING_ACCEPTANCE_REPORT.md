# NMS Runtime-Only Polling Verification

**Date:** 2026-09-17 (Asia/Kolkata)  
**Scope:** runtime evidence only. No source audit repeated, no code/topology changes, no data inserted.

## Runtime precheck

| Dependency | Observation | Result |
|---|---|---|
| PostgreSQL | `pg_isready -h localhost -p 5432`: no response | FAIL / blocks direct DB queries |
| FastAPI | localhost:8000 probes returned no connection | FAIL / blocks live API calls |
| Frontend | localhost:3000 and :5173 probes returned no connection | FAIL / blocks browser acceptance |
| Scheduler/collectors | Same-day `snmp.log` and `api.log` contain collector/persistence activity through 11:15:59 | PARTIAL runtime evidence |
| Real devices | Same-day logs identify monitored device IDs and IPs | PARTIAL; baseline fields unavailable |

The current process/port precheck is down, but retained same-day runtime logs provide bounded evidence for SNMP poll cycles. They cannot replace direct DB/API/frontend interaction.

## Selected real device

Selected from same-day collector/persistence evidence:

| Field | Value |
|---|---|
| Device ID | 283 |
| IP | 192.168.100.2 |
| Hostname | Not available without DB/API; not inferred |
| SNMP version | Not available without DB/API; not inferred |
| Monitoring enabled | Not directly queryable; collector activity proves a poll target, not configuration state |
| Derived health | Not available without API/DB |

This is treated as a real runtime target because the log contains successful SNMP root queries and accepted persistence for device 283; no fixture/sample device was selected.

## Three-cycle polling proof: device 283

The following same-day entries are from `hardik/logs/snmp.log` and `hardik/logs/api.log`. Each cycle has collector success, accepted persistence, and a subsequent API cached read for the persisted record.

| Cycle | Poll/collector evidence | DB persistence evidence | API evidence | Result |
|---|---|---|---|---|
| T1 | 11:11:29.915, host 192.168.100.2, 6/6 roots succeeded, 1762.4 ms | 11:11:29.928, device 283, row 86, `05:41:29.923498Z`, accepted | 11:11:37.232, row 86/device 291 cache read; selected 283 was included in live assembly at 11:11:35 | PARTIAL matched chain |
| T2 | 11:12:29.725, host 192.168.100.2, 6/6 roots succeeded, 1540.4 ms | 11:12:29.607, device 283, row 86, `05:42:29.603396Z`, accepted | 11:12:35.611, live assembly included device 283; 11:12:37.818 cached read | PASS for log-observed cycle |
| T3 | 11:13:29.725, host 192.168.100.2, 6/6 roots succeeded, 1461.7 ms | 11:13:29.739, device 283, row 86, `05:43:29.735525Z`, accepted | 11:13:34.831, live assembly included device 283; cached topology read followed | PASS for log-observed cycle |

The persisted timestamps advance as `05:41:29.923498Z < 05:42:29.603396Z < 05:43:29.735525Z`. Additional cycles for device 283 are visible at 11:14 and 11:15. This proves repeated SNMP collector activity and accepted persistence/API assembly in the captured runtime logs. It does **not** prove frontend rendering or direct SQL equality because services are currently unreachable.

### Module coverage

| Module | Runtime result |
|---|---|
| ICMP | PENDING; historical/current log entries exist, but no DB/API/frontend comparison |
| SNMP System/core | PASS from same-day collector/persistence/API log chain |
| Interfaces | PENDING; direct latest row/value unavailable |
| Inventory | PENDING; no direct latest row/value |
| VLAN | PENDING/unsupported status not safely attributable to selected device from this evidence |
| LLDP/CDP | PENDING |
| ARP | PENDING |
| MAC/FDB | PENDING |
| Routing | PENDING |

Long-interval modules were not incorrectly treated as having three short-interval cycles.

## DB → API consistency

| Domain | Result | Evidence |
|---|---|---|
| SNMP topology snapshot | PARTIAL | Persistence is accepted for device 283 and API live assembly includes device 283, but the captured cached reads select other device rows; exact DB-row/API-row equality for 283 requires live query access |
| ICMP | PENDING | No direct DB/API access |
| System | PENDING | No direct DB/API access |
| Interfaces and other modules | PENDING | No direct latest values available |

The log evidence supports logical DB/API agreement for the topology snapshot path, not a complete database equality audit.

## Frontend and cross-page verification

Frontend ports were unreachable. Overview, SNMP Devices, Device Monitoring, Network Topology, and Manual Topology could not be opened, refreshed, or inspected with the selected device. Duplicate requests, race conditions, stale cache behavior, timestamp display, and cross-page identity therefore remain **PENDING**.

| Check | Result |
|---|---|
| Frontend fresh data | PENDING |
| Cross-page consistency | PENDING |
| Network topology runtime | PENDING |
| Manual discovery runtime | PENDING |
| Repeated discovery dedupe | PENDING |
| Manual workspace preservation | PENDING |
| Port Map | PENDING |

## Time consistency

The observed persisted timestamps are UTC-offset timestamps (`Z`/`+00:00`), and log wall-clock times are consistent with the configured India-local audit date. A single event could not be inspected through all four live layers (scheduler, DB, API, frontend), so full timezone acceptance is **PENDING**. No future `last_seen`, negative age, or backwards frontend timestamp was directly observed.

## Demo/mock reachability

Search of startup/service wiring found no import of the following standalone modules from the FastAPI startup path or central runtime services:

| File | Classification |
|---|---|
| `hardik/continuous_monitoring.py` | DEMO/UNUSED in inspected startup wiring |
| `hardik/simple_monitor.py` | DEMO/UNUSED in inspected startup wiring |
| `hardik/setup_monitoring.py` | DEMO/UNUSED standalone setup script |

The files contain random/sample generation, but no evidence was found that they reach the current backend API/DB/UI runtime path. Result: **PASS** for observed production reachability, with the caveat that the unavailable live process prevents a complete deployment-level proof.

## Availability NULL error

No current `availability_percent` NULL/NOT NULL error was found in the available same-day log slice. Because PostgreSQL and FastAPI are not currently reachable and no live availability poll could be triggered, classification is **NOT TRIGGERED**, not RESOLVED.

## Required final statuses

- **RUNTIME SERVICES:** FAIL (PostgreSQL, FastAPI, and frontend unavailable at precheck)
- **REAL DEVICE VERIFIED:** YES (bounded same-day log evidence; incomplete identity fields)
- **ICMP 3-CYCLE:** PENDING
- **SNMP CORE 3-CYCLE:** PASS (same-day logs, device 283, T1 < T2 < T3)
- **DB TIMESTAMPS ADVANCING:** YES (accepted persistence timestamps advance in logs)
- **API TIMESTAMPS ADVANCING:** PENDING (API assembly activity is logged, but exact selected-device API timestamps are unavailable)
- **DB/API LATEST MATCH:** PENDING (direct DB query and exact selected-device API response unavailable)
- **FRONTEND FRESH DATA:** PENDING
- **CROSS-PAGE CONSISTENCY:** PENDING
- **TIMEZONE CONSISTENCY:** PENDING
- **NETWORK TOPOLOGY RUNTIME:** PENDING
- **MANUAL DISCOVERY RUNTIME:** PENDING
- **REPEATED DISCOVERY DEDUPE:** PENDING
- **MANUAL WORKSPACE PRESERVED:** PENDING
- **MOCK/DEMO PRODUCTION REACHABILITY:** PASS (not found in inspected startup wiring)
- **AVAILABILITY NULL ERROR:** NOT TRIGGERED

### P0

- None proven.

### P1

- Runtime services are unavailable for direct acceptance; restart/access PostgreSQL, FastAPI, and frontend, then repeat frontend and direct DB/API checks.
- Full acceptance remains blocked until the selected device’s hostname, SNMP version, derived health, interface values, and API/DB rows are directly queried.

### P2

- Add/retain an auditable correlation ID or cycle ID across scheduler, persistence, API, and frontend telemetry to make future runtime acceptance unambiguous.

## Final real-data pipeline

- **DEVICE → POLLER:** PASS (same-day SNMP collector success for device 283)
- **POLLER → DB:** PASS (same-day accepted persistence for device 283)
- **DB → API:** PARTIAL (same-day live API assembly is logged, but exact selected-device row equality is pending)
- **API → FRONTEND:** PENDING (frontend unavailable)

## Overall acceptance

**PARTIAL** — SNMP core polling and persistence/API log evidence pass for three advancing cycles; frontend, direct DB/API verification, ICMP, and topology interaction remain pending.

- **SAFE TO FREEZE TOPOLOGY RUNTIME:** NO
- **SAFE TO MOVE TO IP SCAN:** NO

Stopped after creating this report. No failures were fixed.
