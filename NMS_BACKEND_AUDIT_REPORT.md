# NMS Backend API Audit Report

Date: 2026-08-24

Scope: backend-only API flow, database queries, SNMP collection, timeout/retry behavior, duplicate-query risks, and performance risks.

## Audit Safety Status

- Backend code modified: **No**
- Packages installed: **No**
- OIDs changed: **No**
- SNMP v2/v3 behavior changed: **No**
- Files deleted: **No**
- Runtime performance benchmark executed: **No**
- Static backend flow audit: **Complete**

## A. Current Architecture

```text
Frontend
  -> FastAPI route
  -> permission + SQLAlchemy DB session
  -> DB read
  -> optional SNMPService
  -> SNMPClient / pysnmp
  -> collector modules
  -> optional DB persistence
  -> JSON response
```

Main backend files:

- `hardik/backend/api/routes.py`
- `hardik/backend/api/snmp_device_routes.py`
- `hardik/backend/api/discovery_routes.py`
- `hardik/backend/snmp/collector.py`
- `hardik/backend/snmp/client.py`
- `hardik/backend/services/snmp_polling.py`

`SNMPService.collect()` performs identity GETs, vendor/UCD scalar GETs, multiple table walks, and collector execution for one device.

## B. Requested API Trace

| API | Route/function | DB queries/tables | Live SNMP | Collector | Response source | Main bottleneck |
|---|---|---|---|---|---|---|
| `GET /devices` | `api/routes.py:list_devices` | `Device`, non-deleted rows, pagination | No | None | DB | Large list or missing indexes |
| `GET /device-metrics` | `api/routes.py:list_device_metrics` | `DeviceMetric`, optional `device_id`, sort by `created_at` | No | None | DB | Sorting large history |
| `GET /snmp/devices` | `list_snmp_devices_optimized` | `Device`, `Vendor`, `DeviceType`, `DeviceCredential`, `DeviceIdentity`, `DeviceCapabilities`, `MonitoringConfig`; count query | No | None | DB | Count plus joins and batch queries |
| `GET /snmp/devices/{id}/overview` | `get_snmp_overview` | `Device`, `DeviceIdentity`, `DeviceCapabilities`, latest 20 `PollingHistory` | No | None | DB | Multiple queries and relationship loading |
| `GET /snmp/devices/{id}/metrics/latest` | `get_latest_metrics` | `LatestCPU`, `LatestMemory`, `LatestStorage`, `LatestInterface`, `LatestEnvironment` | No | None | DB | Five separate queries |
| `/system` | `get_snmp_system` | `Device`, `DeviceCredential`, vendor/device type relationship | Yes | `SystemCollector` | Live SNMP | Identity GET and system walk |
| `/cpu` | `get_snmp_cpu` | `Device`, `DeviceCredential`, `CPUStatistic` history | Yes | `CPUCollector` | Live CPU plus DB history | SNMP plus history query |
| `/memory` | `get_snmp_memory` | `Device`, `DeviceCredential` | Yes | `MemoryCollector` | Live SNMP | SNMP timeout/walk |
| `/storage` | `get_snmp_storage` | `Device`, `DeviceCredential` | Yes | `StorageCollector` | Live SNMP | Storage table walk |
| `/interfaces` | `get_snmp_interfaces` | `Device`, `DeviceCredential`, `LatestInterface`; then latest/history persistence | Yes | Full `SNMPService.collect()` | Live SNMP plus DB enrichment | Full collection used instead of interface-only |
| `/environment` | `get_snmp_environment` | `Device`, `DeviceCredential` | Yes | `EnvironmentCollector` | Live SNMP | Entity/sensor walks |
| `/vlans` | `get_snmp_vlans` | `Device`, `DeviceCredential` | Yes | VLAN collector | Live SNMP | VLAN table walk |
| `/lldp` | `get_snmp_lldp` | Up to 500 `Device` rows and `DeviceIdentity` map | Yes | Full `SNMPService.collect()` | Live SNMP plus DB enrichment | Full collection plus enrichment |
| `/routing` | `get_snmp_routing` | `Device`, `DeviceCredential` | Yes | Full `SNMPService.collect()` | Live SNMP | Full collection instead of routing-only |
| `/mac-table` | `get_snmp_mac_table` | `Device`, `DeviceCredential`, `DeviceCapabilities` | Yes | `MACTableCollector`, possibly ARP again | Live SNMP plus cached ARP | Additional ARP collection possible |
| `/arp` | `get_snmp_arp` | `Device`, `DeviceCredential`, `DeviceCapabilities` | Yes | `ARPCollector` | Live SNMP and optional cached data | Live call on each request |
| `POST /poll` | `poll_device_now` | `Device`, `DeviceCredential`, latest/history persistence | Yes | Full `SNMPService.collect()` | Full live collection | Runs every collector and persists all results |
| `/polling-history` | `get_snmp_polling_history` | `PollingHistory`, max 500 rows | No | None | DB | Time filtering and sorting |
| `/monitoring/{module}/start` | `start_module_monitoring` | `DeviceCapabilities`, then `MonitoringConfig` via scheduler | No immediate SNMP | Scheduler / `SNMPPoller` later | DB scheduler state | `asyncio.run()` inside sync route |
| `/monitoring/{module}/stop` | `stop_module_monitoring` | `MonitoringConfig` via scheduler | No immediate SNMP | Scheduler | DB/scheduler state | Same sync-to-async bridge |
| `POST /discover` | `discover_device` / `_run_identity_discovery` | `Device`, `DeviceCredential`, `DeviceIdentity`, `DeviceCapabilities`, latest/history tables, `Event` | Yes | Full collection plus identity/capability services | Live SNMP plus persisted DB | Full collect plus persistence passes |
| `POST /discovery/snmp` | `discovery_snmp` | Per result: `Device`, `Interface`, `DeviceCredential`, `DeviceCapabilities`, `DeviceIdentity`, `Event`, latest/history tables | Yes | `SNMPDiscovery` / `SNMPService` | Live SNMP plus DB upsert | Thread scan plus per-interface and collector persistence |
| `POST /test-snmp` | `test_snmp_connection` | `Device`, `DeviceCredential` | Yes | Full `SNMPService.collect()` | Live SNMP, returns `response_ms` | Quick test performs full collection |

