# Agnigate NMS - Complete System Documentation

Date: 2026-08-25

Audience: non-technical users, testers, support engineers, and developers

This document explains how the current NMS application works from the browser
to the backend, database, SNMP device, and back again. It describes the code as
it exists today. It is documentation, not a redesign proposal.

## 1. What This Application Does

Agnigate NMS is a network monitoring system. It can:

- Store devices, interfaces, users, vendors, sites, alerts, and events.
- Test and monitor devices through SNMP.
- Read CPU, memory, storage, interface, environment, VLAN, LLDP, routing,
  ARP, MAC-table, system, inventory, and topology information.
- Run scheduled polling in the background.
- Show stored/latest metrics in dashboards without polling the device on every
  screen load.
- Discover devices from an IP/subnet.
- Display live health, topology, traffic, alerts, and monitoring history.

The most important distinction is this:

```text
DB read page       = reads already stored data; normally fast; no SNMP request
Live SNMP page     = contacts the device now; slower; can timeout
Background poll    = contacts device on a schedule and saves the result
```

## 2. Big Picture Architecture

```text
User browser
  |
  | React page, React Query, requestJson(), Bearer token
  v
FastAPI application (backend/main.py)
  |
  +--> Authentication and permission checks
  |
  +--> Normal CRUD route ----------------------> PostgreSQL
  |
  +--> Dashboard/overview route ---------------> Redis, then PostgreSQL
  |
  +--> Stored monitoring route ----------------> PostgreSQL latest/history tables
  |
  +--> Live SNMP route ------------------------> SNMP device -> normalize -> collector
  |
  +--> Discovery route ------------------------> scan/probe -> SNMP -> save device
  |
  +--> Scheduler ------------------------------> SNMP module poll -> latest/history DB
```

Main backend entry point: `hardik/backend/main.py`

The application registers these router groups:

- `routes.py`: authentication, users, roles, devices, interfaces, alerts,
  events, reports, metrics, dashboard summary, and standard CRUD.
- `snmp_device_routes.py`: per-device SNMP capabilities, polling, live module
  endpoints, latest values, monitoring configuration, and SNMP device list.
- `discovery_routes.py`: IP/ICMP/TCP/ARP/DNS/SNMP discovery, chunked scans,
  discovery monitoring, analytics, and discovery streaming.
- `overview_routes.py`: `/overview`, service status, kill-all, and daily report.
- `monitoring_data_routes.py`: database-only monitoring data API.
- `manual_topology_routes.py`: saved manual topology snapshots and reconcile.
- `legacy_routes.py`: old compatibility endpoints under `/api/...`.

## 3. Browser Startup and Security

### Login

Page: `/login`

1. User enters email and password.
2. Frontend calls `POST /api/v1/auth/login`.
3. Backend verifies the user password and returns a JWT access token.
4. Frontend stores the token in memory and local storage.
5. Every later API request sends:

```text
Authorization: Bearer <token>
```

Frontend files:

- `figma design/src/pages/Login.tsx`
- `figma design/src/components/AuthContext.tsx`
- `figma design/src/lib/api.ts`

### Protected pages

`ProtectedLayout` checks whether the user is logged in. If there is no valid
login state, the user is sent to `/login`. `withPermission(...)` checks the
required permission for each page. A logged-in user can still receive an
Access Denied screen if the required permission is missing.

Frontend files:

- `figma design/src/components/ProtectedLayout.tsx`
- `figma design/src/routes.tsx`
- `figma design/src/features/snmp/routes.tsx`

### Shared layout

`Layout` stays around the child page and provides:

- Sidebar navigation.
- Theme switcher.
- Clock.
- Back button.
- Notification/alert panel.
- Page-view audit logging.

It also loads alert data at startup and then approximately every 60 seconds
while the tab is visible. Page-view logging is throttled per route for 30
seconds.

File: `figma design/src/components/Layout.tsx`

## 4. How Frontend API Calls Work

Most pages do not call `fetch` directly. They use functions from:

