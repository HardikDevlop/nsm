# Current NMS Baseline

Date: 2026-08-29
Repository: `/home/agnigate/Desktop/NMS`
Baseline commit: `beb29b4`

## Purpose and Scope

This is a behavior-neutral baseline of the existing NMS. It was created by
static inspection of the current frontend, backend, models, migrations,
collectors, dependencies, tests, and project documentation.

No application behavior was changed. No existing source, model, migration,
collector, API contract, or test was removed or rewritten.

Runtime values such as live device reachability, database row counts, response
latency, scheduler state, and actual vendor support require a running
environment and are not claimed by this document.

## System Boundary

The repository contains two primary applications:

- Frontend: `figma design/`, React and TypeScript served by Vite.
- Backend: `hardik/`, FastAPI, SQLAlchemy, PostgreSQL, SNMP, and schedulers.

The backend is consolidated into one FastAPI application. `backend/main.py`
registers the core CRUD/RBAC router, discovery router, SNMP router, manual
topology router, monitoring-data router, Linux monitoring router, overview
router, and legacy compatibility router.

## End-to-End Workflow

```text
Browser route
  -> protected layout and permission guard
  -> frontend API client / React Query or page effect
  -> FastAPI router
  -> authentication and permission dependency where required
  -> PostgreSQL read/write and/or live SNMP operation
  -> normalize raw SNMP values
  -> run selected collector(s)
  -> persist latest values, history, capabilities, events, and alerts
  -> JSON response or scheduled next poll
  -> frontend card, table, chart, topology, alert, or report
```

There are three different data paths:

1. DB-backed read: reads stored inventory, latest values, history, alerts, or
   reports without contacting a device.
2. Live SNMP read: contacts the device, runs transport, normalization, and a
   collector, then returns the current result.
3. Background poll: the scheduler contacts the device at a configured
   interval, persists results, evaluates thresholds, and records polling
   history.

## Frontend Inventory

### Application shell

- `figma design/src/main.tsx`: frontend entry point.
- `figma design/src/App.tsx`: application composition.
- `figma design/src/routes.tsx`: protected and general route tree.
- `figma design/src/components/ProtectedLayout.tsx`: authentication and
  permission gating.
- `figma design/src/components/Layout.tsx`: navigation shell, theme, clock,
  alert panel, and page-view audit logging.
- `figma design/src/components/AuthContext.tsx`: login/session state.
- `figma design/src/lib/api.ts`: API base URL, bearer token requests, GET
  cache, in-flight deduplication, and mutation cache invalidation.
- `figma design/src/lib/queryProvider.tsx`: React Query configuration.

### Active general routes

The route tree currently includes:

| Route | Component / purpose |
|---|---|
| `/login` | Login |
| `/` | Dashboard |
| `/topology` | Automatic topology view |
| `/manual-topology` | Manual topology snapshots and reconciliation |
| `/isp` | ISP monitoring/discovery workspace |
| `/incidents` | Alert-derived incident view |
| `/alerts` and `/alerts-management` | Alert CRUD and lifecycle actions |
| `/packet-analysis` | Packet/traffic analysis view |
| `/linux-servers` | Linux server detection and monitoring |
| `/device-monitoring` | Device monitoring list |
| `/device-monitoring/:deviceId` | Device health and status history |
| `/roles` | Role management |
| `/users` | User management |
| `/organizations` | Organization management |
| `/vendors` | Vendor management |
| `/sites` | Site management |
| `/reports/daily` | Daily report |
| `/reports/management` | Report CRUD/export management |
| `/events` | Event management |
| `/notifications` | Notification management |
| `/audit-logs` | Audit log view |
| `/monitoring-jobs` | Monitoring job CRUD |
| `/device-credentials` | Credential management |
| `/device-types` | Device type management |
| `/interfaces` | General interface inventory |
| `/thresholds` | Threshold CRUD |

### Active SNMP routes

SNMP routes are defined in `figma design/src/features/snmp/routes.tsx`:

- `/snmp` and `/snmp-monitoring`: SNMP workspace.
- `/snmp/dashboard` and `/snmp/dashboard/:deviceId`: SNMP dashboards.
- `/snmp/devices`: SNMP device inventory.
- `/snmp/devices/add`: add and validate SNMP device.
- `/snmp/devices/:deviceId`: device details.
- `/snmp/devices/:deviceId/monitoring`: module scheduler configuration.
- Device module pages for CPU, memory, interfaces, storage, environment, VLAN,
  LLDP, routing, topology, OIDs, polling, capabilities, and generic modules.
- `/snmp/capabilities` and `/snmp/capabilities/:deviceId`: capability views.

### Frontend data behavior

- SNMP pages use `useSnmpQueries.ts`, module hooks, and React Query for
  device/module data.