## C. APIs Doing Live SNMP

These routes directly call `_live_collect()`:

- `/snmp/devices/{id}/system`
- `/snmp/devices/{id}/cpu`
- `/snmp/devices/{id}/memory`
- `/snmp/devices/{id}/storage`
- `/snmp/devices/{id}/interfaces`
- `/snmp/devices/{id}/environment`
- `/snmp/devices/{id}/vlans`
- `/snmp/devices/{id}/lldp`
- `/snmp/devices/{id}/routing`
- `/snmp/devices/{id}/mac-table`
- `/snmp/devices/{id}/arp`
- `POST /snmp/devices/{id}/poll`
- `POST /snmp/devices/{id}/discover`
- `POST /snmp/devices/{id}/test-snmp`
- `GET /snmp/topology?refresh=true`

Important findings:

- `/interfaces`, `/lldp`, and `/routing` call `_live_collect()` without a domain.
- These routes execute the full collector pipeline instead of only their requested module.
- `/poll` and `/discover` intentionally run the full pipeline.
- `/mac-table` can issue another live ARP collection when cached ARP data is missing.

## D. APIs Doing DB Reads Only

- `GET /devices`
- `GET /device-metrics`
- `GET /snmp/devices`
- `GET /snmp/devices/{id}/overview`
- `GET /snmp/devices/{id}/metrics/latest`
- `GET /snmp/devices/{id}/polling-history`
- `GET /snmp/devices/{id}/polling-stats`
- `GET /snmp/devices/{id}/identity`
- `GET /snmp/devices/{id}/capabilities`
- `GET /snmp/devices/{id}/oids`
- `GET /snmp/devices/{id}/oid-tree`
- `GET /snmp/devices/{id}/monitoring`

Monitoring start/stop routes do not poll immediately, but configure scheduler jobs that later execute live SNMP polls.

## E. Timeout And Retry Behavior

### Route-level live collection

`_live_collect()` creates:

```text
SNMPService(timeout=3.0, retries=1)
```

One SNMP request can therefore retry once.

### SNMP client

`snmp/client.py` uses:

```text
UdpTransportTarget(timeout=3, retries=1)
```

The thread wrapper has:

```text
future.result(timeout=120)
```

This is a Python thread wait cap, not a complete HTTP request timeout.

### Scheduler polling

`services/snmp_polling.py` uses:

```text
SNMPService(timeout=2.0, retries=0)
```