`figma design/src/lib/api.ts`

The normal flow is:

```text
Page
  -> api.ts function
  -> requestJson()
  -> add API base URL and Bearer token
  -> fetch()
  -> parse JSON or throw an error
```

### Frontend caching

`requestJson()` has a short in-memory GET cache. A normal GET can be reused for
the configured cache window. Requests with an AbortSignal bypass that cache.
Important manual refresh paths now pass a signal so the user gets current data.

React Query also keeps query data in memory. It controls loading, refetching,
stale time, and invalidation. A page refresh button normally calls `refetch()`.

### Error display

If the backend returns an error, `requestJson()` turns it into a message such
as:

```text
Request failed: 500
Request failed: 502 - No SNMP response received before timeout
```

The page decides whether to show a banner, toast, popup, or error screen.

## 5. Backend Request Lifecycle

For every FastAPI request, the current lifecycle is:

```text
HTTP request
  -> request timing middleware creates request_id
  -> route and permission dependency
  -> route function
  -> DB and/or SNMP work
  -> JSON response
  -> timing log
```

The instrumentation logs:

- `request_id`
- HTTP method
- route
- status code
- total duration in milliseconds
- DB duration and query count
- SNMP duration
- collector duration

Requests above 500 ms are logged as `slow_api`.

File: `hardik/backend/observability.py`

### Timeouts

Current settings are configurable through environment variables/settings:

- `SNMP_REQUEST_TIMEOUT`: timeout for an individual SNMP request.
- `SNMP_RETRIES`: number of SNMP retries.
- `SNMP_OPERATION_TIMEOUT`: upper bound for the SNMP operation wrapper.

Defaults in `hardik/backend/config/settings.py` are approximately 3 seconds,
1 retry, and 120 seconds for the complete operation. A request can still feel
slow when a live route performs many sequential walks, because the operation
contains more than one network action.

## 6. Database: What Is Stored

The database is PostgreSQL through SQLAlchemy. The connection/session setup is
in `hardik/backend/database/session.py`.

### Core inventory tables

- `devices`: main device record, IP, name, status, last seen, vendor/type links.
- `device_credentials`: encrypted SNMP credential metadata.
- `interfaces`: general interface inventory used by normal CRUD pages.
- `vendors`, `device_types`, `sites`, `organizations`.

### Identity and capability tables

- `device_identity`: discovered hostname, vendor, model, system description,
  serial, firmware, roles, and confidence/source information.
- `device_capabilities`: boolean capability flags plus detailed collector
  evidence in JSON.
- `oid_cache`: remembered OID support results.

### Latest-value tables

These hold the newest value used by fast dashboard/detail reads:

- `latest_cpu`
- `latest_memory`
- `latest_storage`
- `latest_interfaces`
- `latest_environment`

### History and normalized SNMP tables

- `polling_history`: every poll attempt, module, result, error, and duration.
- `cpu_statistics`, `memory_statistics`, `storage_statistics`.
- `interface_statistics`: counter samples and calculated traffic values.
- `device_interfaces`: normalized SNMP interface identity.
- `vlan_information`, `lldp_neighbors`, `routing_table`.
- `system_health`, `device_inventory`, alarms, traps, and related records.

The latest tables answer “what is the most recent known value?” The history
tables answer “what happened over time?”

## 7. SNMP Collection Flow

### Full collection

The full SNMP path is implemented by:

`hardik/backend/snmp/collector.py`

For one device it generally does:

1. Read system identity OIDs such as description, object ID, uptime, name,
   contact, and location.
2. Detect vendor and device type.
3. Read vendor scalar OIDs and UCD-SNMP scalar OIDs.
4. Walk standard table roots: interfaces, CPU, memory/storage, entity/sensors,
   LLDP, VLAN, MAC FDB, routing, ARP, and related tables.
5. Normalize raw OID values into a common internal device object.
6. Build an OID registry for supported/vendor-specific values.
7. Run the collector list.
8. Return a stable result containing `collectors`, `unsupported`, timestamps,
   and collection duration.

