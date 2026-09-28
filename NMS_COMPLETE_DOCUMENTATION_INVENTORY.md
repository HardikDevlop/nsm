# AgniGate NMS — Complete Documentation Inventory

> Source audit date: 2026-09-21. Scope: repository source only. This is an inventory, not the final product manual. Runtime success, device compatibility, credentials, data freshness, and deployment health were not assumed from source presence.

## Audit rules and evidence

- Frontend route authority: `figma design/src/routes.tsx` and `figma design/src/features/snmp/routes.tsx`.
- Frontend navigation authority: `figma design/src/components/Sidebar.tsx`.
- Frontend API authority: `figma design/src/lib/api.ts`, feature-local API calls, and `fetch`/SSE consumers.
- Backend authority: `hardik/backend/main.py`, `hardik/backend/api/`, `hardik/backend/linux_monitoring/`, services, collectors, models, and configuration.
- Existing reports were used only as audit pointers; implementation claims below are based on source inspection.
- No secrets, passwords, JWT values, SNMP credentials, or tokens are reproduced.

## 1. Product architecture inventory

| Area | Purpose | Source files | Currently used | Notes |
|---|---|---|---|---|
| Frontend | React/Vite single-page NMS UI, lazy routes, React Query | `figma design/package.json`, `src/main.tsx`, `src/routes.tsx`, `src/components/` | YES | TypeScript, React 19, React Router, Recharts, Tailwind v4/Vite plugin. |
| Backend | FastAPI REST API and background services | `hardik/backend/main.py`, `backend/api/`, `backend/services/` | YES | Routers are included in `main.py` under `/api/v1` or router prefixes. |
| Database | SQLAlchemy persistence | `hardik/backend/database.py`, `backend/models/`, `backend/migrations/` if present | YES | PostgreSQL configuration is present; exact deployed DB requires runtime configuration. |
| Cache/lease | Redis cache and scheduler coordination | `backend/cache/redis_cache.py`, `backend/services/ha_scheduler.py`, settings | YES/CONFIG DEPENDENT | Redis lease behavior is implemented; availability depends on deployment configuration. |
| Scheduler | APScheduler/background polling and monitoring jobs | `backend/snmp/poll_scheduler.py`, `backend/linux_monitoring/scheduler.py`, `backend/services/ha_scheduler.py` | YES | Job restoration/ownership behavior must be confirmed in deployed runtime. |
| Authentication | JWT login, current-user validation, route permissions | `backend/auth/security.py`, `backend/api/routes.py`, `src/lib/api.ts`, `src/components/ProtectedLayout.tsx` | YES | Backend authorization and frontend permission guards both exist. |
| ICMP | Ping/discovery/reachability and realtime monitoring | `discovery_modules/icmp_discovery.py`, `backend/services/realtime_monitor.py`, `backend/services/availability.py`, discovery routes | YES | Exact effective intervals are configuration/runtime dependent. |
| SNMP v2c/v3 | Credentialed polling and collectors | `backend/snmp/client.py`, `credentials.py`, `security.py`, `polling.py`, `collectors/`, `snmp_device_routes.py` | YES | Source supports v2c/v3 paths; device/OID support varies by vendor/module. |
| SSH/Linux monitoring | Server detection, SSH metrics, history | `backend/linux_monitoring/` | YES/PARTIAL | Implemented metrics are defined in `metrics.py`/schemas; runtime SSH access is required. |
| Flow/packet | sFlow/IPFIX ingestion and analytics | `backend/api/flow_routes.py`, `backend/models/flow.py`, flow service/parser files | YES/PARTIAL | Active NetFlow support was not established by this audit. |
| Streaming | SSE for monitoring/discovery/topology | `src/lib/api.ts`, discovery routes, realtime services | YES | No WebSocket implementation was identified in the inspected paths. |
| Charts/export | Recharts; CSV/report downloads; XLSX dependency | `src/pages/`, `src/features/`, `src/lib/api.ts`, package.json | YES | Excel/CSV availability is page-specific. |
| Deployment | shell startup, Python requirements, frontend build | `hardik/start_*.sh`, `hardik/backend/requirements.txt`, `figma design/package.json`, `hardik/backend/main.py` | YES | Exact service manager/systemd unit inventory needs host-level verification. |

## 2. Complete frontend route inventory

Permission values below are the guards in source. `Sidebar` means an active sidebar entry; commented entries are not active sidebar navigation.