- General CRUD pages mostly use direct functions from `lib/api.ts`, loading on
  mount and reloading after mutations.
- Device monitoring uses status streams/fallback refresh paths.
- Dashboard and monitoring pages use periodic refresh according to the page or
  hook configuration.
- Topology data is API-driven; node layout is also persisted in browser
  storage.
- The layout alert panel may use session storage during startup/failure before
  fresh API data is available.

## Backend Router and API Inventory

### Core router: `hardik/backend/api/routes.py`

Mounted with `/api/v1` and includes:

- Health, login, current-user, users, roles, permissions.
- Organizations, sites, vendors, device types.
- Devices and device credentials.
- General interfaces, metrics, monitoring jobs, thresholds.
- Alerts: list, create, update, acknowledge, resolve, clear.
- Events and notifications.
- Reports, daily reports, management reports, and export.
- Audit logs and page-view audit events.
- Dashboard summary.
- General monitoring and discovery compatibility actions.

### Discovery router: `hardik/backend/api/discovery_routes.py`

Mounted with `/api/v1` and includes:

- Local subnet, IP, ICMP, TCP, ARP, DNS, HTTP, SNMP, SSH, and WMI discovery.
- Device profiling, discovery summary, inventory, chunked scan, progress, and
  streaming status.
- Discovery device import and stored-device checks.
- ICMP, SNMP, syslog, and trap ingestion endpoints.
- Alert/event/topology analytics endpoints.
- Discovery monitoring start, stop, start-all, stop-all, status, and stream.
- Device history, discovery planning, and MAC vendor lookup/CRUD.

### SNMP router: `hardik/backend/api/snmp_device_routes.py`

Mounted with `/api/v1` and includes:

- SNMP device create/test/discovery flows.
- Identity and capability reads.
- Manual polling and device overview.
- Live system, CPU, memory, storage, interface, environment, LLDP, routing,
  VLAN, CDP, ARP, MAC table, inventory, health, firewall, wireless, and
  topology reads.
- OID list and OID tree.
- Polling history and polling statistics.
- Automatic topology.
- Per-module monitoring configuration, start, stop, update, and status.
- Latest CPU, memory, interface, storage, and environment values.
- SNMP device list and detail routes.

### Other routers

- `manual_topology_routes.py`: manual topology snapshots, changes,
  reconciliation, and change resolution.
- `monitoring_data_routes.py`: stored monitoring data reads/writes.
- `overview_routes.py`: overview, service status, daily report, and monitoring
  kill-all operation.
- `linux_monitoring/api.py`: Linux server CRUD, SSH/SNMPv3 detection,
  monitoring, metrics, security events, credentials, and configuration.
- `legacy_routes.py`: `/api/inventory`, `/api/discovery/modules`, and
  `/api/discovery/summary` compatibility endpoints.

## Database and Models

### Core models in `hardik/backend/models/__init__.py`

- `Role`, `Permission`, `User`.
- `Organization`, `Site`, `Vendor`, `DeviceType`.
- `Device`, `DeviceCredential`, `Interface`.
- `MonitoringJob`, `DeviceMetric`, `Threshold`.
- `Alert`, `Event`, `Notification`, `Report`.
- `AuditLog`, `DeviceStatusHistory`.

### SNMP models in `hardik/backend/models/snmp.py`

- Inventory and credentials: `device_inventory`, `snmp_credentials`.
- Performance/history: `device_performance`, `cpu_statistics`,
  `memory_statistics`, `storage_statistics`, `environment_statistics`,
  `interface_statistics`.
- Network data: `vlan_information`, `lldp_neighbors`, `routing_table`,
  `device_interfaces`.
- Device state: `system_health`, `polling_history`, `alarms`, `monitoring_configs`,
  `monitoring_fields`.
- Latest-value tables: `latest_cpu`, `latest_memory`, `latest_storage`,
  `latest_interface`, `latest_environment`.
- Discovery/support: `snmp_traps`, `oid_cache`, `vendor_profiles`.

### Identity and capability models in `hardik/backend/models/identity.py`

- `device_identity`: discovered hostname, vendor, model, serial, firmware,
  role, source, and confidence.
- `device_capabilities`: per-device collector support flags and detailed
  capability evidence.
- `vendor_ouis`: MAC OUI knowledge.
- `device_products`: product knowledge used by identity resolution.

### Manual topology models

`hardik/backend/models/manual_topology.py` stores manual topology snapshots and
manual topology changes.

### Linux monitoring models

`hardik/backend/linux_monitoring/models.py` defines:

- `linux_servers`.
- Linux SSH and SNMP credentials.
- Monitoring configuration.
- Current and historical metric tables.
- Linux interfaces and disks.
- Linux security events.

## Migration Baseline

Migrations are application-managed and idempotent in
`hardik/backend/database/migrations.py`. The migration registry currently
contains:

- `20260821_0001_device_credentials_columns`.
- `20260821_0002_performance_indexes`.
- `20260821_0003_device_types_metadata`.
- `20260821_0004_device_topology_metadata`.
- `20260825_0005_linux_server_monitoring_foundation`.
- `20260825_0006_linux_server_inventory`.
- `20260825_0007_linux_server_metric_columns`.
- `20260825_0008_linux_security_events`.
- `20260825_0009_linux_monitoring_scheduler`.
- `20260825_0010_linux_metric_retention`.

At startup, the application registers model metadata, creates the non-Linux
tables if needed, runs pending migrations, and seeds RBAC plus OUI/product
knowledge. Linux tables are handled through their isolated migration helpers.

## SNMP Transport and Collection

### Transport and security

- `hardik/backend/snmp/client.py`: pysnmp transport adapter, GET/walk,
  timeout, retry, executor isolation, and walk row cap.
- `hardik/backend/snmp/credentials.py`: credential shape.
- `hardik/backend/snmp/security.py`: SNMP authentication/privacy protocol
  mappings.
- `hardik/backend/utils/crypto.py`: encrypted secret handling.
- `hardik/backend/snmp/compat.py`: compatibility helpers.

SNMP v2c and SNMP v3 are preserved requirements of this baseline.

### Collection pipeline

`hardik/backend/snmp/collector.py` runs this sequence:

1. Identity GET for standard system values.
2. Vendor and device-type detection.
3. Vendor scalar GETs and UCD-SNMP scalar GETs.
4. Standard and vendor table walks.
5. Raw value normalization.
6. Dynamic OID registry construction.
7. Ordered collector execution.
8. Stable collector response construction.

OID knowledge is held in `hardik/backend/snmp/oid_catalog.py`; the collection
code does not rely on external JSON/YAML OID files.

### Active collectors

The ordered collector set currently includes:

- System
- CPU
- Memory
- Storage
- Interfaces
- Environment
- VLAN
- LLDP
- CDP
- Routing
- ARP
- MAC table
- Firewall
- Wireless
- Inventory
- Topology
- Health

Collector implementations are in `hardik/backend/snmp/collectors/`. Shared
response and normalization contracts are in `collectors/base.py` and
`normalizer.py`.

### Discovery support modules

The separate discovery modules cover IP, ICMP, TCP, ARP, DNS, HTTP, SNMP, SSH,
and WMI probing, plus profiling and network range handling.

## Scheduler and Persistence Flow

`hardik/backend/services/snmp_polling.py` provides the centralized SNMP polling
service:

1. Load enabled `monitoring_configs`.
2. Reconstruct scheduled jobs after restart.
3. Map device/module to a collector.
4. Check device credentials and discovered capability.
5. Use the single-flight poll guard to avoid duplicate device/module polls.
6. Run synchronous SNMP collection in a worker thread.
7. Persist latest values and module history.
8. Update capability detail and polling history.
9. Evaluate threshold alerts.
10. Commit the transaction and schedule the next poll.

Configured module defaults include system, CPU, memory, storage, interfaces,
environment, VLAN, LLDP, CDP, routing, ARP, MAC table, inventory, topology,
firewall, wireless, and health. The interface default is 15 seconds; other
modules have their own intervals. UI-approved interval values are constrained
by `ALLOWED_INTERVALS`.

The application starts this scheduler during FastAPI lifespan and shuts it
down during application shutdown. Linux monitoring has a separate scheduler
that restores enabled Linux servers.

## Alerts, Events, Topology, and Reports

- Threshold evaluation is performed during scheduled module persistence for
  CPU, memory, storage, interface-down, and environment conditions.
- Alert records support open, acknowledged, and resolved lifecycle states.
- Events and notifications have CRUD APIs and frontend pages.
- Automatic topology uses SNMP topology data and LLDP/CDP-related collectors.
- Manual topology stores snapshots and explicit changes separately.
- Dashboard and overview responses read stored state and latest values.
- Daily and management report endpoints exist, with frontend report pages and
  export functionality.
- Audit logs capture backend/user activity, including frontend page views.

## Dependencies

### Backend

Declared in `hardik/backend/requirements.txt`:

- FastAPI and Uvicorn.
- SQLAlchemy and psycopg PostgreSQL driver.
- Pydantic and pydantic-settings.
- python-jose, passlib, bcrypt, and cryptography.
- pysnmp 6.x range.
- APScheduler 3.x range.
- Paramiko for SSH/Linux monitoring.
- Redis client.

### Frontend

Declared in `figma design/package.json`:

- React and React DOM.
- React Router.
- TanStack React Query.
- Recharts.
- SweetAlert2.
- XLSX export library.
- Vite, TypeScript, Tailwind Vite plugin, and formatting tooling.