The full collector list includes system, CPU, memory, storage, interfaces,
environment, VLAN, LLDP, CDP, routing, ARP, MAC table, firewall, wireless,
inventory, topology, and health.

### Interface-specific or module-specific collection

The service also has `collect_domain(host, domain)`. It reads identity values,
walks only the configured domain roots, normalizes the result, and runs only
that collector. The scheduler and optimized module routes use this path where
implemented.

### Normalization

Raw SNMP responses are not directly shown to the user. The normalization layer
converts vendor-specific or differently formatted values into consistent names
such as `utilization_percent`, `oper_status`, `speed_bps`, `vlan_id`, and
`next_hop`.

Files:

- `hardik/backend/snmp/normalizer.py`
- `hardik/backend/snmp/vendor_detector.py`
- `hardik/backend/snmp/oid_mapper.py`
- `hardik/backend/snmp/oid_catalog.py`

## 8. SNMP Module Guide

The following table explains each module in simple language.

| Module | What it shows | Typical source | If unavailable |
|---|---|---|---|
| System | device description, uptime, name, identity | system SNMP OIDs / stored identity | device may not expose system OIDs |
| CPU | utilization, per-core values, load | host/UCD/vendor CPU OIDs | device may not expose CPU MIB |
| Memory | used, total, free, utilization | host/UCD/vendor memory OIDs | device may not expose memory MIB |
| Storage | volumes, mount names, used/free space | HOST-RESOURCES storage table | device may return no storage rows |
| Interfaces | port names, status, speed, counters | IF-MIB and IF-X-MIB | interface table missing or access denied |
| Environment | temperature, sensors, power | ENTITY-SENSOR/vendor sensor OIDs | no sensors or unsupported MIB |
| VLAN | VLAN IDs and names | Q-BRIDGE/BRIDGE VLAN tables | switch does not expose VLAN table |
| LLDP | neighbors and remote ports | LLDP-MIB | LLDP disabled or no neighbors |
| CDP | Cisco neighbor information | Cisco CDP MIB | non-Cisco device or CDP disabled |
| Routing | destination, next hop, mask/route data | IP forwarding table | routing table unavailable |
| ARP | IP to MAC mappings | IP-MIB ARP table | ARP table not exposed |
| MAC table | learned MAC addresses and ports | Bridge/Q-Bridge FDB | switch does not expose FDB |
| Inventory | hardware identity and components | ENTITY-MIB and identity data | inventory MIB unavailable |
| Health | collector/device health state | derived from collection results | no successful health evidence |
| Topology | links/neighbor relationship | LLDP/CDP and stored topology | no neighbor/link evidence |
| Firewall | firewall-specific sessions/metrics | vendor enterprise OIDs | device is not a supported firewall |
| Wireless | wireless/SSID values | vendor wireless OIDs | wireless MIB unavailable |

A red capability tile means “the last stored evidence says unsupported or no
data.” It does not necessarily mean the IP address is unreachable. A green tile
means the system has evidence from a collector or stored latest data.

## 9. Background Polling

The scheduler is in:

`hardik/backend/services/snmp_polling.py`

At application startup it reconstructs monitoring jobs from the database. Each
job is identified by:

```text
device_id + module_name
```

The normal scheduler flow is:

```text
MonitoringConfig says module is enabled
  -> scheduler waits until next_poll_at
  -> SNMPPoller loads device and encrypted credentials
  -> capability check
  -> single-module SNMP collect_domain()
  -> latest table update
  -> history row update
  -> capability detail update
  -> next poll scheduled
```

Important default intervals include:

- Interfaces: 15 seconds.
- CPU and memory: 60 seconds.
- Environment, ARP: approximately 300 seconds.
- System and storage: approximately 300 seconds.
- VLAN, LLDP, CDP, routing, MAC table: approximately 600 seconds.
- Inventory: daily.

The exact active interval comes from `MonitoringConfig`, so a user setting can
override the default.