| Route | Page/component | Permission | Classification | Purpose/status |
|---|---|---|---|---|
| `/` | Dashboard | `dashboard:read` | Routed + sidebar | Overview metrics, health, traffic, topology/activity. Implemented. |
| `/manual-topology` | ManualTopology | `topology:read` | Routed + sidebar | Manual/actual/compare topology workflows. Implemented; runtime evidence dependent. |
| `/manual-topology/device/:deviceId/ports` | DevicePortMap | `topology:read` | Detail/child | Device port map. Implemented. |
| `/isp` | ISPMonitoring | `isp:read` | Routed + sidebar | IP/device discovery, monitoring controls, inventory. Implemented. |
| `/incidents` | Incidents | `incidents:read` | Routed, sidebar commented | Incident view; not active sidebar entry. |
| `/alerts`, `/alerts-management` | AlertsManagement | `alerts:read` | Routed/management | Alerts list and actions. |
| `/packet-analysis` | PacketAnalysis | `packet_analysis:read` | Routed + sidebar | Packet/analysis view. |
| `/flow-analytics` | FlowAnalytics | `flows:read` | Routed, sidebar commented | Flow analytics. |
| `/apm` | APM | `apm:read` | Routed, sidebar commented | Application health metrics. |
| `/cmdb` | CMDB | `cmdb:read` | Routed, sidebar commented | CI inventory, relationships, history. |
| `/rca` | RCA | `rca:read` | Routed, sidebar commented | Root-cause analysis. |
| `/incident-management` | IncidentManagement | `incidents:read` | Routed, sidebar commented | ITSM incident management. |
| `/problem-management` | ProblemManagement | `problems:read` | Routed, sidebar commented | Problem management. |
| `/change-management` | ChangeManagement | `changes:read` | Routed, sidebar commented | Change approval/implementation workflow. |
| `/knowledge-base` | KnowledgeBase | `knowledge:read` | Routed, sidebar commented | Articles, versions, relationships, feedback. |
| `/configuration-backups` | ConfigurationBackups | `config_backups:read` | Routed, sidebar commented | Device configuration capture/compare. |
| `/configuration-compliance` | ConfigurationCompliance | `config_compliance:read` | Routed, sidebar commented | Compliance policies/violations. |
| `/availability` | Availability | `availability:read` | Routed, sidebar commented | Availability reports/export. |
| `/qos` | QoS | `qos:read` | Routed, sidebar commented | QoS samples/view. |
| `/bgp` | BGP | `bgp:read` | Routed, sidebar commented | BGP observations/neighbors. |
| `/snmp` | SNMPMonitoring | `devices:read` | Routed + feature entry | SNMP overview/controls. |
| `/snmp-monitoring` | SNMPMonitoring | `devices:read` | Legacy/alias route | Same page as `/snmp`. |
| `/snmp/dashboard` | SNMPDashboard | `devices:read` | Routed/detail | SNMP dashboard. |
| `/snmp/dashboard/:deviceId` | SNMPDashboard | `devices:read` | Detail | Device-specific SNMP dashboard. |
| `/snmp/devices` | SNMPDevices | `devices:read` | Routed + sidebar | SNMP device inventory. |
| `/snmp/devices/add` | AddSNMPDevice | `devices:create` | Detail/action | Add SNMP device. |
| `/snmp/devices/:deviceId` | SNMPDeviceDetails | `devices:read` | Detail | Device details and modules. |
| `/snmp/devices/:deviceId/monitoring` | SNMPMonitoringConfig | `devices:update` | Detail/action | Module monitoring configuration. |
| `/snmp/devices/:deviceId/cpu` | SNMPCPUMonitoring | `devices:read` | Detail/module | CPU metrics. |
| `/snmp/devices/:deviceId/memory` | SNMPMemoryMonitoring | `devices:read` | Detail/module | Memory metrics. |
| `/snmp/devices/:deviceId/interfaces` | SNMPInterfaceMonitoring | `devices:read` | Detail/module | Interface metrics/history. |
| `/snmp/devices/:deviceId/interfaces/:interfaceId` | SNMPInterfaceDetails | `devices:read` | Detail/child | One interface details. |
| `/snmp/devices/:deviceId/storage` | SNMPStorageMonitoring | `devices:read` | Detail/module | Storage volumes. |
| `/snmp/devices/:deviceId/environment` | SNMPEnvironmentMonitoring | `devices:read` | Detail/module | Sensors/environment. |
| `/snmp/devices/:deviceId/vlan` | SNMPVLANMonitoring | `devices:read` | Detail/module | VLAN data. |
| `/snmp/devices/:deviceId/lldp` | SNMPLLDPMonitoring | `devices:read` | Detail/module | LLDP neighbors. |
| `/snmp/devices/:deviceId/routing` | SNMPRoutingMonitoring | `devices:read` | Detail/module | Routing table. |
| `/snmp/devices/:deviceId/topology` | SNMPGenericModulePage | `devices:read` | Detail/module | Generic topology module. |
| `/snmp/devices/:deviceId/oids` | SNMPOIDExplorer | `devices:read` | Detail/module | OID cache/tree exploration. |
| `/snmp/devices/:deviceId/polling` | SNMPPollingMonitoring | `devices:read` | Detail/module | Polling history/statistics. |
| `/snmp/devices/:deviceId/capabilities` | SNMPCapabilities | `devices:read` | Detail/module | Capability view. |
| `/snmp/devices/:deviceId/:moduleId` | SNMPGenericModulePage | `devices:read` | Generic child route | Dynamic module fallback. |
| `/snmp/capabilities`, `/snmp/capabilities/:deviceId` | SNMPCapabilities | `devices:read` | Routed/detail | Capability overview/device capability. |
| `/linux-servers` | LinuxServerMonitoring | `linux_servers:read` | Routed + sidebar | SSH/Linux server onboarding and monitoring. |
| `/device-monitoring` | DeviceMonitoringList | `device_monitoring:read` | Routed + sidebar | Device monitoring inventory. |
| `/device-monitoring/:deviceId` | DeviceMonitoring | `device_monitoring:read` | Detail | Device monitoring detail. |
| `/roles`, `/users`, `/organizations`, `/sites`, `/vendors`, `/device-types`, `/device-credentials` | Corresponding admin pages | matching `*:read` | Routed + admin sidebar | Administration CRUD. |
| `/reports/daily` | Redirect | none | Redirect | Redirects to `/reports/management?preset=daily`. |
| `/reports/management` | ReportManagement | `reports:read` | Routed + sidebar | Unified report center. |
| `/events`, `/syslog`, `/notifications`, `/audit-logs`, `/monitoring-jobs` | Corresponding management pages | matching permission | Routed + management sidebar | Operations and audit views. |
| `/login`, `/unauthorized`, `*` | Login, Unauthorized, ErrorPage | n/a | Public/error | Authentication, denial, and fallback. |

