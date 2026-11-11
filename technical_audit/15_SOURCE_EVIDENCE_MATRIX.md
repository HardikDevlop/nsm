# Source Evidence Matrix

Legend: **S** = source implementation found; **U** = runtime behavior unverified; **P** = partial/ambiguous; **N** = not found.

| Capability | Backend evidence | Frontend evidence | Model/migration evidence | Tests/docs | Status |
|---|---|---|---|---|---|
| Auth/RBAC | `dependencies.py`, `auth/security.py`, `auth/authorization.py` | `AuthContext`, `ProtectedLayout`, `PermissionGuard` | users/roles/permissions/sessions | auth-related tests/docs | S/U |
| Sites/tenancy | core routes, `can_access_site` | `Sites.tsx`, site filters | sites, user_sites, site FKs | route-specific tests | S/P/U |
| Discovery | `api/discovery_routes.py`, `services/discovery.py`, discovery modules | `ISPMonitoring`, SNMP discovery | devices/interfaces/identity | discovery tests | S/U |
| ICMP | `icmp_monitor.py`, availability services | availability/device pages | metrics/availability/outages | availability tests | S/U |
| SNMP | client, security, collectors, poll scheduler | `features/snmp/*` | SNMP and latest/history tables | SNMP tests/docs | S/U |
| Windows | Windows API/CIM/WinRM/snapshots/trust/helper | Windows pages/components | Windows snapshot/history/event/CA/helper tables | focused Windows tests | S/U |
| Linux | Linux API/service/metrics/scheduler | Linux page | Linux models/migrations | Linux-related tests | S/U |
| Alerts/recovery | `analytics_modules/alert_engine.py`, `services/alerting.py`, threshold services | alerts/incidents/notifications | alerts/events/notifications/incidents | alert regressions | S/U; workflow details need validation |
| Reports | report management/export/email/schedule services | report pages | report schedules/generated reports | report tests/artifacts | S/U |
| Remote access | SSH/Telnet services, session manager, WebSocket route | `RemoteAccess.tsx` | credentials/host keys/sessions | remote access tests | S/U |
| Syslog | `backend/syslog`, syslog routes | `SyslogManagement.tsx` | syslog records/rules | syslog tests | S/U; disabled by default |
| sFlow/IPFIX | `backend/flow` receiver/parser/service | `FlowAnalytics.tsx` | flow records/sFlow samples | flow tests | S/U; disabled by default |
| ITSM/CMDB/RCA/knowledge | dedicated routes/services/models | dedicated pages | corresponding tables/links/history | feature tests | S/U |
| Remote collectors | no separate agent/package located | no collector deployment page verified | no collector entity conclusively located | no deployable collector artifact | P/N |