Duplicate polling is protected using a device/module single-flight guard in
`hardik/backend/services/snmp_poll_guard.py`. This protects scheduler polls,
manual polls, repeated start actions, and repeated frontend requests from
running the same device/module simultaneously.

## 10. Main Application Pages

The following are the normal non-SNMP pages. Each page is protected by a
permission and usually reads or mutates PostgreSQL data through `routes.py`.

| URL | Page | What the user sees | Main data |
|---|---|---|---|
| `/` | Dashboard | health cards, performance, traffic, alerts, top devices | `/dashboard/summary`, `/overview`, latest/history tables |
| `/topology` | Network Topology | automatically discovered/current network graph | `/snmp/topology`, device details, monitoring data |
| `/manual-topology` | Manual Topology | user-created device cards and links | manual topology snapshot APIs plus health checks |
| `/isp` | ISP Monitoring | WAN/ISP status and traffic view | overview/device/traffic APIs and periodic refresh |
| `/incidents` | Incidents | incident list and status | incident CRUD APIs |
| `/alerts` | Alerts Management | open/resolved alerts and actions | alerts CRUD, acknowledge, resolve |
| `/packet-analysis` | Packet Analysis | packet/traffic analysis view | packet/metric endpoints and refresh |
| `/servers` | Server Monitoring | server health, metrics, interfaces | devices, metrics, interfaces, monitoring data |
| `/device-monitoring` | Device Monitoring List | monitored device inventory | devices and monitoring APIs |
| `/device-monitoring/:id` | Device Monitoring Detail | one device health and history | device, metrics, status history |
| `/roles` | Role Management | roles and permissions | role/permission CRUD |
| `/users` | User Management | user accounts and roles | user CRUD and role assignment |
| `/organizations` | Organizations | organization records | organization CRUD |
| `/vendors` | Vendors | vendor records | vendor CRUD |
| `/sites` | Sites | site records | site CRUD |
| `/reports/daily` | Daily Report | generated/report history | report endpoints |
| `/alerts-management` | Alerts Management | alternate alert route | alert APIs |
| `/events` | Events | event timeline | event CRUD |
| `/notifications` | Notifications | notifications | notification CRUD |
| `/audit-logs` | Audit Logs | user/action history | audit log API |
| `/monitoring-jobs` | Monitoring Jobs | configured jobs | monitoring job CRUD |
| `/device-credentials` | Device Credentials | credential metadata/forms | encrypted credential APIs |
| `/device-types` | Device Types | device type catalog | device type CRUD |
| `/interfaces` | Interface List | normal interface inventory | `/interfaces` CRUD and interface history |

Some pages are currently disabled in the route table, including the older
standalone firewall, forensics, compliance, Nginx, and thresholds routes. Their
source files still exist, but a user cannot reach them through the active route
configuration unless the route is enabled.

### Dashboard (`/`)

The dashboard is a summary page, not a live SNMP poll page. It reads persisted
device state, latest metrics, interface history, alert counts, and overview
statistics. The backend dashboard summary uses Redis cache-aside when Redis is
available, then falls back to PostgreSQL.

The dashboard may refresh summary data on a timer. It should be understood as
“latest stored monitoring state,” not an immediate device probe.

Frontend: `figma design/src/pages/Dashboard.tsx`

Backend: `hardik/backend/api/routes.py` and `overview_routes.py`

### Network Topology (`/topology`)

This page shows current/reachable topology data. It requests topology data and
then loads details for selected nodes. It avoids showing deleted/stale device
inventory as active topology nodes. A forced refresh can call
`GET /api/v1/snmp/topology?refresh=true`, which may perform live collection.

Frontend: `figma design/src/pages/Topology.tsx`

### Manual Topology (`/manual-topology`)

This page is user-managed. It stores snapshots/cards and relationships rather
than automatically deleting database devices. It also performs periodic health
checks for displayed devices and can show an offline warning once per session.

Frontend: `figma design/src/pages/ManualTopology.tsx`

Backend: `hardik/backend/api/manual_topology_routes.py`