### Sidebar status

Active primary/sidebar entries include Overview, Manual Topology, IP Scan, SNMP Devices, Device Monitoring, Packet Analysis, Linux Server Monitoring, Alert Management, Events, Syslog Management, Notifications, Monitoring Jobs, Role Management, User Management, Organizations, Sites, Vendors, Device Types, Device Credentials, Audit Logs, and Report Center. Several registered routes are intentionally commented out in `Sidebar.tsx` and are therefore routed-but-not-sidebar. No active Network Topology page route was found; topology backend/builder infrastructure remains.

## 3. Page-by-page functional inventory

| Page family | Visible/function inventory | APIs/data | Writes/background | Status/limitations |
|---|---|---|---|---|
| Dashboard | Summary metrics, gauges, traffic charts, radar/pies, alerts, topology/network summary, recent devices/activity; time range and refresh. | `getOverview`, dashboard/summary helpers; normalized device and collector data. | Refresh interval and navigation only. | Empty/no-data states are source-defined; runtime coverage varies. |
| ISP/IP Scan | Target input, module selection, chunked discovery, progress/results, add/store devices, topology/status summaries, SNMP modal. | local subnet, chunked scan/status/progress/stream, add/check-stored, monitoring controls, device/site/org APIs. | Starts discovery jobs; persists discovered devices; start/stop monitoring. | Module/device support is runtime dependent. |
| SNMP Monitoring | Service controls, device selector, refresh, overview counts, SNMP modules and polling state. | SNMP overview/latest metrics/config/service APIs. | Start/stop/restart polling/module jobs. | Data absent until collectors persist samples. |
| SNMP Devices | Search, pagination, refresh, device inventory, add/edit/delete, monitoring actions, device details. | list/options/device CRUD, SNMP optimized/detail/config/status APIs. | Device CRUD and module monitoring mutations. | Credential/device compatibility dependent. |
| SNMP Device Details | Identity, health, module navigation, system/CPU/memory/storage/interfaces/environment and capability summaries. | module-specific SNMP helpers. | Module start/stop/update where permitted. | Unsupported OIDs/modules are represented as unsupported/no data. |
| SNMP module pages | Module-specific tables/charts, refresh, filters where implemented, polling status. | `getSNMP*`, latest metrics and monitoring APIs. | Some pages start/stop/update monitoring. | Module availability and vendor OIDs vary. |
| Add SNMP Device | Device identity and v2c/v3 credentials/form validation. | device/credential APIs. | Creates device/credential and may enable monitoring. | Secrets not documented. |
| Manual Topology | Manual/actual/compare modes, device placement/edit/delete, links/ports, snapshots, reconciliation, health overlay, evidence and port map navigation. | manual snapshot/reconcile/resolve, topology/SNMP collection helpers, device APIs. | Save/update snapshots, resolve changes, device edits/removals. | Evidence confidence and stale/unknown states are source-dependent. |
| Device Port Map | Device ports/interfaces, status/filter/search, actions into topology. | device/interface/SNMP interface APIs. | Mostly navigation/updates where exposed. | Physical occupancy inference is not equivalent to confirmed cabling. |
| Device Monitoring | Device list/detail, status history, monitoring controls, metrics and refresh. | device, status history, monitoring config/latest metrics. | Start/stop/update monitoring. | Reachability and freshness drive displayed health. |
| Linux Server Monitoring | Server list, detect/onboard, SSH validation, current metrics, historical charts, retention state, start/stop monitoring, delete/edit. | `/linux-servers` API family. | Server/credential/config writes; background metric collection. | Requires reachable SSH/SNMP configuration; only implemented metrics should be documented. |
| Flow Analytics / Packet Analysis | Flow records/trends, top talkers/destinations/conversations and packet analysis views as implemented in page source. | flow analytics helpers and flow routes. | Ingestion is backend-driven; page is primarily read/analysis. | sFlow/IPFIX source quality and sampling affect results. |
| Alerts / Events / Notifications / Syslog | Lists, filters, acknowledgement/clear actions where present, syslog rules and retention. | alert/event/syslog APIs. | Acknowledge/resolve/clear; rule CRUD/enable/disable/cleanup. | Do not infer alert rules beyond source. |
| ITSM pages | Incident, problem, change, RCA, knowledge workflows, statuses, links/history/comments/feedback. | corresponding route families. | Create/update/status transitions/relationships. | Manual vs automated transitions must be distinguished. |
| Reports | Management report filters/options, daily redirect, availability report/export. | report management, daily, availability and CSV helpers. | Report definitions and export requests. | Coverage is data-dependent; N/A/stale semantics require runtime confirmation. |
| Administration | Users, roles/permissions, orgs, sites, vendors, device types, credentials, audit logs, branding/theme. | CRUD helpers and auth/branding APIs. | CRUD and assignments. | Authorization is enforced server-side and guarded client-side. |

