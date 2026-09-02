# Core NMS Validation Baseline

Date: 2026-08-29
Repository: /home/agnigate/Desktop/NMS
Evidence priority: real host runtime verification supplied for 2026-08-29 is authoritative over restricted-environment observations.
Scope: documentation-only baseline. No code, schema, credentials, devices, jobs, OIDs, or database rows were changed.

## Status Definitions

- PASS: verified successfully on the real host runtime.
- PARTIAL: core workflow works, but an enrichment or completeness gap remains.
- UNSUPPORTED BY DEVICE: real device reported the capability/OIDs are unsupported.
- EMPTY-BUT-WORKING: endpoint works and returns no current records.
- KNOWN ISSUE: confirmed issue retained for later review.
- NOT TESTABLE: required account or scenario does not exist.

## Executive Result

The current real-host NMS runtime is operational for the core platform and verified device workflow. PostgreSQL 14/main is online, 29 of 29 migrations are applied, FastAPI health/authentication/protected APIs pass, and the core device, scheduler, persistence, SNMP, alert, event, report, and frontend Devices/SNMP workflows passed the supplied host verification.

Device 115 (Core-switch) is a real monitored SNMP v3 device. CPU and memory are unsupported by device 115, not failures. Metadata, semantic consistency, history-quality, lifecycle, and restart-persistence items remain for later review.

## Core Functionality Matrix

| Functionality | Status | Verified result / evidence |
|---|---|---|
| PostgreSQL connectivity and migrations | PASS | PostgreSQL 14/main online; 127.0.0.1:5432 accepting connections; authentication successful; schema_migrations exists; 29 applied of 29 known. |
| FastAPI health | PASS | GET /api/v1/health returned HTTP 200 with database.connected=true. |
| Authentication and admin authorization | PASS | Existing Admin login and /auth/me succeeded; admin protected access verified. |
| RBAC permission denial for restricted user | NOT TESTABLE | No restricted/non-admin user currently exists; not a failure. |
| PostgreSQL-backed device management | PASS | Protected device list returned HTTP 200 and 10 real PostgreSQL-backed devices. |
| SNMP v3 device monitoring | PASS | Device 115 Core-switch is a real verified SNMP v3 monitored device. |
| Automatic 60-second SNMP polling | PASS | Scheduler polls at approximately 60-second intervals. |
| Polling history persistence | PASS | Repeated successful persisted polls are present. |
| Latest metrics endpoint | PASS | Returned HTTP 200 after the bind-parameter fix. |
| System/identity | PASS | SNMP system/identity passed. |
| Interfaces and traffic metrics | PASS | SNMP interfaces and traffic data passed. |
| Historical interface metrics | PASS | Real persisted interface time-series data returned. |
| VLAN | PASS | VLAN passed. |
| LLDP | PARTIAL | Collection passed; remote hostname/platform/capabilities are not fully populated for all neighbors. |
| MAC address table | PASS | MAC table passed. |
| ARP table | PASS | ARP passed. |
| Routing table | PASS | Routing passed; some metadata remains incomplete. |
| SNMP inventory | PASS | SNMP inventory passed. |
| Device topology | PASS | Device topology passed. |
| Global topology | PASS | Global topology passed. |
| Realtime ICMP monitoring | PASS | Ran successfully for device 115. |
| DeviceMetric persistence | PASS | Persistence verified. |
| DeviceStatusHistory persistence | PASS | Persistence verified. |
| Alerts | PASS | Alerts passed; interface-down alert lifecycle remains later review. |
| Events | PASS | Events passed. |
| Daily reports | PASS | Daily report passed. |
| Management reports | PASS | Management report passed. |
| Stored reports list | EMPTY-BUT-WORKING | /api/v1/reports returned []; endpoint works but has no stored records. |
| Frontend Devices/SNMP runtime integration | PASS | Browser runtime passed; /devices uses PostgreSQL-backed API. |
| Legacy /discovery/inventory | EMPTY-BUT-WORKING | Returned {"devices":[]}; legacy JSON-backed path expects data/inventory.json, which does not exist. |

## Device 115 Domain Results