There is no explicit timeout around the complete `asyncio.to_thread()` task.

### Discovery

`POST /discovery/snmp` uses `timeout_seconds=0.75` by default and scans IPs with up to 64 workers. There is no outer timeout for the complete worker pool request.

### Missing timeout

There is no end-to-end FastAPI/client timeout around complete route execution. A request can remain pending while SNMP walks, DB persistence, scheduler operations, or discovery futures are running.

## F. Duplicate And Expensive Queries

1. `/interfaces` performs full SNMP collection instead of interface-only collection.
2. `/lldp` performs full SNMP collection and then loads up to 500 devices plus identity maps.
3. `/routing` performs full SNMP collection instead of routing-only collection.
4. `/poll` executes every collector even when one module is needed.
5. `/discover` runs full collection, identity/capability processing, and another persistence pass.
6. `POST /discovery/snmp` performs per-interface SELECT queries during upsert.
7. Discovery persists every collector through `SNMPPoller._persist_results`, causing repeated DB work and commits.
8. `/mac-table` may run a separate ARP collection after MAC collection.
9. `/snmp/devices/{id}/metrics/latest` performs five independent latest-value queries.
10. `/snmp/devices` performs count, paginated device, credential, identity, capabilities, and monitoring-config queries.
11. Full collection walks many standard OID roots sequentially.
12. Full collection also performs vendor scalar and UCD scalar GETs before table walks.
13. Scheduler jobs and manual `/poll` can overlap for the same device/module; no clear route-level single-flight lock was found.
14. `PollingHistory.duration_ms` is written as `0` in `_persist_history`, even though poll duration is measured separately.
15. Monitoring routes repeatedly bridge async scheduler code with `asyncio.run()`.

## G. Top 10 Performance Problems

1. Full SNMP collection is used by module routes that should be domain-specific.
2. Full collection contains many sequential SNMP walks.
3. No end-to-end HTTP timeout exists.
4. Live SNMP calls happen synchronously inside FastAPI sync routes.
5. Interfaces route combines live collection, DB enrichment, and persistence in one request.
6. Discovery has high DB query volume and per-interface upsert work.
7. Discovery persists all collector data after collecting all devices.
8. Latest metrics endpoint uses multiple separate queries.
9. Monitoring routes repeatedly start/bridge async scheduler operations.
10. Polling jobs can duplicate work with manual poll/module requests.

## H. Exact Files To Change Later

No changes applied now. Future changes should be isolated to:

- `hardik/backend/api/snmp_device_routes.py`
  - Domain-specific collection, timeout handling, duplicate-query reduction.
- `hardik/backend/snmp/collector.py`
  - Collector timing, cancellation, and strict domain collection.
- `hardik/backend/snmp/client.py`
  - Bounded operation cancellation and timeout propagation.
- `hardik/backend/services/snmp_polling.py`
  - Duplicate poll protection and real `duration_ms` persistence.
- `hardik/backend/api/discovery_routes.py`
  - Batch DB upserts, persistence optimization, outer discovery timeout.
- `hardik/backend/api/routes.py`
  - Device/metric pagination and index review.
- Backend model/migration files
  - Indexes on `device_id`, `created_at`, `deleted_at`, `ip_address`, `interface_id`, and monitoring keys.
- `hardik/backend/backend_smoke_test.py`
- `hardik/backend/unified_smoke_test.py`
  - Route timeout, query-count, duplicate-poll, and error-path tests.

## I. Recommended Migration Order

1. Add observability first: request duration, DB duration, SNMP duration, collector duration, and query count.
2. Add cancellation/timeouts without changing SNMP versions, credentials, or OIDs.
3. Fix `/interfaces`, `/lldp`, and `/routing` to use intended domain collection.
4. Add duplicate-poll protection for manual poll versus scheduler poll.
5. Optimize discovery persistence with batch operations.
6. Optimize `/snmp/devices` and latest-metrics queries after measuring query plans.
7. Move scheduler lifecycle handling away from repeated `asyncio.run()` calls.
8. Add regression tests for every requested API and timeout/error path.
9. Only after measurements, consider schema indexes or collector-level changes.

## Final Result

The audit identified the current request flow, DB/SNMP boundaries, collector usage, persistence work, timeout behavior, duplicate-query risks, and the safest future migration order. No backend behavior was changed during this audit.