Common page states: loading indicators, empty/no-data messages, request error displays, permission-denied views, and disabled/busy buttons exist selectively; each page must be verified against its component before final user-manual prose is written.

## 4. Shared component inventory

| Component | Responsibility/consumers |
|---|---|
| `Layout`, `ProtectedLayout`, `withPermission` | Authenticated shell, route guard, permission gating, error boundary behavior. |
| `Sidebar`, header/notification components | Navigation, service status, theme/language/cache controls, notifications. |
| `ThemeContext`, `ThemePicker`, `BrandingContext` | Theme mode/colors, font settings, branding allowed themes. |
| `GlassCard`, badges/status components | Shared surfaces, semantic status styling, clickable cards. |
| Table/pagination/query helpers | Repeated data-grid behavior and React Query refresh/cache. |
| SNMP shells/cards/discovery panels | Device/module layout, discovery inputs, collector data, MAC/FDB mapping. |
| Charts (`LineChart`, `AreaChart`, `BarChart`, `PieChart`, Recharts wrappers) | Dashboard, monitoring, reports, flow/APM pages. |
| Topology graph builder/canvas/port map | Manual topology, SNMP topology and device port views. |
| Dialog/toast/confirm helpers | CRUD confirmation, errors, destructive actions, feedback. |

## 5. Frontend API inventory by domain

`src/lib/api.ts` is a large typed request facade using `requestJson`, authenticated headers/token storage, error handling, and selected SSE helpers. The following is the authoritative functional grouping; exact helper signatures are in source.

| Domain | Helpers/endpoints represented | Read/write |
|---|---|---|
| Auth/branding | login, logout, getMe, getBranding | both |
| Dashboard/overview | getDashboardSummary, getOverview, service state/start/kill | both |
| Discovery | detectLocalSubnet, discoverSNMP, start/get/cancel/progress/stream chunked discovery, add/check stored, ping IPs | both/stream |
| Monitoring | start/stop device monitoring, start/stop/update/restart module jobs, monitoring status/history/stream | both/stream |
| Devices | list/options/get/create/update/delete/delete-all, credentials, interfaces, status history | both |
| SNMP | overview/system/CPU/memory/storage/interfaces/history/environment/LLDP/routing/VLAN/OID/tree/polling/topology/capabilities/latest metrics | read plus monitoring mutations |
| Topology | topology collection/snapshots, manual snapshot create/update/latest, reconcile, resolve changes | both |
| Alerts/events/syslog | list alerts/events/notifications, clear alerts, syslog records/rules CRUD/enable/disable/cleanup | both |
| ITSM | incidents, SLA, RCA; problems; changes; knowledge articles/versions/links/feedback | both |
| Reporting | management report/options/export, daily report, availability reports/export | read/create/export |
| Flow/APM/CMDB | flow records/trends, APM apps/services/overview/metrics/dependencies, CMDB types/items/relationships/history/sync | both |
| Admin | users/roles/permissions/orgs/sites/vendors/device types/credentials CRUD and assignments | both |
| Configuration | backups capture/compare; compliance policies/violations | both |
| Linux | list/detect/validate/create/update/delete, credentials, config, collect/start/status/history/retention/security | both |

Helpers with no consumer were not conclusively separated in this inventory because some feature-local modules call the backend directly and route-level lazy loading hides static usage. A dedicated call-graph pass is required before publishing an exact unused-helper list.

## 6. Backend route inventory

Backend routers are registered in `hardik/backend/main.py`: base NMS routes, discovery, SNMP device monitoring, manual topology, monitoring data, flows, APM, CMDB, RCA, incidents, problems, changes, knowledge, config backup/compliance, availability, virtualization, QoS, BGP, syslog, Linux monitoring, overview/service control, and legacy compatibility.

| Router/domain | Prefix/source | Endpoint families | Operations |
|---|---|---|---|
| Core auth/admin/devices | `/api/v1`, `backend/api/routes.py` | auth, health, branding, roles, permissions, users, orgs, sites, vendors, device types, devices, credentials, interfaces, reports | CRUD/read/actions/export |
| Discovery | `/api/v1`, `discovery_routes.py` | local subnet/modules, IP/ICMP/TCP/ARP/DNS/HTTP/SNMP/SSH/WMI/profile, summary/inventory, chunked scan, add/check devices, monitoring control/status/stream, device history, plan | actions/stream/read/write |
| SNMP | `/api/v1`, `snmp_device_routes.py` | device/module discovery, latest data, collector/polling/configuration, capabilities, OID/topology paths | read/write/action |
| Manual topology | `/api/v1`, `manual_topology_routes.py` | snapshots latest/create/update, reconcile, change resolve | write/read/action |
| Monitoring data | `/api/v1`, `monitoring_data_routes.py` | monitoring data ingest/read | write/read |
| Flow | `/api/v1/flows/analytics`, `flow_routes.py` | `/records`, `/trends` | read |
| APM | `/api/v1/apm`, `apm_routes.py` | applications/services/overview/service metrics/dependencies, metrics ingest, retention | read/write/action |
| CMDB | `/api/v1/cmdb`, `cmdb_routes.py` | types/items/relationships/history/sync | read/write/action |
| ITSM | `/api/v1/incidents`, `/problems`, `/changes`, `/knowledge`, corresponding files | lists/details, create/update, transitions, history/comments/links/feedback | read/write/actions |
| Syslog | `/api/v1/syslog`, `syslog_routes.py` | records/rules CRUD enable/disable/retention | read/write/action |
| Reports | `/api/v1`, `overview_routes.py`, `availability_routes.py`, `routes.py` | daily/management/availability/export | read/create/export |
| Linux | `/api/v1/linux-servers`, `linux_monitoring/api.py` | server CRUD/detect/SSH or SNMP validation, metrics, monitoring, retention/security | read/write/action |
| Operations | `/api/v1`, `overview_routes.py` | service overview, kill-all, polling start | read/action |
| Legacy | `legacy_routes.py` | backward-compatible endpoints | LEGACY; verify individually |

