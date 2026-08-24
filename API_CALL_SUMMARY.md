# API Call Summary Report

Date: 2026-08-24
Scope: all frontend API calls in `figma design/src/lib/api.ts`, SNMP hooks/modules, pages, and refresh utilities.

This is a static source audit. The repository does not currently record request start/end timestamps for every API, so exact runtime milliseconds cannot be claimed here. The `Duration` column therefore distinguishes cache time, refresh frequency, and calls whose duration depends on database/SNMP work.

## Global Request Rules

| Rule | Current behavior |
|---|---|
| Base URL | `/api/v1` unless `VITE_API_BASE_URL` is set |
| Auth | Bearer token from memory/localStorage on every request |
| GET cache | 15 seconds in memory and session storage |
| Duplicate GETs | Same in-flight authenticated GET shares one promise |
| Mutation cache | POST/PUT/PATCH/DELETE clears GET cache |
| React Query default stale time | 30 seconds |
| React Query retry | 1 retry |
| Focus/reconnect refetch | Disabled globally |
| Client timeout | Not configured in `requestJson()` |
| Exact duration | Not measured by current code; use browser Network timing/server logs |

## API Summary By Group

### Authentication and session

| API | Called when | Duration behavior |
|---|---|---|
| `POST /auth/login` | Login submit | Network/auth dependent; not cached |
| `GET /auth/me` | Auth context/session validation | GET cache 15s; DB dependent |

### Dashboard, overview, alerts, events

| API | Called when | Duration behavior |
|---|---|---|
| `GET /dashboard/summary` | Dashboard load/refresh | GET cache 15s; aggregate DB query |
| `GET /overview?hours={hours}` | SNMP Monitoring and overview screens | GET cache 15s; aggregate payload, may be slow with large data |
| `GET /alerts?...` | Alerts, incidents, compliance and dashboard pages | GET cache 15s; filter/time-window dependent |
| `GET /events?...` | Events, audit and dashboard pages | GET cache 15s; result size dependent |
| `GET /notifications` | Notifications panel/page | GET cache 15s |
| `DELETE /alerts/clear-all` | Clear-all action | Mutation; invalidates GET cache |
| `POST /alerts` | Create alert | Mutation; invalidates GET cache |
| `PUT /alerts/{id}` | Update alert | Mutation; invalidates GET cache |
| `DELETE /alerts/{id}` | Delete alert | Mutation; invalidates GET cache |
| `POST /alerts/{id}/acknowledge` | Acknowledge action | Mutation; invalidates GET cache |
| `POST /alerts/{id}/resolve` | Resolve action | Mutation; invalidates GET cache |
| `POST /events` | Create event | Mutation; invalidates GET cache |
| `PUT /events/{id}` | Update event | Mutation; invalidates GET cache |

### Core device inventory

| API | Called when | Duration behavior |
|---|---|---|
| `GET /devices` | Device inventory/monitoring list | GET cache 15s; DB list query |
| `GET /devices/options` | Device selectors/forms | GET cache 15s |
| `GET /devices/{id}` | Device detail/monitoring page | GET cache 15s; DB detail query |
| `POST /devices` | Create device | Mutation; invalidates GET cache |
| `PUT /devices/{id}` | Edit device | Mutation; invalidates GET cache |
| `DELETE /devices/{id}` | Delete device | Mutation; invalidates GET cache |
| `DELETE /devices` | Delete all devices | Mutation; invalidates GET cache |
| `GET /devices/{id}/status-history` | Device monitoring detail | GET cache 15s; history size dependent |
| `GET /device-metrics?device_id=&skip=&limit=` | Monitoring charts and SNMP monitoring | GET cache 15s; `limit=200` used in some screens |
| `GET /discovery/device-history/{ip}?hours=24` | Device monitoring detail | GET cache 15s; history aggregation can be slow |

### SNMP device list and details