### CRUD management pages

Users, roles, organizations, vendors, sites, device types, credentials, alerts,
events, notifications, reports, and monitoring jobs follow the same pattern:

```text
page load -> GET list
create/edit -> POST or PATCH
delete -> DELETE
success -> local state/query refresh
```

The data is persisted in PostgreSQL. These pages do not normally contact SNMP
devices unless the specific action explicitly starts discovery or monitoring.

## 11. SNMP Pages and Routes

### SNMP landing/monitoring (`/snmp`, `/snmp-monitoring`)

This is the SNMP monitoring workspace. It loads database-backed monitoring data,
capabilities, and monitoring configuration. It can start/stop module monitoring
and can request a manual poll.

### SNMP dashboard (`/snmp/dashboard` and `/:deviceId`)

Shows an SNMP-focused overview for all devices or one device. It combines:

- Device identity/status.
- Capability map.
- Latest CPU/memory/storage/interface/environment values.
- Polling status/history.

The normal overview read is intended to be DB-backed. A manual poll button is a
separate action and can contact SNMP.

### SNMP device inventory (`/snmp/devices`)

This is the page shown in the screenshot. It lists SNMP-verified devices only.
The query supports pagination, search, device status, device type, vendor,
monitoring status, and SNMP status. The current UI fixes the SNMP status to
`verified`, so ordinary devices without verified SNMP identity are not shown on
this page. They remain in the normal device inventory.

Backend list route: `GET /api/v1/snmp/devices`

The list combines:

- `devices` row.
- `device_credentials` for SNMP version.
- `device_identity` for verified identity/vendor.
- `monitoring_configs` for running modules and last poll.

The refresh button refetches the list with a cache-bypass signal, so it requests
current data instead of reusing the short frontend GET cache.

### Add SNMP device (`/snmp/devices/add`)

The form sends IP, SNMP v2c/v3 settings, community or security credentials,
and optional identity fields. Backend stores encrypted secret material, tests
or discovers the device depending on the action, and can create monitoring
configuration.

### Device details (`/snmp/devices/:deviceId`)

This is DB-backed device detail. It reads identity, credentials metadata,
capabilities, monitoring configuration, latest values, and recent polling
history. It does not need to perform live SNMP for a normal page load.

Manual refresh bypasses the frontend cache.

### Capabilities (`/snmp/devices/:deviceId/capabilities`)

Shows a tile for every known module. The green/red result is based on
`DeviceCapabilities` and its detail JSON. The tile itself is not a fresh probe.
To change a capability, run discovery or a supported poll path.

### Monitoring configuration (`/snmp/devices/:deviceId/monitoring`)

Shows module jobs and allows start, stop, or interval changes. Starting a job
changes scheduler configuration; it does not necessarily mean a live SNMP poll
has completed at that exact moment.

### Polling history (`/snmp/devices/:deviceId/polling`)

Reads `polling_history` rows. It shows success, timeout, unsupported, error,
duration, and timestamps. It is historical DB data, not a live probe.

### OID Explorer (`/snmp/devices/:deviceId/oids`)

Shows cached/discovered OID information and the OID tree. It is intended for
inspection. It does not change OIDs merely by opening the page.

## 12. Dedicated SNMP Monitoring Pages

Each dedicated page follows the same conceptual structure:

```text
load capabilities
  -> if unsupported, show unavailable state
  -> otherwise load module data
  -> render cards/table/chart
  -> optional monitoring controls
```