The audit found approximately 364 FastAPI decorator occurrences across inspected backend paths; this is a raw source count and includes routes that may be mounted under common prefixes, compatibility routes, and endpoints outside the primary user flows. A generated OpenAPI/runtime enumeration is required for an authoritative exact endpoint total.

## 7. Major database/model inventory

| Entity family | Source/model purpose | Main writers/readers |
|---|---|---|
| Users, roles, permissions, assignments, audit | Authentication/RBAC and audit trail | auth/admin routes, guards, audit page |
| Organizations/sites/vendors/device types | Inventory ownership/classification | admin/device/discovery pages |
| Devices, credentials, interfaces, status history | Managed inventory and health evidence | discovery, monitoring, SNMP, device pages |
| SNMP polling/config/latest/raw/cache/statistics | Collector output, job state, module capability/data | SNMP routes/services/pages |
| Discovery/chunked jobs/results | Scan state/progress and discovered devices | discovery routes/services/ISP page |
| Alerts/events/notifications/thresholds | Operational signals and user-facing alerts | monitoring/alert/event pages/services |
| Syslog/rules | Syslog records/correlation/retention | syslog routes/service |
| Flow records and sFlow counter samples | Flow/packet ingestion and analytics | flow routes/analytics |
| Incidents/SLA/history/comments/attachments | Incident lifecycle | incident routes/page |
| Problems/history/relationships | Problem lifecycle | problem routes/page |
| Changes/history/relationships | Change approval/implementation/rollback | change routes/page |
| Knowledge articles/versions/history/feedback/links | Knowledge lifecycle and cross-references | knowledge routes/page |
| CMDB CI types/items/relationships/history | Configuration item graph | CMDB routes/page |
| Config backups/compliance policies/violations | Backup comparison/compliance | corresponding routes/pages |
| Manual topology snapshots/changes | Manual/actual comparison and reconciliation | topology routes/page |
| Linux servers/credentials/config/metrics/security events | Server monitoring/history | Linux API/service/page |
| APM metrics/applications/services/dependencies | Application telemetry | APM routes/page |
| BGP observations, QoS samples, virtualization objects | Specialized monitoring domains | respective routes/pages |

Exact table names and fields are in `hardik/backend/models/`; retention/cleanup is implemented only for domains whose service/routes expose retention functions (for example syslog, Linux history, APM). A model existence is not proof of active production writes.

## 8. Device lifecycle and discovery

Source-trace lifecycle: discovery UI (`ISPMonitoring`, SNMP discovery panels) → discovery router/services/modules → duplicate/storage checks → device/credential creation → ICMP and/or SNMP monitoring start → scheduler/collector → latest/history persistence → health derivation (`backend/services/device_health.py`) → alerts/events/pages/reports.

Discovery modules present: IP, ICMP, TCP, ARP, DNS, HTTP, SNMP, SSH, WMI, device profiler, plus chunked discovery orchestration. Inputs are validated in frontend and backend; chunked scans expose job IDs, progress, cancellation and SSE/progress polling. `addDiscoveredDevices` performs the persistence path and `checkStoredDevices` supports duplicate handling. Exact duplicate rules and device identity precedence require runtime/data verification.

## 9. ICMP monitoring

ICMP code is present in discovery, ping engine, availability/realtime services and monitoring routes. Source tracks reachability/status/history fields in device/status models and exposes monitoring controls/history/stream. The source distinguishes concepts such as last seen/status history and monitoring attempts in different paths, but field population and effective cadence must be verified against runtime responses. Online/offline/degraded/stale/unknown display is centralized through device health logic plus page-specific normalization. Alert generation and recovery are implemented only where an alert service/rule consumes the evidence; no universal alert rule should be assumed.

## 10. SNMP workflow and module matrix

SNMP v2c and v3 credential/security code is present (`backend/snmp/client.py`, `credentials.py`, `security.py`) and exposed by add/configuration UI. Polling is scheduled by SNMP polling/scheduler services and persists collector/module results, errors, latest values and statistics.

