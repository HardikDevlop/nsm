# Module and Feature Inventory

Status reflects static evidence only. No tests, services, migrations, or device operations were run.

| Module | Status | Evidence |
|---|---|---|
| Dashboard/overview | IMPLEMENTED — UNVERIFIED | `api/overview_routes.py`, `pages/Dashboard.tsx` |
| Discovery/onboarding | IMPLEMENTED — UNVERIFIED | `api/discovery_routes.py`, `services/discovery.py`, `discovery_modules/*` |
| Device inventory/sites/vendors | IMPLEMENTED — UNVERIFIED | `api/routes.py`, core models/schemas, `AllDevices.tsx`, `Sites.tsx` |
| ICMP availability | IMPLEMENTED — UNVERIFIED | `monitoring_modules/icmp_monitor.py`, `services/availability.py`, availability routes |
| SNMP v2c/v3 | IMPLEMENTED — UNVERIFIED | `backend/snmp/*`, `snmp_device_routes.py`, SNMP feature pages |
| SSH/Telnet remote access | IMPLEMENTED — UNVERIFIED | `services/remote_access/*`, remote-access REST/WebSocket route, `RemoteAccess.tsx` |
| Windows monitoring | IMPLEMENTED — UNVERIFIED | `windows_monitoring/*`, Windows routes/pages/tests |
| Linux monitoring | IMPLEMENTED — UNVERIFIED | `linux_monitoring/*`, Linux routes/page |
| Topology/interfaces/bandwidth | IMPLEMENTED — UNVERIFIED | SNMP collectors, topology APIs, manual topology pages |
| Alerts/incidents/events | IMPLEMENTED — UNVERIFIED | `services/alerting.py`, alert engine, incident/event models/routes/pages |
| Email notifications | IMPLEMENTED — UNVERIFIED | `services/report_email.py`, alerting/settings SMTP fields |
| Syslog | IMPLEMENTED — UNVERIFIED | `backend/syslog`, `api/syslog_routes.py`, `SyslogManagement.tsx` |
| sFlow/IPFIX | IMPLEMENTED — UNVERIFIED / feature-gated | `backend/flow/*`, `FlowReceiver`; `flow_enabled` defaults false |
| Reports/exports | IMPLEMENTED — UNVERIFIED | report CSV/XLSX/PDF/email/schedule services and pages |
| User/RBAC/audit | IMPLEMENTED — UNVERIFIED | auth, core routes/models, permission guards, audit services/pages |
| CMDB/APM/RCA/ITSM | IMPLEMENTED — UNVERIFIED | dedicated APIs/models/services/pages |
| Remote collectors | PARTIAL | collector concepts are not verified as a separate deployable agent; single backend ingestion exists |
| Windows certificate trust/diagnostics | IMPLEMENTED — UNVERIFIED | Windows CA services/routes/components/tests |
| Service/application monitoring | PARTIAL | APM and Nginx modules exist; broad service-monitoring production behavior is unverified |
| Help Center/knowledge | IMPLEMENTED — UNVERIFIED | knowledge routes/models and Help Center/Knowledge Base pages |

## Common flow

The intended flow is frontend/API request or scheduler trigger → service/protocol adapter → normalization and persistence → alert/report/dashboard consumers. Exact behavior is source-supported; successful device/database execution is unverified.

