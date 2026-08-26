# Frontend Static Data Audit

Date: 2026-08-25

Scope: frontend pages only

Safety: No application code was modified during this audit.

## 1. Meaning of Static Data

This report uses four categories:

- **Static UI**: labels, icons, colors, dropdown options, module names, and
  design text. This is expected and is not monitoring data.
- **Hardcoded business/demo data**: values that look like real monitoring or
  security data but are written directly in the frontend source.
- **Browser-persisted data**: values stored in `localStorage` or
  `sessionStorage`. This is not hardcoded, but it can become old until the
  application refreshes or replaces it.
- **Dynamic data**: values loaded from backend APIs, React Query, database
  responses, or live/discovery requests.

## 2. Executive Summary

The main pages with hardcoded business-looking data are:

1. Attack Path
2. Compliance

The pages with browser-persisted data are:

1. Manual Topology
2. Network Topology
3. Shared alert panel in the application layout

The SNMP pages mostly use dynamic APIs. Their module lists, labels, icons,
empty states, and formatting rules are static UI configuration, but device
values and capability states come from the backend.

## 3. Page-by-Page Findings

### 3.1 Attack Path

File:

`figma design/src/pages/AttackPath.tsx`

#### Hardcoded business/demo data

The following data is declared directly in the page:

- MITRE ATT&CK tactic list.
- Technique IDs and names.
- Several technique states such as `detected: true` or `detected: false`.
- Static times such as `23:41`, `23:42`, `23:55`, and `00:02`.
- Static attack-flow endpoints:
  - `External IP`
  - `Internal Host`
  - `Web API :443`
  - `SRV-DB-01`
- Static incident label `INC-2847`.

#### Dynamic data

- Alerts are loaded through `listAlerts()`.
- The visible attack flow is generated from the first five alert records.
- Alert title, created time, and resolved state are dynamic.

#### Conclusion

The attack-flow list changes with real alerts, but the MITRE matrix detection
states and some displayed context are partly demo/static. The page should not
be considered a fully real-time attack-path engine.

### 3.2 Compliance

File:

`figma design/src/pages/Compliance.tsx`

#### Hardcoded business-looking configuration

- Framework names and control totals:
  - ISO 27001: 114
  - NIST CSF: 108
  - PCI DSS: 264
  - SOC 2 II: 64
- Base framework scores:
  - 87
  - 79
  - 92
  - 84
- Control domain names:
  - Access Control
  - Cryptography
  - Network Security
  - Incident Response
  - Asset Management
  - Vulnerability Management

#### Dynamic data

- `/overview?hours=24` supplies alerts and devices.
- `/events` supplies event data.
- Overall compliance score is calculated from online devices and unresolved
  alerts.
- Framework scores are adjusted using the number of open alerts.
- Vulnerability-looking entries are created from real alert records, but their
  CVE IDs and CVSS values are generated in the frontend.

#### Conclusion

The page is a mixture of live alert/device/event data and hardcoded compliance
framework assumptions. It is not currently backed by a compliance control
database or vulnerability scanner.

### 3.3 Manual Topology

File:

`figma design/src/pages/ManualTopology.tsx`

#### Browser-persisted data

- Manual workspace/layout is stored in `localStorage`.
- Offline popup tracking is stored in `sessionStorage`.
- One-time offline alert IP tracking is stored in `sessionStorage`.

#### Dynamic data

- Latest manual topology snapshot is loaded from the backend.
- SNMP device list is loaded from the backend.
- Interface data is loaded from live or latest-interface APIs depending on
  availability.
- Device health checks are sent periodically.

#### Risk

Node/card positions and user-created layout can remain old in the browser.
This is not the same as old SNMP metrics, but it can make an old device card
appear until the workspace is refreshed or replaced.

### 3.4 Network Topology

File:

`figma design/src/pages/Topology.tsx`

#### Browser-persisted data

- Node layout is saved in `sessionStorage`.

#### Dynamic data

- `/snmp/topology` provides topology information.
- `/devices` provides inventory information.
- `/monitoring/data` provides stored monitoring data.
- Device detail APIs provide selected-node details.
- Forced topology refresh can request a fresh topology collection.

#### Risk

Node positions are cached locally, while device/link information is API-driven.
An old position can remain even when the device data is refreshed.

### 3.5 Shared Layout and Notifications

File:

`figma design/src/components/Layout.tsx`

#### Browser-persisted data

- Alerts are cached in `sessionStorage` under the layout alert cache key.
- Hidden/dismissed alert IDs are cached in `sessionStorage`.

#### Dynamic data

- Alerts are loaded from the alerts API.
- Alerts refresh approximately every 60 seconds while the tab is visible.
- Page views are sent to the backend with a 30-second per-route throttle.

#### Risk

The alert panel can show cached alerts briefly during startup or API failure.
The current session cache is not permanent database truth.

## 4. SNMP Pages

SNMP pages use dynamic device and monitoring APIs. The following items are
static UI configuration only:

- Module names.
- Module order.
- Icons.
- Descriptions.
- Table column definitions.
- Color and status mappings.
- Empty-state text.
- Formatting rules for bytes, uptime, speed, and percentages.

Main configuration file:

`figma design/src/features/snmp/modules/snmpModuleRegistry.ts`