| Module | Collector/source | UI/API evidence | Status |
|---|---|---|---|
| System | `collectors/system.py` | overview/system pages/helpers | Implemented source; device/OID dependent |
| CPU | `collectors/cpu.py` | CPU page/latest CPU | Implemented source; device/OID dependent |
| Memory | `collectors/memory.py` | memory page/latest memory | Implemented source; device/OID dependent |
| Storage | `collectors/storage.py` | storage page/latest storage | Implemented source; device/OID dependent |
| Interfaces | `collectors/interfaces.py` | interfaces/details/latest interfaces | Implemented source; device/OID dependent |
| Environment | `collectors/environment.py` | environment page/latest environment | Implemented source; sensor/OID dependent |
| VLAN | `collectors/vlan.py` | VLAN page/API | Implemented source; device/OID dependent |
| LLDP | `collectors/lldp.py` | LLDP page/topology | Implemented source; neighbor/OID dependent |
| CDP | `collectors/cdp.py` | topology/collector infrastructure | Source present; UI/API coverage needs runtime verification |
| Routing | `collectors/routing.py` | routing page/API | Implemented source; OID dependent |
| ARP | `collectors/arp.py` | topology/MAC correlation | Implemented source; data dependent |
| MAC/FDB | `collectors/mac_table.py` | collector/MAC port summary/topology | Implemented source; mapping may be unresolved |
| Firewall | `collectors/firewall.py` | backend/source presence; page coverage requires verification | Partial/source-dependent |
| Wireless | `collectors/wireless.py` | backend/source presence; page coverage requires verification | Partial/source-dependent |
| Inventory | `collectors/inventory.py` | inventory/device views | Implemented source; vendor/OID dependent |
| Health | `collectors/health.py` | health indicators | Implemented source; evidence dependent |
| Topology | `collectors/topology.py`, topology builder | topology pages/APIs | Implemented/partial; evidence quality dependent |
| OID Explorer | OID catalog/cache/tree | OID Explorer page/API | Implemented source |
| Polling | poll scheduler/statistics/raw cache | polling page/API | Implemented source; scheduler/runtime dependent |

Unsupported OID/module, timeout, authentication failure, empty response and partial collector results must be documented as distinct states; source does not justify claiming every vendor supports every module.

## 11. Manual topology

`ManualTopology.tsx`, `topologyGraphBuilder.ts`, SNMP topology helpers, `manual_topology_routes.py`, and topology tests/reports establish manual, actual/evidence and compare/reconciliation concepts. Source includes persisted snapshots, save/load, device placement, manual and managed devices, links/port connections, editing/deletion actions, health/status overlays, LLDP/CDP and FDB/ARP correlation, physical occupancy/inference handling, change resolution, and device-port-map navigation. Exact confidence/occupancy semantics are source-defined and should be explained with examples only after runtime verification. The removed Network Topology page is not an active route; shared builders/backend remain infrastructure.

## 12. Linux server monitoring

`backend/linux_monitoring/` contains server schemas, SSH/security helpers, detection, metrics, service, scheduler and API. Source-defined data includes CPU, memory, disk/storage, network/interfaces and historical metric records; process/service/security fields must be listed only where present in the corresponding schemas/metrics. UI supports server selection, detection/onboarding, validation, current/history views, monitoring controls and retention status. SSH connectivity, credentials, privilege and platform support are configuration/device dependent. SNMP validation is represented in schemas; it is not proof that all metrics use SNMP.

## 13. Packet and flow analysis

Flow models include `FlowRecord` and `SFlowCounterSample`; flow routes expose records/trends and frontend includes flow analytics/packet analysis pages. Source references IPFIX/sFlow paths and sampling/analytics concepts. sFlow v5 and IPFIX v10 must be documented separately after verifying listener/parser configuration. Active NetFlow support was not established by the inspected source and must not be claimed. Receiver ports, device export configuration, persistence and source-quality semantics require deployment/runtime verification.

## 14. Health authority

`backend/services/device_health.py` is the health authority candidate and should be traced as the canonical `derive_device_health()` source. The supported semantic states are online, offline, degraded, stale and unknown, with evidence from ICMP, SNMP, freshness, unsupported/disabled states and last-known data. Pages normalize/display these states in badges, cards, topology nodes and device tables. Final manual must quote the actual precedence/threshold logic from that function and distinguish it from page-local fallback labels.

## 15. Alert/event pipeline

Source contains alerting/event services, discovery analytics endpoints, alert/event/notification pages, threshold/rule routes, acknowledgement/resolve paths in incident/alert domains, and persistence models. The verified pipeline shape is condition/evaluation → persistence → UI/action; automatic vs manual transitions differ by domain. Inventory exact alert rules from `alert_engine.py`, `services/alerting.py`, thresholds and route code before documenting rule thresholds. Do not infer alerts from status colors alone.

## 16. ITSM modules

Incident, problem, change and knowledge route/page/model families are implemented in source. Incidents include history, SLA policies, acknowledgement/resolve/reopen, RCA, comments and attachments. Problems include lifecycle/history and incident relationships. Changes include submit/approve/reject/schedule/start/complete/fail/rollback/close and links. Knowledge includes draft/review/publish/retire/restore, versions, history, feedback and links to incidents/problems/changes/CIs/devices/services. Automation must be separated from manual UI-triggered actions; source presence does not establish external ticketing integration.

## 17. Reporting

Active reporting authority is `ReportManagement` at `/reports/management`; `/reports/daily` redirects there with `preset=daily`. Availability reporting has its own route/API/export. Source includes period/filter/options, management sections, CSV/export helpers and daily report data. Final manual must describe only columns/sections returned by current code and mark missing data as N/A/empty/stale according to component logic. A separate “Unified Report Center” should be treated as the active Report Management implementation unless runtime branding says otherwise.