| API | Called when | Duration behavior |
|---|---|---|
| `GET /snmp/devices?page=&page_size=&search=&filters` | SNMP Devices page mount, search, sort, filter, pagination | React Query stale 15s plus API GET cache 15s; DB count + joins |
| `GET /snmp/devices/{id}` | SNMP device details | React Query stale 10s; DB-backed |
| `GET /snmp/devices/{id}/overview` | SNMP dashboard/device overview | GET cache 15s; DB-backed summary |
| `GET /snmp/devices/{id}/monitoring` | Monitoring configuration screens | React Query stale 30s |
| `GET /snmp/devices/{id}/monitoring/{module}/status` | Module status controls | React Query stale 10s |
| `GET /snmp/devices/{id}/metrics/latest` | Overview/latest metrics cards | React Query stale 30s |
| `GET /snmp/devices/{id}/cpu/latest` | Latest CPU card | React Query stale 30s |
| `GET /snmp/devices/{id}/memory/latest` | Latest memory card | React Query stale 30s |
| `GET /snmp/devices/{id}/interfaces/latest` | Latest interfaces card | React Query stale 30s |
| `GET /snmp/devices/{id}/storage/latest` | Latest storage card | React Query stale 30s |
| `GET /snmp/devices/{id}/environment/latest` | Latest environment card | React Query stale 30s |

### SNMP live collector modules

| API | Called when | Duration behavior |
|---|---|---|
| `GET /snmp/devices/{id}/system` | System module page | Live SNMP; device/network timeout dependent |
| `GET /snmp/devices/{id}/cpu` | CPU module page | Live SNMP; timeout dependent |
| `GET /snmp/devices/{id}/memory` | Memory module page | Live SNMP; timeout dependent |
| `GET /snmp/devices/{id}/storage` | Storage module page | Live SNMP; timeout dependent |
| `GET /snmp/devices/{id}/interfaces` | Interfaces module page | Live SNMP; response size/device dependent |
| `GET /snmp/devices/{id}/environment` | Environment module page | Live SNMP; device capability dependent |
| `GET /snmp/devices/{id}/vlans` | VLAN module page | Live SNMP; timeout dependent |
| `GET /snmp/devices/{id}/lldp` | LLDP module page | Live SNMP; timeout dependent |
| `GET /snmp/devices/{id}/routing` | Routing module page | Live SNMP; table size dependent |
| `GET /snmp/devices/{id}/oids` | OID explorer | Cached/persisted OID data; payload size dependent |
| `GET /snmp/devices/{id}/oid-tree` | OID tree view | Cached OID data; payload size dependent |
| `GET /snmp/devices/{id}/polling-history?hours=` | Polling history page | History window and DB size dependent |
| `GET /snmp/devices/{id}/polling-stats` | Polling statistics page | DB aggregation dependent |
| `GET /snmp/topology` | Global topology page | DB/topology aggregation; refresh every 30s |
| `GET /snmp/topology?device_id={id}` | Device topology module | DB/topology aggregation dependent |
| `POST /snmp/devices/{id}/poll` | Manual live poll action | Live SNMP; potentially slow |
| `POST /snmp/devices/{id}/discover` | Full device discovery action | Live SNMP + persistence; potentially longest call |
| `POST /snmp/devices/{id}/test-snmp` | Test connection action | Live SNMP; timeout dependent |
| `GET /snmp/devices/{id}/capabilities` | Capabilities/module navigation | React Query stale 60s; may use persisted capability data |
| `GET /snmp/devices/{id}/identity` | Identity view | GET cache 15s; persisted identity |
| `GET /snmp/devices/{id}/device-topology` | Device topology module | Live/DB topology dependent |
| `GET /snmp/devices/{id}/inventory` | Inventory module | Live SNMP/device capability dependent |
| `GET /snmp/devices/{id}/health` | Health module | Live SNMP/device capability dependent |
| `GET /snmp/devices/{id}/firewall` | Firewall module | Device capability dependent |
| `GET /snmp/devices/{id}/wireless` | Wireless module | Device capability dependent |
| `GET /snmp/devices/{id}/arp` | ARP module | Table size/device dependent |
| `GET /snmp/devices/{id}/mac-table` | MAC table module | Table size/device dependent |
| `GET /snmp/devices/{id}/cdp` | CDP module | Device capability dependent |

### SNMP monitoring controls

| API | Called when | Duration behavior |
|---|---|---|
| `POST /snmp/devices/{id}/monitoring/{module}/start` | Start one module | Mutation; starts backend poll job |
| `POST /snmp/devices/{id}/monitoring/{module}/stop` | Stop one module | Mutation; stops backend poll job |
| `PUT /snmp/devices/{id}/monitoring/{module}` | Change interval/enabled state | Mutation; invalidates GET cache |
| `POST /discovery/monitoring/start` | Start one legacy monitoring device | Mutation; monitoring loop dependent |
| `POST /discovery/monitoring/stop` | Stop one legacy monitoring device | Mutation |
| `POST /discovery/monitoring/start-all` | Start all monitoring | Payload/device-count dependent |
| `POST /discovery/monitoring/stop-all` | Stop all monitoring | Number of active jobs dependent |
| `GET /discovery/monitoring/status` | Monitoring list/detail and SNMP Monitoring page | GET cache 15s; can be large with many devices |
| `GET /monitoring/services` | Service status page | GET cache 15s |
| `DELETE /monitoring/kill-all` | Kill all services action | Mutation |
| `SSE /discovery/monitoring/stream` | Live monitoring pages | Long-lived connection; not a normal finite duration |