| URL | Page | Data endpoint family | Normal read behavior |
|---|---|---|---|
| `.../cpu` | CPU Monitoring | `/snmp/devices/{id}/cpu` and latest/history | current implementation may use live or stored path depending on route code |
| `.../memory` | Memory Monitoring | `/snmp/devices/{id}/memory` and latest/history | shows normalized memory values |
| `.../storage` | Storage Monitoring | `/snmp/devices/{id}/storage` and latest/history | shows volumes and utilization |
| `.../interfaces` | Interface Monitoring | `/snmp/devices/{id}/interfaces`, latest, history | shows ports, status, speed, counters |
| `.../interfaces/{interfaceId}` | Interface Details | interface detail/history APIs | one selected interface and time series |
| `.../environment` | Environment Monitoring | `/snmp/devices/{id}/environment` | sensors, temperature, power/status |
| `.../vlan` | VLAN Monitoring | `/snmp/devices/{id}/vlans` | VLAN table |
| `.../lldp` | LLDP Monitoring | `/snmp/devices/{id}/lldp` | neighbors and remote ports |
| `.../routing` | Routing Monitoring | `/snmp/devices/{id}/routing` | routes and next hops |
| `.../:moduleId` | Generic Module | registry-selected endpoint | generic cards/table based on module registry |
| `.../topology` | Device Topology | device topology endpoint | neighbor/link view |

The module registry is in:

`figma design/src/features/snmp/modules/snmpModuleRegistry.ts`

It defines module labels, routes, endpoint names, supported checks, columns,
summary fields, and rendering metadata. This is why many module pages can share
the same shell and table components.

## 13. Live SNMP vs Stored Data

### Stored/database-only examples

These normally read PostgreSQL and do not contact the device:

- `/devices`
- `/device-metrics`
- `/snmp/devices`
- `/snmp/devices/{id}`
- `/snmp/devices/{id}/overview`
- `/snmp/devices/{id}/metrics/latest`
- `/snmp/devices/{id}/polling-history`
- `/snmp/devices/{id}/polling-stats`
- `/monitoring/data`
- `/dashboard/summary`
- `/overview` after cache miss

### Live SNMP examples

These can contact a device during the request:

- `/snmp/devices/{id}/system`
- `/snmp/devices/{id}/cpu`
- `/snmp/devices/{id}/memory`
- `/snmp/devices/{id}/storage`
- `/snmp/devices/{id}/interfaces`
- `/snmp/devices/{id}/environment`
- `/snmp/devices/{id}/vlans`
- `/snmp/devices/{id}/lldp`
- `/snmp/devices/{id}/routing`
- `/snmp/devices/{id}/arp`
- `/snmp/devices/{id}/mac-table`
- `POST /snmp/devices/{id}/poll`
- discovery and test-SNMP actions

The exact behavior of a module endpoint must be checked in
`hardik/backend/api/snmp_device_routes.py`. A green capability does not by
itself prove that the page made a live request; it only proves stored support
evidence exists.

## 14. Discovery Flow

Discovery has two different meanings in the product.

### IP/subnet discovery

The discovery panel can scan a subnet using ICMP, SNMP, TCP, ARP, DNS, HTTP,
SSH, WMI, or selected modules. Chunked scan APIs allow progress to be shown
without waiting for one huge request.

```text
user selects subnet/modules
  -> discovery scan starts
  -> worker checks candidate IPs
  -> optional SNMP probe
  -> results stream/status endpoint
  -> user chooses devices to add
  -> backend upserts device/identity/credentials/capability data
```

### Per-device SNMP discovery

`POST /api/v1/snmp/devices/{id}/discover` runs identity and capability discovery
for an existing device. It can:

1. Run full SNMP collection.
2. Resolve vendor/model/hostname/identity.
3. Determine supported collectors.
4. Save identity and capabilities.
5. Persist collector results into latest/history tables.
6. Save an event saying discovery completed.

Files:

- `hardik/backend/api/discovery_routes.py`
- `hardik/backend/api/snmp_device_routes.py`
- `hardik/backend/services/chunked_discovery.py`

## 15. Dashboard and Overview Data Flow

### `/dashboard/summary`

The route builds summary counts and latest values from PostgreSQL. It uses a
Redis cache-aside key when Redis is available. On a cache hit, PostgreSQL work
is avoided. On a cache miss or Redis failure, PostgreSQL is used and the API
still returns a response.

It does not intentionally perform live SNMP.

### `/overview?hours=24`

