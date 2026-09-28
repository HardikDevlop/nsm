# AgniGate NMS — Page-by-Page Functional Reference

Source-grounded reference for the current frontend routes. Source audit date: 2026-09-21. “Implemented in source” does not mean runtime success; device support, data freshness, credentials, permissions, and deployment configuration must be verified in the target environment.

## Reading this document

- Route and permission authority: `figma design/src/routes.tsx` and `src/features/snmp/routes.tsx`.
- Sidebar authority: `src/components/Sidebar.tsx`.
- UI/API authority: each page/component and `src/lib/api.ts`.
- Backend mappings are summarized from `hardik/backend/api/`, services, collectors, and models.
- `N/A`, empty, unsupported, stale, and unknown are not interchangeable. The UI can display a value only when the corresponding source data exists.

## Route checklist

| Route | Page | Class | Permission | Sidebar |
|---|---|---|---|---|
| `/` | Dashboard | Primary | `dashboard:read` | Yes |
| `/manual-topology` | Manual Topology | Primary | `topology:read` | Yes |
| `/manual-topology/device/:deviceId/ports` | Device Port Map | Child/detail | `topology:read` | No |
| `/isp` | IP Scan / ISP Monitoring | Primary | `isp:read` | Yes |
| `/incidents` | Incidents | Routed hidden | `incidents:read` | No |
| `/alerts` | Alert Management | Management | `alerts:read` | Yes/alias |
| `/packet-analysis` | Packet Analysis | Primary | `packet_analysis:read` | Yes |
| `/flow-analytics` | Flow Analytics | Routed hidden | `flows:read` | No |
| `/apm` | APM | Routed hidden | `apm:read` | No |
| `/cmdb` | CMDB | Routed hidden | `cmdb:read` | No |
| `/rca` | RCA | Routed hidden | `rca:read` | No |
| `/incident-management` | Incident Management | Routed hidden | `incidents:read` | No |
| `/problem-management` | Problem Management | Routed hidden | `problems:read` | No |
| `/change-management` | Change Management | Routed hidden | `changes:read` | No |
| `/knowledge-base` | Knowledge Base | Routed hidden | `knowledge:read` | No |
| `/configuration-backups` | Configuration Backups | Routed hidden | `config_backups:read` | No |
| `/configuration-compliance` | Configuration Compliance | Routed hidden | `config_compliance:read` | No |
| `/availability` | Availability | Routed hidden | `availability:read` | No |
| `/qos` | QoS | Routed hidden | `qos:read` | No |
| `/bgp` | BGP | Routed hidden | `bgp:read` | No |
| `/snmp` | SNMP Monitoring | Primary/module | `devices:read` | Feature entry |
| `/snmp-monitoring` | SNMP Monitoring | Legacy alias | `devices:read` | No |
| `/snmp/dashboard` | SNMP Dashboard | Module | `devices:read` | No |
| `/snmp/dashboard/:deviceId` | SNMP Dashboard | Detail | `devices:read` | No |
| `/snmp/devices` | SNMP Devices | Primary | `devices:read` | Yes |
| `/snmp/devices/add` | Add SNMP Device | Action | `devices:create` | No |
| `/snmp/devices/:deviceId` | SNMP Device Details | Detail | `devices:read` | No |
| `/snmp/devices/:deviceId/monitoring` | SNMP Monitoring Config | Detail/action | `devices:update` | No |
| `/snmp/devices/:deviceId/cpu` | CPU Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/memory` | Memory Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/interfaces` | Interface Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/interfaces/:interfaceId` | Interface Details | Child/module | `devices:read` | No |
| `/snmp/devices/:deviceId/storage` | Storage Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/environment` | Environment Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/vlan` | VLAN Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/lldp` | LLDP Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/routing` | Routing Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/topology` | Topology Module | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/oids` | OID Explorer | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/polling` | Polling Monitoring | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/capabilities` | SNMP Capabilities | Module | `devices:read` | No |
| `/snmp/devices/:deviceId/:moduleId` | Generic SNMP Module | Dynamic child | `devices:read` | No |
| `/snmp/capabilities` | SNMP Capabilities | Module | `devices:read` | No |
| `/snmp/capabilities/:deviceId` | Device Capabilities | Detail | `devices:read` | No |
| `/linux-servers` | Linux Server Monitoring | Primary | `linux_servers:read` | Yes |
| `/device-monitoring` | Device Monitoring List | Primary | `device_monitoring:read` | Yes |
| `/device-monitoring/:deviceId` | Device Monitoring Detail | Detail | `device_monitoring:read` | No |
| `/roles` | Role Management | Admin | `roles:read` | Yes |
| `/users` | User Management | Admin | `users:read` | Yes |
| `/organizations` | Organizations | Admin | `organizations:read` | Yes |
| `/vendors` | Vendors | Admin | `vendors:read` | Yes |
| `/sites` | Sites | Admin | `sites:read` | Yes |
| `/device-types` | Device Types | Admin | `device_types:read` | Yes |
| `/device-credentials` | Device Credentials | Admin | `device_credentials:read` | Yes |
| `/reports/daily` | Daily Report redirect | Redirect | none | No |
| `/reports/management` | Report Center | Management | `reports:read` | Yes |
| `/alerts-management` | Alert Management | Management alias | `alerts:read` | No |
| `/events` | Events | Management | `events:read` | Yes |
| `/syslog` | Syslog Management | Management | `syslog:read` | Yes |
| `/notifications` | Notifications | Management | `notifications:read` | Yes |
| `/audit-logs` | Audit Logs | Admin/management | `audit_logs:read` | Yes |
| `/monitoring-jobs` | Monitoring Jobs | Management | `monitoring_jobs:read` | Yes |
| `/login` | Login | Public | none | No |
| `/unauthorized` | Unauthorized | Public/error | none | No |
| `*` | Error Page | Error | none | No |

## Shared page behavior

`Layout`, `ProtectedLayout`, `withPermission`, `Sidebar`, header/notification controls, `ThemeContext`, `GlassCard`, status badges, pagination/query helpers, chart wrappers, toast/confirm helpers, and SNMP shells are reused across page families. Backend permission checks remain authoritative even when the frontend hides a button. Refresh behavior is page-specific: manual buttons, React Query refetches, component intervals, scheduler-persisted data, and SSE are not interchangeable.

## Dashboard

**Route:** `/`  **Permission:** `dashboard:read`  **Navigation:** Overview sidebar  **Component:** `src/pages/Dashboard.tsx`  **Primary users:** NOC operator, network administrator.

### What it does

Provides a consolidated view of inventory, device health, traffic, polling, alerts, topology/network summaries, and recent device activity. It does not itself prove that a device is reachable; displayed values originate from persisted/API data.

### Visible sections

- Header: Network Operations title, live indicator, time range selector and Refresh.
- KPI cards: total devices, online, offline, SNMP enabled/failed, critical/warning alerts, interfaces down.
- System Vitals: availability, poll success, average CPU, average memory gauges.
- Performance/traffic: RX/TX cards and charts, health radar, status share.
- Inventory/alerts: device type map/donut, alert distribution, top devices by traffic.
- Network information: LLDP/CDP neighbors, VLANs, routes, ARP, MAC entries and topology nodes.
- Recent Devices/Activity: device, IP, type, status/health reason and last poll.

### Actions and data

| Action | Result/API | Write/background | Failure/empty behavior |
|---|---|---|---|
| Change time range | Re-runs `getOverview(hours)` | No; reads scheduler-persisted data | Empty charts/cards show N/A/no stored data. |
| Refresh | Calls `getOverview` again | No | Error state displays request failure. |
| Click KPI/device links | Navigates to device/alerts/SNMP pages | No | Permission guard may deny target. |

**Source chain:** Dashboard state → `getOverview()` → overview/dashboard API → overview routes/services → persisted device, SNMP, traffic, alert and health data. Health derivation is backend-authoritative; confirm exact precedence in `derive_device_health()` before final operational policy.

**Live behavior:** initial load, range changes, and a source-defined visibility-aware interval in the page. It is not a direct device poll; scheduler persistence and API freshness determine data age.

## IP Scan / ISP Monitoring

**Route:** `/isp`  **Permission:** `isp:read`  **Navigation:** IP Scan sidebar  **Component:** `src/pages/ISPMonitoring.tsx`  **Primary users:** operator/administrator.

The page accepts a single IP/range/CIDR target, selects discovery modules, starts chunked discovery, shows progress/results, checks stored devices, and supports adding devices and starting/stopping monitoring. The SNMP subnet discovery modal is a child flow.

**Visible controls:** discovery target, ICMP/SNMP module cards, Discover Devices, progress/result panels, stored/duplicate indicators, device result details, add/store actions, monitoring controls and SNMP discovery modal.

**Operator flow:** open page → enter target → choose modules → Discover → monitor job progress/SSE or status → inspect results → check duplicate/stored state → add devices → optionally start monitoring. Invalid target, cancellation, failed job, empty result and API error states are represented; exact wording comes from page/API source.

**Source chain:** UI state → `detectLocalSubnet`, `startChunkedDiscovery`, `getChunkedDiscoveryStatus`, `streamChunkedDiscovery`, `addDiscoveredDevices`, `checkStoredDevices`, monitoring helpers → `/discovery/*` routes → discovery modules/services → device/discovery models. Writes occur when adding devices or changing monitoring. Discovery is network and credential dependent.

## SNMP Monitoring overview

**Routes:** `/snmp`, `/snmp-monitoring` (alias)  **Permission:** `devices:read`  **Component:** `features/snmp/pages/SNMPMonitoring.tsx`.

Shows SNMP monitoring title, device/interface/trap counts, service controls for ping/polling/auto refresh, selected device, module cards and polling/health summaries. Refresh reloads page data. Service start/stop/restart actions call discovery/monitoring or SNMP monitoring endpoints and can trigger background jobs. Stopped, failed, unsupported and no-data states must remain distinct.

## SNMP Devices

**Route:** `/snmp/devices`  **Permission:** `devices:read`  **Sidebar:** SNMP Devices. **Component:** `features/snmp/pages/SNMPDevices.tsx`.

Displays searchable/paginated device inventory, hostname/IP/status, SNMP identity and monitoring state. Add opens `/snmp/devices/add`; edit opens an edit dialog; delete is destructive and confirmation behavior must follow the component; details navigate to device detail. Device/module monitoring controls start/stop/update jobs. Data uses device list/options/detail, credential/config and latest monitoring helpers.

SNMP v2c/v3 selection and credential fields are implemented in add/configuration components. Secret values are intentionally omitted here. Create/update/delete are writes; list/search/refresh are reads. Unsupported credentials, timeout/authentication failures and missing collector data are not equivalent to offline.

## Add SNMP Device

**Route:** `/snmp/devices/add`  **Permission:** `devices:create`  **Component:** `AddSNMPDevice.tsx`.

Collects device identity and SNMP v2c/v3 credentials/security options, validates form fields, submits device/credential data, and navigates or reports errors. It may enable monitoring only through explicit source actions. Backend validation and authorization remain authoritative.

## SNMP Device Details and modules

**Base route:** `/snmp/devices/:deviceId`  **Permission:** `devices:read`  **Component:** `SNMPDeviceDetails.tsx`.

The detail shell exposes identity, health, latest data, module navigation, refresh and monitoring/configuration links. Module routes use typed pages or `SNMPGenericModulePage`.

| Module/page | Operational display | Source/API | Empty/unsupported behavior |
|---|---|---|---|
| System | identity/system information and overview | `getSNMPDeviceOverview`, `getSNMPSystemInfo` | N/A/no-data/unsupported from API |
| CPU | utilization/current/history where page exposes it | CPU helpers, CPU collector/latest metrics | No sample is not zero |
| Memory | RAM/swap metrics/history where exposed | memory helpers/collector | No sample/unsupported distinct |
| Storage | volumes/capacity/utilization | storage helpers/collector | Vendor/OID dependent |
| Interfaces | interface inventory/current/history | interface helpers/collector | Interface absence is not device offline |
| Environment | sensors/temperature/fan/power data where returned | environment helper/collector | Unsupported sensors remain unsupported |
| VLAN | VLAN table/data | VLAN helper/collector | Empty VLAN response is not failure |
| LLDP/CDP | neighbor evidence where returned | LLDP/CDP collectors/topology paths | Evidence may be unavailable |
| Routing | routing table | routing helper/collector | OID/device dependent |
| ARP/MAC | ARP/FDB evidence and mapping | ARP/MAC collectors, topology helpers | Unresolved IP is explicitly unresolved |
| Firewall/Wireless/Inventory/Health | only where current generic/collector page exposes data | corresponding collectors/routes | Source exists but device/UI coverage requires verification |
| Topology | topology/evidence view | topology APIs/builder | Inferred relationships are not confirmed cabling |
| OID Explorer | OID cache/tree and explorer controls | OID helpers/catalog | Unsupported OID is not failed device |
| Polling | job/history/statistics/status | polling helpers/routes | Configured job is not proof of successful poll |
| Capabilities | supported/enabled module capability view | capability helpers/collector | Capability absence requires runtime context |

All module pages may expose refresh or React Query refetch according to their component. Exact intervals must be read from each module source; do not generalize one module’s refresh behavior to all modules.

## Interfaces

**Routes:** `/snmp/devices/:deviceId/interfaces`, `/snmp/devices/:deviceId/interfaces/:interfaceId`.

The interface list/detail surfaces actual fields used by the component such as interface identity/name, ifIndex, description, admin/operational status, speed, RX/TX, utilization, errors and historical values where available. `N/A`, null and unavailable history remain data-quality states. The source chain is interface helper → SNMP device routes/collector → persisted latest/history interface records. Refresh is component/query based, not necessarily a direct poll.

## MAC table and port topology

MAC/FDB data is grouped by port and shown with MAC count, VLANs, classification and MAC→IP mapping. ARP correlation may resolve an IP or show `IP NOT RESOLVED`. Port summary and 2D topology components expose endpoint/uplink/unknown classifications. These are evidence/inference views: a learned MAC or FDB/ARP correlation must not be documented as confirmed physical cabling unless the source explicitly confirms it.

## Manual Topology

**Route:** `/manual-topology`  **Permission:** `topology:read`  **Sidebar:** Manual Topology  **Component:** `src/pages/ManualTopology.tsx`.

### Modes and objects

Manual, Actual and Compare modes are implemented in the page/state model. Managed devices come from inventory; manual devices/links can be placed and edited. Nodes can be moved, selected, inspected, edited, deleted/removed according to the page action. Links use source/target devices and ports; duplicate/occupancy validation is source-controlled.

### Evidence and reconciliation

SNMP collection, LLDP/CDP, MAC/FDB and ARP evidence feed the shared topology builder. Actual topology is evidence-derived; manual topology is user-authored. Compare mode exposes changes with status/evidence/confidence and resolve actions such as keeping manual or accepting a real change where implemented. Save/load uses manual topology snapshots; resolving a change updates reconciliation state, not necessarily a device’s physical truth.

### Health and navigation

Health overlays display online/green, offline/red, degraded/amber and stale/unknown neutral semantics where source styles support them. Runtime health overlay does not mutate the saved topology snapshot. Port Map navigation opens `/manual-topology/device/:deviceId/ports`. Auto-refresh/freshness behavior is page-specific and must be verified from the current effect/query code; do not call snapshot data live merely because an overlay refreshes.

## Device Port Map

**Route:** `/manual-topology/device/:deviceId/ports`  **Permission:** `topology:read`  **Component:** `DevicePortMap.tsx`.

Shows physical/logical/management ports, status, port identity, search/filter, device focus, port selection, peer/connection information and topology navigation where present. It uses device/interface/SNMP topology data. Occupancy and inferred peers remain evidence semantics. Back/navigation returns to topology or device context; writes are only those exposed by explicit topology actions.

## Device Monitoring

**Routes:** `/device-monitoring`, `/device-monitoring/:deviceId`  **Permissions:** `device_monitoring:read`.

List page provides device selection/status and navigation. Detail page shows current reachability/health, monitoring configuration, latest metrics and status history, with refresh/start/stop actions where exposed. Source chain: device/config/status-history/latest-metric helpers → device and monitoring routes/services → persisted device/status/metric records. Start/stop changes monitoring state; it does not by itself prove a successful poll.

## Linux Server Monitoring

**Route:** `/linux-servers`  **Permission:** `linux_servers:read`  **Component:** `LinuxServerMonitoring.tsx`.

The page exposes server list/selection, detection/onboarding, SSH validation, credentials/configuration dialogs, current metrics, historical charts, monitoring start/stop, edit/delete and retention/security status where rendered. Visible metrics must be taken from the page: backend-only schema fields are not automatically UI fields. Source chain is Linux API → detector/security/service/scheduler → server, credential, configuration and metric models. SSH/platform/network configuration is required; no universal metric availability is implied.

## Packet Analysis and Flow Analytics

**Routes:** `/packet-analysis` and `/flow-analytics` (Flow Analytics routed hidden from sidebar).

Document each current component’s actual cards, filters, charts and tables separately. Flow source includes records/trends and flow models including sFlow counter samples; packet page may consume related analytics. Source does not establish active NetFlow support. Identify displayed source as sFlow, IPFIX, combined or unknown only after tracing the page/API response fields. Sampling/source-quality information must be preserved; missing data is not zero traffic.

## Alerts, Events, Syslog and Notifications

### Alert Management — `/alerts`, `/alerts-management`

Shows alert list/detail fields that the current component renders: severity, status, device/source, timestamps, message and available filters/search. Acknowledge, resolve, clear or detail actions are documented only where present in component code. APIs are alert routes/helpers; writes are action-specific.

### Events — `/events`

Shows event records, source/device, severity/type, timestamps and filters/actions that the page renders. Events are not automatically alerts; keep the distinction made by the source models/routes.

### Syslog Management — `/syslog`

Shows syslog records and filters/search plus rule list/detail. Rule create/update/delete and enable/disable are writes; retention cleanup is a backend action where exposed. Record data comes from syslog routes/service and persisted syslog models. Facility/severity/source semantics must follow the current page fields.

### Notifications — `/notifications`

Shows notification records and read/unread or available actions as implemented. Source is notification API/state; do not assume it is a second alert store.

## Monitoring Jobs

**Route:** `/monitoring-jobs`  **Permission:** `monitoring_jobs:read`  **Sidebar:** management.

Displays configured job/device/module, interval, status, last poll/next poll/error fields where rendered. Restart action stops/starts a job through monitoring helpers and is a write/background action. Configured job rows are not identical to scheduler-registered jobs unless the page/API explicitly correlates them.

## Report Center

**Route:** `/reports/management`  **Permission:** `reports:read`  **Sidebar:** Report Center. `/reports/daily` redirects here with `preset=daily`.

Current implementation is Report Management, not a separate active Daily Report page. Document only period presets/options, device/site/protocol filters, report sections, Run Report and CSV/Excel controls actually rendered by `ReportManagement.tsx` and its API helpers. Availability, downtime, SNMP/ICMP, performance, interfaces, alerts/incidents and recommendations are included only where current response/UI supports them. Empty/N/A/stale output follows current data normalization; export contains what the current export endpoint returns, not an assumed full dashboard.

## Administration pages

| Page | Route/permission | Current UI purpose and writes |
|---|---|---|
| Role Management | `/roles`, `roles:read` | Role list/detail, permission assignments, create/update/delete where rendered. |
| User Management | `/users`, `users:read` | User list/form, role assignment, create/update/delete and validation. |
| Organizations | `/organizations`, `organizations:read` | Organization CRUD and list/detail fields. |
| Sites | `/sites`, `sites:read` | Site CRUD, organization association and validation. |
| Vendors | `/vendors`, `vendors:read` | Vendor CRUD/list fields. |
| Device Types | `/device-types`, `device_types:read` | Device type CRUD/classification. |
| Device Credentials | `/device-credentials`, `device_credentials:read` | Credential records/form/actions; secret values are not reproduced. |
| Audit Logs | `/audit-logs`, `audit_logs:read` | Audit record listing/filtering as rendered; normally read-only. |

Exact columns, pagination, modal confirmation, and validation are page-source details; each CRUD write maps to the corresponding `/api/v1` admin helper and backend route. Permissions may hide actions beyond page read access.

## Routed hidden business pages

`Incidents`, `IncidentManagement`, `ProblemManagement`, `ChangeManagement`, `KnowledgeBase`, `CMDB`, `RCA`, `Availability`, `ConfigurationBackups`, `ConfigurationCompliance`, `QoS`, `BGP`, `APM`, and `FlowAnalytics` are routed but several are commented out of the current sidebar. They remain documented routes, not implied normal operator workflow.

- Incident pages: incident list/detail, SLA/history/comments/attachments and acknowledge/resolve/reopen where rendered.
- Problem page: problem records, detail/history and incident relationships.
- Change page: submit/approve/reject/schedule/implementation/rollback/close workflow where rendered.
- Knowledge Base: search/filter, article CRUD, lifecycle, versions, feedback and cross-links.
- CMDB: CI types/items, relationships, history and sync.
- RCA: incident selection, analysis/results where rendered.
- Availability: reports, filters and CSV export where rendered.
- Configuration Backup: capture, version/compare/baseline-current views.
- Configuration Compliance: policies/violations and actions where rendered.
- QoS/BGP/APM: only current page fields and corresponding APIs; source presence is not runtime success.

## Authentication and error pages

### Login — `/login`

Public login form calls `/auth/login`; success stores the client token/session and enters protected routes. Failure displays the page’s error state. Secrets are never documented.

### Unauthorized — `/unauthorized`

Public denial page shown when permission/authorization prevents access. It does not grant access or change permissions.

### Error Page — `*` and route error elements

Fallback for unknown routes and route-level errors. The exact recovery controls must follow `ErrorPage.tsx`; it is not evidence that a backend operation failed in a particular way.

## Page dependency matrix

| Page family | Primary API/domain | Writes? | Background work? | Auto/live behavior | Export? | Detail routes |
|---|---|---:|---:|---|---:|---|
| Dashboard | overview | No | No direct start | interval/manual/range | No | device links |
| ISP/IP Scan | discovery | Yes | Yes, scan/monitor jobs | SSE/status | No | SNMP modal |
| SNMP devices | devices/SNMP | Yes | module jobs | query/manual | No | add/detail/modules |
| SNMP modules | SNMP module helpers | Some config | Polling may run backend | query/manual | Page-specific | module children |
| Manual topology | topology/snapshots | Yes | evidence collection where triggered | source-defined | No | port map |
| Port map | devices/interfaces/topology | Page-specific | No direct assumption | query/manual | No | topology |
| Device monitoring | device/metrics/history | Yes | monitoring jobs | query/manual | No | detail |
| Linux servers | linux API | Yes | server monitoring | query/history | No | none |
| Packet/flow | flow APIs | Usually no UI write | ingestion backend | query | Page-specific | none |
| Alerts/events/syslog | respective APIs | Actions/rules yes | service ingestion | query/manual | Page-specific | details |
| Report Center | reports | report definitions/export | No direct assumption | run/manual | CSV/Excel if rendered | none |
| Admin | CRUD APIs | Yes | No | query/manual | No | dialogs/details |
| ITSM hidden pages | ITSM APIs | Yes | Automation only where source | query/manual | Page-specific | details |

## Operator workflow map

Login → Overview → IP discovery → inspect/duplicate-check results → add/configure device → validate ICMP/SNMP → enable monitoring → inspect SNMP modules/interfaces/MAC/LLDP → Device Monitoring → Manual Topology/reconciliation → Alerts/Events/Syslog → optional Linux server and flow monitoring → incidents/problems/changes → Report Center. Optional stages are explicitly configuration/device dependent.

## Documentation status and limitations

This reference covers every declared route in the current route files and excludes the removed Network Topology page as an active page. Exact per-button HTTP methods, every field/column, and every page-specific timer require a further AST/call-site pass where the current source is highly dynamic or generic. Those cases are marked by the source-grounded limitation language above rather than invented behavior.

**Secrets exposed:** No.  
**Application code changed:** No.  
**Documentation only:** Yes.