### Discovery and network scans

| API | Called when | Duration behavior |
|---|---|---|
| `GET /discovery/local-subnet` | Discovery form initialization | GET cache 15s |
| `POST /discovery/snmp` | SNMP discovery submit | IP count × SNMP timeout dependent |
| `POST /discovery/icmp` | Ping selected IPs | IP count × configured timeout; default timeout 1000ms |
| `POST /discovery/chunked-scan` | Large subnet scan start | Returns job; scan continues asynchronously |
| `GET /discovery/chunked-scan/{job_id}` | Chunked scan progress | Polling interval controlled by page |
| `POST /discovery/add-devices` | Save discovered devices | Mutation; payload/device count dependent |
| `POST /discovery/check-stored` | Check discovered devices against DB | Payload/device count dependent |
| `POST /devices/manual` | Add SNMP device form | Credential/device validation dependent |

### Organizations, sites, vendors, users, roles

| API family | Called when | Duration behavior |
|---|---|---|
| `/organizations` | Organizations page list/create/update/delete | GET cache on reads; CRUD mutation invalidates cache |
| `/sites` | Sites page list/create/update/delete | GET cache on reads; CRUD mutation invalidates cache |
| `/vendors` | Vendors page list/create/update/delete | GET cache on reads; CRUD mutation invalidates cache |
| `/users` | User Management list/create/update/delete | GET cache on reads; CRUD mutation invalidates cache |
| `/users/{id}/role` | Assign user role | Mutation |
| `/roles` | Role Management list/create/update/delete | GET cache on reads; CRUD mutation invalidates cache |
| `/roles/{id}/permissions` | Open/edit role permissions | GET cache on read; mutation on save |
| `/permissions` | Permission selector/filter | GET cache 15s |

### Reports and audit

| API | Called when | Duration behavior |
|---|---|---|
| `GET /reports` | Reports page list | GET cache 15s |
| `POST /reports` | Create report | Mutation |
| `PUT /reports/{id}` | Update report | Mutation |
| `DELETE /reports/{id}` | Delete report | Mutation |
| `GET /reports/daily` | Daily Report page | GET cache 15s; report aggregation dependent |
| `GET /audit-logs` | Audit Logs page | GET cache 15s; page/filter dependent |

## Refresh And Call Frequency

| Area | Frequency |
|---|---:|
| API GET cache | 15s |
| React Query global stale time | 30s |
| SNMP device list query stale time | 15s |
| Device detail query stale time | 10s |
| Latest SNMP metrics hooks | 30s |
| SNMP capabilities | 60s |
| Topology refresh | 30s |
| Manual topology change check | 120s |
| Device Monitoring metrics/status history | 15s |
| Realtime device stream helper default | 5s |
| Realtime metrics stream helper default | 2s |
| Realtime alerts stream helper default | 10s |
| SSE streams | Continuous until page unmounts/connection closes |

## Duration Interpretation

The current frontend can report only these timing facts without instrumentation:

- Cache hit: immediate from memory/session storage.
- Cache miss: waits for `fetch()` response and JSON parsing.
- React Query retry: a failed query can execute twice because global retry is `1`.
- Live SNMP: duration is controlled by backend collector/network timeout and device response.
- SSE: intentionally does not finish like a normal request.

For actual milliseconds per API, capture one browser session and export the Network log. Record request URL, start time, duration, status, response size, TTFB, and whether the result was cached. Backend SNMP responses that include `collection_ms` should be recorded separately from total browser duration.

## Highest Optimization Risk Areas

1. Live SNMP module calls without a client timeout.
2. Pages using direct `useEffect` loaders instead of shared query caching.
3. Aggregate `/overview`, `/device-metrics`, and monitoring status calls started together.
4. 30-second topology refresh and continuous monitoring streams.
5. List pages that reload after every mutation instead of updating/invalidation at row level.
6. Large history/table requests with high `limit` or long `hours` windows.