## Test Inventory

### Collector and SNMP unit tests

Located in `hardik/tests/`:

- Collector response/base contract tests.
- CPU collector tests.
- Memory collector tests.
- General collector contract tests.
- OID registry tests.
- Vendor detector tests.
- Identity resolver tests.
- SNMP normalizer tests.
- Capability discovery tests.

### Discovery and preservation tests

- `test_snmpv3_timeout_exploration.py`: SNMPv3 timeout bug exploration.
- `test_device_deletion_exploration.py`: discovery deletion bug exploration.
- `test_snmpv2c_preservation.py`: v2c discovery and credential preservation.
- `test_icmp_preservation.py`: ICMP-only discovery preservation.
- `test_mixed_protocol_preservation.py`: ICMP/SNMP coexistence preservation.
- `test_soft_deleted_device_undelete.py`: soft-deleted device behavior.

### Integration/smoke tests

- `hardik/backend/backend_smoke_test.py`: authenticated CRUD/API smoke flow.
- `hardik/backend/unified_smoke_test.py`: consolidated backend, discovery,
  analytics, legacy, and protected endpoint smoke flow.
- Root-level API scripts: `test_direct.py`, `test_monitoring_api.py`, and
  `test_frontend_api.js`.

The repository test documentation distinguishes exploratory tests from
preservation tests. Exploratory test expectations must be interpreted with
care because they document historical bug conditions, not only current
success criteria.

## Implemented Feature Baseline

The current source provides the following product areas:

- Authentication, JWT session handling, RBAC, permission-protected routes.
- Device, credential, site, organization, vendor, and type management.
- ICMP, TCP, ARP, DNS, HTTP, SNMP, SSH, and WMI discovery paths.
- SNMP v2c/v3 transport and encrypted credential storage.
- Dynamic device identity and capability discovery.
- Device/system, resource, interface, network table, environment, inventory,
  health, firewall, wireless, and topology collection.
- Scheduled polling, latest/history persistence, alerts, events, and status
  history.
- Automatic and manual topology workflows.
- Linux server detection and monitoring foundation.
- Dashboards, monitoring pages, reports, exports, notifications, and audit
  logs.
- API compatibility routes retained for the existing frontend.

## Risk and Verification Areas

These are baseline risks or areas requiring runtime verification. They are
listed without changing behavior.

### High priority

- No verified 5,000-device load/scalability result is stored in the repository.
- Full live SNMP collection performs many sequential GET/walk operations; large
  tables can be expensive.
- Some API routes perform live SNMP work synchronously from route handlers.
- Discovery can have high database query and persistence volume.
- The backend audit identifies repeated/full collection work in some
  module-specific routes.
- Production HA, database failover, scheduler failover, backup restore, and DR
  evidence are not established by source inspection.

### Functional boundary risks

- NetFlow, sFlow, IPFIX, J-Flow, NetStream, NBAR, AVC, and deep flow analytics
  are not represented as a complete ingestion/storage/analytics subsystem.
- Full application performance monitoring is not established by the current
  route/model inventory.
- Full CMDB, ITSM/helpdesk, problem/change management, knowledge base, and RCA
  workflows are not established by the current models/routes.
- Configuration backup, baseline, diff, compliance, and rollback workflows
  are not established as a complete subsystem.
- Virtualization, advanced QoS, and advanced BGP analytics are not established
  as complete subsystems.

### Frontend/data-truth risks

- `AttackPath.tsx` and `Compliance.tsx` contain business-looking derived or
  hardcoded presentation data; they should not be treated as authoritative
  security/compliance engines.
- Browser storage is used for some topology layouts and alert UI state.
- A normal DB-backed page read does not prove a live SNMP poll occurred.
- Collector support is device/MIB dependent; a capability flag is not a
  guarantee that every optional field is available.
- A legacy SNMP dashboard path has documented loading/error-path risk.
- The SNMPv3 form/discovery issue report documents a subnet-form UX limitation
  that should be rechecked at runtime before relying on that workflow.

### Evidence gaps

The repository does not by itself prove OEM support contracts, India deployment
references, certifications, tender sign-offs, warranty, or production load
results. Those require external evidence and should be maintained separately
from application source.

## Compatibility Constraints for Future Work

Future implementation work must preserve unless a verified migration and
contract review explicitly approves otherwise:

- SNMP v2c and v3 behavior.
- Existing OID catalog and collectors.
- JWT/RBAC and permission names.
- Existing PostgreSQL data and migration history.
- Discovery behavior and preservation guarantees.
- Monitoring scheduler and per-module configuration.
- Alerts, events, topology, reports, and audit paths.
- Existing frontend API response shapes and legacy compatibility routes.

Every future change should inspect its related frontend, API route, schema,
model, migration, scheduler/collector path, and regression tests before edits.