## 18. Authentication/RBAC/security

Login obtains a JWT through `/auth/login`; authenticated requests add the token, `getMe` restores identity, logout clears client state. `ProtectedLayout`/`withPermission` guard routes, while FastAPI dependencies enforce backend permissions. Roles, permissions, users and assignments have CRUD APIs. Credential values must remain secret; storage/encryption behavior is configuration/source dependent and must be described from credential/security modules without reproducing values.

Implemented/configuration-dependent controls include JWT auth, route/backend permission checks, request validation, protected APIs, environment-based configuration and protocol security options for SNMP/SSH. “Compliant”, “encrypted at rest”, or “secure by default” claims require deployment evidence and are not made here.

## 19. Scheduler, Redis and realtime

APScheduler/poll scheduler/background services register monitoring work; HA scheduler/Redis code provides lease/ownership coordination. SNMP and Linux schedulers restore/register jobs through service code; exact restart behavior and job inventory require runtime log/config verification. Frontend intervals, React Query refresh, manual Refresh buttons, backend scheduler persistence and SSE streams coexist. No WebSocket claim is made. Redis outage behavior, lease TTLs and rescheduling failure handling require runtime verification from deployed configuration/logs.

## 20. Administration and configuration

Admin pages cover users, roles/permissions, organizations, sites, vendors, device types, device credentials, audit logs, branding/theme and report center. Device/SNMP pages cover device onboarding, credentials and monitoring configuration. Environment/configuration sources include backend settings, requirements, frontend environment/API base configuration, shell startup scripts, PostgreSQL/Redis settings and ports. Actual secrets and host values are excluded.

## 21. Installation/deployment inventory

| Item | Evidence | Audit status |
|---|---|---|
| Python dependencies | `hardik/backend/requirements.txt` | Source found; install/runtime not verified |
| Node/npm | `figma design/package.json` | Source found; build verified during code work, deployment not verified |
| Frontend build | Vite scripts/package | Source found |
| Backend startup | `backend/main.py`, `start_*.sh`, service scripts | Source found; exact production command requires host verification |
| PostgreSQL | backend DB/settings/config | Configuration-dependent |
| Redis | cache/HA scheduler/settings | Configuration-dependent |
| Migrations/init | backend init/migration files | Inventory requires deployment check for applied revision |
| Ports/firewall/systemd | shell/config/host | Needs host/runtime verification |

Use placeholders such as `<DATABASE_URL>`, `<REDIS_URL>`, `<JWT_SECRET>`, `<SNMP_SECRET>` in final manuals.

## 22. Operational workflow

Fresh install → configure database/Redis/environment → start backend/frontend → login → create organization/site/credentials as needed → discover IP/subnet → validate ICMP/SNMP/SSH → add device → enable monitoring and configure modules/intervals → observe health/latest/history → inspect modules/interfaces/MAC/ARP/LLDP → build/reconcile topology → configure/observe alerts/events/syslog → monitor servers/flows → handle incidents/problems/changes → produce reports → maintain retention/backups/compliance. Optional steps are site/org setup, SSH, flows, topology reconciliation, ITSM and compliance; device/protocol support is configuration dependent.

## 23. Troubleshooting inventory from source

| Area | Evidence/messages/classes | Status |
|---|---|---|
| Frontend API/auth | request errors, token expiry/logout, permission/Unauthorized/ErrorPage | Implemented messages; exact operator fixes need deployment guide |
| Database | backend exceptions/health and query services | Source present; runtime symptoms need logs |
| Redis/scheduler | lease/cache/service-state paths | Source present; outage behavior needs runtime verification |
| ICMP | discovery/monitor failures, offline/stale evidence | Implemented paths |
| SNMP | timeout/auth/unsupported/no data/error fields | Implemented paths; vendor behavior dependent |
| SSH/Linux | validation/detection/metric errors | Implemented paths; credentials/network dependent |
| sFlow/IPFIX | parser/receiver/source-quality fields | Partial; listener deployment verification required |
| Reports | empty/no stored data/N/A | Implemented UI semantics; coverage data dependent |
| Topology | stale/unknown/insufficient evidence/unresolved MAC-IP | Implemented evidence states; confidence requires runtime data |

## 24. Implementation-status matrix

| Feature | Classification |
|---|---|
| Auth/RBAC | IMPLEMENTED; configuration/security deployment dependent |
| Core dashboard/device inventory | IMPLEMENTED; data freshness dependent |
| IP/ICMP discovery | IMPLEMENTED; network dependent |
| SNMP v2c/v3 | IMPLEMENTED source; vendor/OID/configuration dependent |
| SNMP modules | PARTIAL across vendors; source collectors exist, support varies |
| Linux/SSH monitoring | IMPLEMENTED/PARTIAL; SSH/platform dependent |
| Manual topology | IMPLEMENTED/PARTIAL; evidence quality and runtime data dependent |
| Flow analytics | PARTIAL; ingestion/listener/source coverage requires runtime verification |
| sFlow | SOURCE FOUND; runtime receiver verification required |
| IPFIX | SOURCE FOUND/partial; runtime receiver verification required |
| Active NetFlow | NOT ESTABLISHED by source audit |
| Alerts/events/syslog | IMPLEMENTED/PARTIAL by domain; rule coverage requires audit/runtime |
| ITSM modules | IMPLEMENTED source; external automation/integration not assumed |
| Reports | IMPLEMENTED source; coverage/export verification required |
| Redis lease/HA scheduler | SOURCE FOUND; deployment/runtime verification required |
| Network Topology page | NOT ACTIVE/removed; shared infrastructure remains |

