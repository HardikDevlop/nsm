# Frontend → Backend Mapping

| Frontend route/component | UI permission | API client/features | Backend source/service | Status |
|---|---|---|---|---|
| `/` → `Dashboard` | `dashboard:read` | `getOverview`, devices/alerts/metrics | `overview_routes.py`, core services | S/U |
| `/devices`, `/device-monitoring/*` | device monitoring read | `lib/api.ts` device/metric calls | `api/routes.py`, monitoring services | S/U |
| `/windows-devices/*` | `device_monitoring:read` | Windows snapshots/diagnostics/process/CA calls | `windows_monitoring/api.py`, `cim.py`, helper APIs | S/U |
| `/linux-servers` | `linux_servers:read` | Linux CRUD/metrics/security calls | `linux_monitoring/api.py`, service/scheduler | S/U |
| `/snmp-*`, `/snmp/*` | devices read/create/update | SNMP React Query hooks | `snmp_device_routes.py`, `backend/snmp/*` | S/U |
| `/manual-topology*` | `topology:read` | topology snapshots/ports | `manual_topology_routes.py`, topology services | S/U |
| `/alerts`, `/alerts-management`, `/incidents`, `/events` | alerts/incidents/events read | alerts/events/incident calls | core routes, incident/event/alert services | S/U |
| `/reports/*`, `/availability` | reports/availability read | report/export/history calls | report and availability services | S/U |
| `/syslog`, `/flow-analytics`, `/qos`, `/bgp` | family read | family API wrappers | corresponding routers/services | S/U; listeners may be disabled |
| `/remote-access` | `remote_access:view` | session/credential calls + WebSocket | `remote_access_routes.py`, session manager, SSH/Telnet | S/U |
| `/users`, `/roles`, `/sites`, `/organizations` | admin-family permissions | user/role/site API wrappers | core routes, auth/authorization | S/U |
| `/cmdb`, `/apm`, `/rca` | family read | dedicated API wrappers | dedicated routers/services/models | S/U |
| `/incident-management`, `/problem-management`, `/change-management` | family read | ITSM API wrappers | dedicated routers/services | S/U |
| `/knowledge-base`, `/help-center` | knowledge/dashboard read | knowledge API wrappers/static help | knowledge routes/service | S/U |

## Mapping limitations

`figma design/src/lib/api.ts` is the primary client index, but some components use direct `fetch` (notably SNMP discovery). UI guards do not prove backend authorization. Pages such as `ISPMonitoring`, `Firewall`, `NginxMonitoring`, `PacketAnalysis` and `Forensics` require endpoint-level review because their UI naming is broader than a single backend router. Runtime route availability and API response compatibility were not tested.