The overview route builds the larger operational dashboard: inventory health,
poll success/failure, CPU/memory/storage summaries, interface history, alerts,
and top traffic devices. It also uses Redis cache-aside and falls back to
PostgreSQL.

If it returns HTTP 500, the browser displays `Request failed: 500`; the exact
root cause must be read from backend logs using the request ID and stack trace.
The frontend `N/A` values are a consequence of the failed response, not proof
that the device has no data.

## 16. Redis Cache

Redis is optional and fail-open. The helper is:

`hardik/backend/cache/redis_cache.py`

Selected read APIs use it:

- `/dashboard/summary`
- `/overview`
- `/snmp/devices/{id}/overview`
- `/snmp/devices/{id}/metrics/latest`

The cache stores response-like JSON only. SNMP credentials, passwords, tokens,
and secrets must not be cached. If Redis is stopped or unreachable, the helper
returns no cached value and PostgreSQL remains the source of truth.

Configured values:

- `REDIS_URL`
- `REDIS_CACHE_TTL_SECONDS`

Cache is not a replacement for polling. Polling writes the database; cache
only shortens repeated reads.

## 17. Common User Questions

### Why does a module show red/unavailable?

The stored capability evidence says the last probe/collector did not produce a
supported value. Possible reasons are:

- SNMP credentials are wrong.
- The device uses a different SNMP version/security setting.
- The device does not expose that MIB/OID.
- The feature is disabled on the device.
- No rows exist, for example no LLDP neighbors or no VLAN table.
- Discovery has not been run after adding the device.
- A previous capability result was stale.

Run device discovery or the module's supported poll path and inspect polling
history. Do not assume a red tile means the whole device is offline.

### Why does a page show old data?

There are three possible sources:

1. Browser/React Query cache.
2. Redis cache for selected summary/overview APIs.
3. PostgreSQL latest tables, which are updated by background polling.

The SNMP device list and device detail refresh paths now bypass the frontend
short GET cache. A refresh still cannot show a value that has never been
successfully persisted or collected.

### Why is live SNMP slow?

Live collection can perform identity GETs, scalar GETs, and sequential table
walks. A switch with large interface, MAC, ARP, VLAN, or routing tables can take
longer than a small server. Timeout settings bound individual/overall work, but
do not make a large walk instant.

### Why do I see only interfaces on a switch?

Interfaces are commonly supported and polled frequently. Other modules appear
only when their collector returns supported data and capability persistence has
recorded it. Domain polling must preserve previously discovered capabilities;
the current persistence logic was corrected so a single interface poll does not
erase the other module flags.

## 18. Error and Troubleshooting Flow

When a page fails:

1. Open browser Network tab.
2. Copy request method, URL, status, and response body.
3. Note the `X-Request-ID` if returned/logged.
4. Search backend logs for that request ID.
5. Check whether the route was DB-only or live SNMP.
6. For SNMP errors, verify IP, port 161, SNMP version, credentials, and device
   firewall/ACL.
7. Check `polling_history` for timeout, authentication failure, unsupported OID,
   or no-data status.
8. Check `device_capabilities.updated_at` to see how old the capability result
   is.

Useful status meanings:

- `verified`: identity/capability evidence is present.
- `unknown`: device exists but verified SNMP identity is absent.
- `running`: monitoring job is enabled and active.
- `stopped`: monitoring job is disabled/stopped.
- `not_supported`: collector does not have usable data for that device.
- `timeout`: device did not respond within configured limits.

## 19. File Map for Future Maintenance

### Frontend foundation

- `figma design/src/App.tsx`: application provider/router shell.
- `figma design/src/routes.tsx`: normal page routes.
- `figma design/src/features/snmp/routes.tsx`: SNMP routes.
- `figma design/src/lib/api.ts`: API functions, auth header, GET cache.
- `figma design/src/components/Layout.tsx`: shell, alerts, page views, theme.
- `figma design/src/components/ProtectedLayout.tsx`: auth/permission gate.
- `figma design/src/features/snmp/hooks/useSnmpQueries.ts`: SNMP React Query hooks.
- `figma design/src/features/snmp/modules/snmpModuleRegistry.ts`: module metadata.