### Dynamic SNMP values

These values come from backend responses:

- Device list.
- SNMP version/status.
- Identity and hostname.
- Capability flags.
- CPU values.
- Memory values.
- Storage volumes.
- Interface rows and counters.
- Environment sensors.
- VLAN rows.
- LLDP neighbors.
- Routing entries.
- OID support details.
- Polling history and duration.
- Monitoring job state.

Important pages:

- `SNMPDevices.tsx`: `/snmp/devices` API.
- `SNMPDeviceDetails.tsx`: device detail/overview APIs.
- `SNMPCapabilities.tsx`: capability API.
- `SNMPCPUMonitoring.tsx`: CPU API/latest/history.
- `SNMPMemoryMonitoring.tsx`: memory API/latest/history.
- `SNMPStorageMonitoring.tsx`: storage API/latest/history.
- `SNMPInterfaceMonitoring.tsx`: interface API/latest/history.
- `SNMPEnvironmentMonitoring.tsx`: environment API/latest/history.
- `SNMPVLANMonitoring.tsx`: VLAN API.
- `SNMPLLDPMonitoring.tsx`: LLDP API.
- `SNMPRoutingMonitoring.tsx`: routing API.
- `SNMPOIDExplorer.tsx`: OID API.
- `SNMPPollingMonitoring.tsx`: polling history/statistics API.

## 5. Static UI Only Pages

These pages do not contain device-monitoring data as their main purpose:

- `Login.tsx`: login form and labels.
- `Unauthorized.tsx`: access-denied message.
- `ErrorPage.tsx`: route error UI.
- `AddSNMPDevice.tsx`: form defaults and protocol dropdown options.

Static values in these pages are expected:

- SNMP v3 security-level options.
- Authentication protocol options.
- Privacy protocol options.
- Form placeholders.
- Button labels and icons.

## 6. Dynamic CRUD Pages

The following pages read their main records from backend CRUD APIs. They do
not use hardcoded monitoring records:

- Dashboard
- ISP Monitoring
- Incidents
- Alerts Management
- Events
- Notifications
- Audit Logs
- Server Monitoring
- Device Monitoring
- Device Monitoring Detail
- Interfaces List
- Device Credentials
- Device Types
- Monitoring Jobs
- Organizations
- Sites
- Vendors
- Roles
- Users
- Reports

Their static content is limited mainly to labels, filters, colors, table
headers, empty messages, and form defaults.

## 7. Static or Disabled Source Pages

Some source files exist but are currently commented out or not active in the
route table:

- `Firewall.tsx`
- `Forensics.tsx`
- `Compliance.tsx` may exist even if its route is disabled in the active router.
- `NginxMonitoring.tsx`
- `Thresholds.tsx`
- `Reports.tsx` depending on the active route configuration.

The source file may contain API calls, but that page is not necessarily
reachable from the current navigation. The active source of truth for route
availability is:

- `figma design/src/routes.tsx`
- `figma design/src/features/snmp/routes.tsx`

## 8. Quick Classification Table

| Page/area | Static UI | Hardcoded business data | Browser cache | API/database data |
|---|---:|---:|---:|---:|
| Attack Path | Yes | Yes | No | Alerts only |
| Compliance | Yes | Yes | No | Overview/events/alerts/devices |
| Manual Topology | Yes | Limited defaults | Yes | Yes |
| Network Topology | Yes | No meaningful device data | Yes for layout | Yes |
| SNMP Devices | Yes | No device rows | React Query/API cache | Yes |
| SNMP Capabilities | Yes | Module categories only | React Query | Yes |
| SNMP module pages | Yes | No meaningful metric data | React Query | Yes |
| Dashboard | Yes | No main metric records | API/Redis/React state | Yes |
| CRUD pages | Yes | No main records | Local React state | Yes |
| Login/Error/Unauthorized | Yes | No | No | Auth only for login |

## 9. What Counts as Old Data

There are four possible old-data locations:

1. **React Query memory**: page-level query cache.
2. **Frontend GET cache**: shared `requestJson()` cache.
3. **Redis**: selected dashboard/overview/device summary responses.
4. **PostgreSQL latest tables**: newest successful background poll, which may
   itself be old if monitoring is stopped or polling failed.

Local/session storage mostly stores topology layout and alert dismissal state;
it is not normally the source of CPU, memory, VLAN, LLDP, or routing metrics.

## 10. Final Findings

### Real hardcoded/mock risk

- Attack Path technique detection matrix.
- Attack Path incident/context labels.
- Compliance framework totals.
- Compliance base framework scores.
- Compliance generated CVE IDs and CVSS values.

### Browser-stored risk

- Manual topology workspace/layout.
- Manual topology offline-popup state.
- Network topology node layout.
- Shared alert panel startup cache.

### Not static monitoring data

- SNMP device rows.
- SNMP capability status.
- SNMP metrics.
- Polling history.
- Device health.
- Dashboard totals.
- Interface, VLAN, LLDP, routing, ARP, and MAC-table data.

## 11. Scope Boundary

This audit only identifies where data comes from. It does not:

- Replace hardcoded values.
- Remove local/session storage.
- Change refresh intervals.
- Change API calls.
- Change backend behavior.
- Change database schema.
- Modify SNMP collection.