## 25. Required runtime verification before final manuals

- Enumerate deployed OpenAPI routes and compare with source decorators.
- Verify database engine, applied migrations, table names, retention jobs and row writers.
- Verify Redis URL/lease ownership, scheduler restart/restore and job duplication behavior.
- Exercise every frontend route with representative permissions and empty/error/loading states.
- Validate SNMP v2c/v3 against supported device vendors/OIDs, including failures and unsupported modules.
- Confirm ICMP cadence and exact `last_seen`, attempt/status and health precedence.
- Confirm sFlow/IPFIX listener ports, parser versions, sampling and persistence; do not enable NetFlow claims without evidence.
- Verify SSH metrics, credentials, server retention and alert behavior.
- Verify alert rule thresholds, recovery/acknowledgement semantics and incident automation.
- Verify CSV/Excel/report data coverage and N/A/stale semantics.
- Confirm production startup/systemd/firewall/ports and security headers.

## 26. Proposed final documentation set

1. `01_NMS_Product_Overview.md`
2. `02_NMS_System_Architecture.md`
3. `03_NMS_Installation_and_Deployment.md`
4. `04_NMS_Getting_Started.md`
5. `05_NMS_Administrator_Guide.md`
6. `06_NMS_Operator_User_Manual.md`
7. `07_NMS_Page_by_Page_Reference.md`
8. `08_NMS_Device_Onboarding_Guide.md`
9. `09_NMS_SNMP_Monitoring_Guide.md`
10. `10_NMS_ICMP_Monitoring_Guide.md`
11. `11_NMS_Server_Monitoring_Guide.md`
12. `12_NMS_Topology_Guide.md`
13. `13_NMS_sFlow_IPFIX_Guide.md`
14. `14_NMS_Alerts_Events_Incident_Guide.md`
15. `15_NMS_Reporting_Guide.md`
16. `16_NMS_Security_and_RBAC_Guide.md`
17. `17_NMS_Operations_and_Maintenance.md`
18. `18_NMS_Troubleshooting_Guide.md`
19. `19_NMS_API_and_Data_Flow_Reference.md`
20. `20_NMS_Appendices_Glossary.md`

## Audit totals and completion status

- TOTAL FRONTEND ROUTES: **66 declared route entries** across `routes.tsx` and `snmp/routes.tsx`, including aliases, parameterized SNMP/detail routes, redirects and public/error routes; this is a declaration count, not a deduplicated URL count.
- TOTAL ACTIVE SIDEBAR PAGES: **approximately 22 active entries** in `Sidebar.tsx`; permissions can hide entries at runtime.
- TOTAL DETAIL/CHILD ROUTES: **at least 25** (SNMP module/device/interface, device-monitoring detail, port map, capabilities/dashboard details).
- TOTAL FRONTEND API HELPERS: **large typed facade in `src/lib/api.ts` (exact count requires AST extraction)**.
- TOTAL BACKEND ENDPOINTS: **approximately 364 raw decorator occurrences inspected; exact mounted OpenAPI count requires runtime enumeration**.
- TOTAL MAJOR DB MODELS: **multiple model families listed above; exact class/table count requires AST extraction**.
- TOTAL MONITORING MODULES: **at least 17 SNMP/monitoring domains** including System, CPU, Memory, Storage, Interfaces, Environment, VLAN, LLDP, CDP, Routing, ARP, MAC/FDB, Firewall, Wireless, Inventory, Health, Topology, OID and Polling.

- PAGES FULLY INVENTORIED: **route families and primary feature domains inventoried from source**.
- PAGES REQUIRING MORE AUDIT: **all pages require action-level source extraction before final manuals; especially generic SNMP modules, Packet Analysis, Flow Analytics, Linux security, legacy routes, and admin detail dialogs**.

- SNMP MODULES FOUND: **System, CPU, Memory, Storage, Interfaces, Environment, VLAN, LLDP, CDP, Routing, ARP, MAC Table, Firewall, Wireless, Inventory, Health, Topology, OID Explorer, Polling**.
- ICMP IMPLEMENTATION FOUND: **YES**.
- SSH SERVER MONITORING FOUND: **YES**.
- SFLOW FOUND: **YES/source models and flow paths; runtime receiver verification required**.
- IPFIX FOUND: **source/flow path indicated; runtime verification required**.
- ACTIVE NETFLOW FOUND: **NO evidence established by this audit**.

- AUTH/RBAC FOUND: **YES**.
- SCHEDULER FOUND: **YES**.
- REDIS LEASE FOUND: **YES/source; runtime verification required**.
- REPORTING FOUND: **YES**.
- MANUAL TOPOLOGY FOUND: **YES**.

- SECRETS INCLUDED IN DOCUMENT: **NO**.
- APPLICATION CODE CHANGED: **NO**.
- DOCUMENTATION ONLY: **YES**.