### Backend foundation

- `hardik/backend/main.py`: FastAPI startup, middleware, router registration.
- `hardik/backend/api/routes.py`: core CRUD/auth/dashboard APIs.
- `hardik/backend/api/snmp_device_routes.py`: SNMP device APIs.
- `hardik/backend/api/discovery_routes.py`: discovery and monitoring APIs.
- `hardik/backend/api/overview_routes.py`: overview/service APIs.
- `hardik/backend/api/monitoring_data_routes.py`: stored monitoring API.
- `hardik/backend/api/manual_topology_routes.py`: manual topology persistence.
- `hardik/backend/services/snmp_polling.py`: scheduler and persistence.
- `hardik/backend/services/snmp_poll_guard.py`: duplicate poll protection.
- `hardik/backend/snmp/client.py`: SNMP transport, timeout, retry.
- `hardik/backend/snmp/collector.py`: full/domain SNMP orchestration.
- `hardik/backend/snmp/collectors/`: individual module collectors.
- `hardik/backend/snmp/normalizer.py`: raw-to-normalized conversion.
- `hardik/backend/snmp/identity/`: identity and capability discovery.
- `hardik/backend/models/snmp.py`: latest/history/monitoring models.
- `hardik/backend/models/identity.py`: identity/capability models.
- `hardik/backend/observability.py`: request/DB/SNMP timing logs.
- `hardik/backend/cache/redis_cache.py`: optional cache-aside helper.

## 20. One Complete Example: Switch Interface Data

Suppose the switch is `192.168.100.2`.

### First setup

1. User adds the switch and SNMP credential.
2. Backend stores the device and encrypted credential metadata.
3. Discovery probes SNMP and runs the interface collector.
4. Normalized interface rows are saved.
5. Capability `interfaces=true` is saved.

### Background operation

1. Monitoring configuration enables `interfaces`.
2. Scheduler wakes up at the configured interval.
3. Poller calls only the interface domain collector.
4. SNMP reads IF-MIB counters/status.
5. Poller updates latest interface values and history.
6. The interface page reads the latest stored result.

### User presses Refresh

1. React Query refetches the API.
2. The SNMP list/detail refresh bypasses frontend GET cache.
3. Backend reads current database rows.
4. The page shows the most recent successful persisted poll.
5. Refresh alone does not perform live SNMP unless the user presses a separate
   manual poll/discovery action.

## 21. Current Boundaries and Important Expectations

- A normal GET page is not automatically a live SNMP test.
- A capability tile is stored evidence, not a continuous health guarantee.
- Refresh gets current backend data, but it cannot create missing metric data.
- Deleting and re-adding a device is not a normal fix for stale capability data;
  discovery/polling should be used first.
- Redis is optional and should never be treated as the permanent source of
  monitoring truth.
- Large SNMP tables can still be expensive during live collection.
- Database history and latest values are separate from the legacy CRUD device
  tables; both may appear in different pages.

## 22. Short Glossary

- **API**: a URL contract used by the frontend to ask the backend for data.
- **CRUD**: create, read, update, delete.
- **Collector**: code that understands one SNMP module's OIDs and output.
- **Discovery**: finding or identifying a device and its supported capabilities.
- **Latest table**: one newest known value for fast display.
- **Polling history**: record of every attempt and its outcome.
- **MIB/OID**: SNMP data namespace/address exposed by a device.
- **Redis**: temporary fast cache; not permanent database storage.
- **Scheduler**: background service that runs polls at intervals.
- **SNMP v2c/v3**: protocol/security modes used to talk to devices.
- **Single-flight guard**: prevents duplicate polls for the same device/module.

## 23. Audit Limitations

This document is based on static source inspection and the current route/model
implementation. Runtime values such as exact response duration, actual device
support, current Redis availability, and live database row counts depend on the
environment and must be checked from logs/API responses at runtime.