| Domain | Status | Notes |
|---|---|---|
| Identity | PASS | Identity collected and returned. |
| Interfaces | PASS | Interface and traffic data collected. |
| CPU | UNSUPPORTED BY DEVICE | Requested CPU monitoring OIDs are not provided by device 115. |
| Memory | UNSUPPORTED BY DEVICE | Requested memory monitoring OIDs are not provided by device 115. |
| Storage | PASS | Verified in supported SNMP monitoring workflow. |
| Routing | PASS | Data collected; metadata incomplete where device does not provide it. |
| ARP | PASS | Data collected. |
| MAC | PASS | Table data collected. |
| VLAN | PASS | Data collected. |
| LLDP | PASS | Collection passed; enrichment is partial. |
| Inventory | PASS | Inventory collected. |

## Partial Results

| Area | Status | Gap |
|---|---|---|
| LLDP neighbor enrichment | PARTIAL | Remote hostname, platform, and capabilities are not populated for all neighbors. |
| Routing metadata enrichment | PARTIAL | Protocol and interface fields are incomplete where device data does not provide them. |
| Inferred topology node enrichment | PARTIAL | Some inferred nodes have null hostname, vendor, device type, or IP fields. |

## Known Issues / Later Review

1. TenGigabitEthernet1-4 naming indicates 10G while speed_bps/reported speed is 100000000.
2. CPU/memory unsupported responses use reachable=false although device 115 is reachable; semantic API consistency issue.
3. ARP response has reachable=null and collection_ms=null despite successful collection.
4. Historical interface utilization is null and percentile_95_mbps=0 appears suspicious.
5. Realtime ICMP monitoring is API-triggered/in-memory and is not automatically restored after backend restart.
6. Linux monitoring emitted un-awaited SNMP coroutine RuntimeWarnings during shutdown.
7. SNMP topology/interfaces polling can take approximately 14 seconds.
8. Some MAC multi-device ports remain UNKNOWN.
9. Some routing metadata remains unknown/null.
10. Some inferred topology nodes lack enrichment metadata.
11. Existing interface-down alerts may remain open; auto-resolution needs later verification.
12. /discovery/inventory is legacy JSON-backed data/inventory.json, while current device management uses PostgreSQL.
13. Layout.tsx had stale undefined loadNotificationPanel/loadThemePicker calls; both were removed and browser console/page operation then worked normally.

## Authentication and RBAC Detail

| Check | Status | Result |
|---|---|---|
| Admin login | PASS | Existing Admin account authenticated successfully. |
| /auth/me | PASS | Valid admin token returned the current user. |
| Protected /devices without token | PASS | Returned HTTP 401. |
| Protected /devices with admin token | PASS | Returned HTTP 200. |
| Restricted-user permission denial | NOT TESTABLE | No restricted/non-admin user currently exists; do not classify as FAIL. |

## Authoritative Runtime Evidence

- PostgreSQL online and authenticated.
- 29/29 migrations applied.
- FastAPI health HTTP 200 with database connected.
- 10 real PostgreSQL-backed devices.
- Device 115 monitored through SNMP v3.
- Approximately 60-second automatic scheduler polling.
- Repeated successful persisted polling history.
- Latest metrics HTTP 200 after bind-parameter fix.
- Real historical interface metrics.
- Successful SNMP system, interfaces, VLAN, LLDP, MAC, ARP, routing, inventory, device topology, and global topology.
- Successful realtime ICMP, DeviceMetric, DeviceStatusHistory, alerts, events, daily reports, management reports, and frontend Devices/SNMP integration.

## Historical Restricted-Environment Limitations

The following older observations came from the restricted Codex/sandbox execution environment only. They are retained for audit history and must not override the real-host results above:

- PostgreSQL was reported unreachable or the local cluster was observed down from the restricted namespace.
- FastAPI startup was reported blocked by database access from that namespace.
- Backend 127.0.0.1:8000 was reported inaccessible from that namespace.
- Vite startup returned EPERM while attempting to bind a local port in that namespace.
- Authentication, RBAC, scheduler, and one-device checks were reported not testable from that namespace.
- Older reports marked runtime features blocked or unverified. Those statuses describe environment access limitations, not the current real-host application state.

## Baseline Interpretation

The core NMS is PASS for the supplied real-host verification scope. CPU and memory for device 115 are UNSUPPORTED BY DEVICE, not failed. LLDP, routing metadata, inferred topology enrichment, report emptiness, and the legacy inventory endpoint are classified separately from core runtime success.

The remaining items are review candidates and should not be silently converted into failures or hidden from future validation.

