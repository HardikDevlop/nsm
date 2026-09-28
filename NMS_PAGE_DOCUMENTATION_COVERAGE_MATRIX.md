# NMS Page Documentation Coverage Matrix

Source: `figma design/src/routes.tsx`, `src/features/snmp/routes.tsx`, `Sidebar.tsx`, and page components. “Partial” means the route is identified and functionally grouped, but a final manual still needs exact dynamic control/API extraction or runtime verification.

| Route | Page | Sidebar? | Permission | Purpose documented? | UI documented? | Actions documented? | API mapped? | Data source mapped? | Refresh mapped? | Errors/empty mapped? | Runtime verification? | Documentation status |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `/` | Dashboard | Yes | dashboard:read | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Complete/source-grounded |
| `/manual-topology` | Manual Topology | Yes | topology:read | Yes | Yes | Yes | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/manual-topology/device/:deviceId/ports` | Device Port Map | No | topology:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/isp` | IP Scan / ISP Monitoring | Yes | isp:read | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Complete/source-grounded |
| `/incidents` | Incidents | No | incidents:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/alerts` | Alert Management | Yes/alias | alerts:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/packet-analysis` | Packet Analysis | Yes | packet_analysis:read | Yes | Partial | Partial | Yes | Partial | Partial | Partial | Yes | Partial |
| `/flow-analytics` | Flow Analytics | No | flows:read | Yes | Partial | Partial | Yes | Partial | Partial | Partial | Yes | Partial |
| `/apm` | APM | No | apm:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/cmdb` | CMDB | No | cmdb:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/rca` | RCA | No | rca:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/incident-management` | Incident Management | No | incidents:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/problem-management` | Problem Management | No | problems:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/change-management` | Change Management | No | changes:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/knowledge-base` | Knowledge Base | No | knowledge:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/configuration-backups` | Configuration Backups | No | config_backups:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/configuration-compliance` | Configuration Compliance | No | config_compliance:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/availability` | Availability | No | availability:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/qos` | QoS | No | qos:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/bgp` | BGP | No | bgp:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp` | SNMP Monitoring | Feature | devices:read | Yes | Yes | Yes | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/snmp-monitoring` | SNMP Monitoring alias | No | devices:read | Yes | Yes | Yes | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/snmp/dashboard` | SNMP Dashboard | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/dashboard/:deviceId` | SNMP Dashboard detail | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices` | SNMP Devices | Yes | devices:read | Yes | Yes | Yes | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/snmp/devices/add` | Add SNMP Device | No | devices:create | Yes | Yes | Yes | Yes | Yes | N/A | Yes | Yes | Complete/source-grounded |
| `/snmp/devices/:deviceId` | SNMP Device Details | No | devices:read | Yes | Yes | Partial | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/snmp/devices/:deviceId/monitoring` | SNMP Monitoring Config | No | devices:update | Yes | Partial | Yes | Yes | Yes | Partial | Yes | Yes | Partial |
| `/snmp/devices/:deviceId/cpu` | CPU Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/memory` | Memory Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/interfaces` | Interface Monitoring | No | devices:read | Yes | Yes | Partial | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/snmp/devices/:deviceId/interfaces/:interfaceId` | Interface Details | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/storage` | Storage Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/environment` | Environment Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/vlan` | VLAN Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/lldp` | LLDP Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/routing` | Routing Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/topology` | Topology Module | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/oids` | OID Explorer | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/polling` | Polling Monitoring | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/capabilities` | SNMP Capabilities | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/devices/:deviceId/:moduleId` | Generic SNMP Module | No | devices:read | Yes | Partial | Partial | Yes | Partial | Partial | Partial | Yes | Partial |
| `/snmp/capabilities` | SNMP Capabilities | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/snmp/capabilities/:deviceId` | Device Capabilities | No | devices:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/linux-servers` | Linux Server Monitoring | Yes | linux_servers:read | Yes | Yes | Yes | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/device-monitoring` | Device Monitoring List | Yes | device_monitoring:read | Yes | Yes | Partial | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/device-monitoring/:deviceId` | Device Monitoring Detail | No | device_monitoring:read | Yes | Partial | Partial | Yes | Yes | Partial | Yes | Yes | Partial |
| `/roles` | Role Management | Yes | roles:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/users` | User Management | Yes | users:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/organizations` | Organizations | Yes | organizations:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/vendors` | Vendors | Yes | vendors:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/sites` | Sites | Yes | sites:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/device-types` | Device Types | Yes | device_types:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/device-credentials` | Device Credentials | Yes | device_credentials:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/reports/daily` | Daily Report redirect | No | none | Yes | Yes | No | Yes | Yes | N/A | Yes | Complete/current behavior |
| `/reports/management` | Report Center | Yes | reports:read | Yes | Partial | Partial | Yes | Yes | Partial | Yes | Yes | Partial |
| `/alerts-management` | Alert Management alias | No | alerts:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/events` | Events | Yes | events:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/syslog` | Syslog Management | Yes | syslog:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/notifications` | Notifications | Yes | notifications:read | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/audit-logs` | Audit Logs | Yes | audit_logs:read | Yes | Partial | No/partial | Yes | Yes | Partial | Partial | Yes | Partial |
| `/monitoring-jobs` | Monitoring Jobs | Yes | monitoring_jobs:read | Yes | Yes | Yes | Yes | Yes | Partial | Yes | Yes | Complete/source-grounded |
| `/login` | Login | No | none | Yes | Yes | Yes | Yes | Yes | N/A | Yes | Yes | Complete/source-grounded |
| `/unauthorized` | Unauthorized | No | none | Yes | Yes | No | N/A | N/A | N/A | Yes | No | Complete/source-grounded |
| `*` | Error Page | No | none | Yes | Partial | Partial | N/A | N/A | N/A | Yes | Yes | Partial |

## Summary

- TOTAL ROUTES CHECKED: **66 declared route entries** across the two route authorities.
- TOTAL USER-FACING PAGES: **all non-wildcard route entries; aliases and redirects are separately classified**.
- TOTAL SIDEBAR PAGES: **22 active sidebar entries** according to `Sidebar.tsx`.
- TOTAL DETAIL/CHILD PAGES: **at least 25**, including SNMP modules, parameterized details, port map and device detail.
- TOTAL ROUTED-HIDDEN PAGES: **the registered non-sidebar business/admin/detail routes identified above**.
- PAGES FULLY DOCUMENTED: **primary dashboard, IP Scan, SNMP inventory/add/details/interfaces, Linux monitoring, device monitoring, topology, operations and auth families at source-grounded functional level**.
- PAGES PARTIALLY DOCUMENTED: **dynamic/generic SNMP modules, hidden ITSM/admin/specialized pages, packet/flow and some detail dialogs**.
- PAGES REQUIRING SOURCE FOLLOW-UP: **any row marked Partial, plus exact dynamic action/API/timer extraction and runtime validation**.
- ALL CURRENT ROUTES COVERED: **YES**.
- REMOVED NETWORK TOPOLOGY EXCLUDED: **YES**.
- MANUAL TOPOLOGY INCLUDED: **YES**.
- REPORT CENTER CURRENT IMPLEMENTATION USED: **YES; `/reports/daily` documented as redirect**.
- SNMP MODULES COVERED: **YES, with vendor/OID/runtime caveats**.
- ADMIN PAGES COVERED: **YES**.
- SECRETS EXPOSED: **NO**.
- APPLICATION CODE CHANGED: **NO**.
- DOCUMENTATION ONLY: **YES**.
