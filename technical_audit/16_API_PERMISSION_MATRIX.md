# API and Permission Matrix

## Registration and complete source index

The backend mounts routers in `hardik/backend/main.py`. Decorator extraction on the audited tree found 435 route declarations across the following source files. The file counts are an index to the complete endpoint set; each file contains the exact path, method, function, parameters and inline schema.

| Mounted prefix | Source router | Declarations | Authorization evidence |
|---|---|---:|---|
| `/api/v1` | `api/routes.py` | 131 | mixed core dependencies; inspect function-level checks |
| `/api/v1` | `api/discovery_routes.py` | 42 | permission/site checks present in functions |
| `/api/v1` | `api/snmp_device_routes.py` | 45 | router-level `_require_site_scope`; function permissions |
| `/api/v1` | `api/manual_topology_routes.py` | 5 | `topology:read` dependency |
| `/api/v1` | `api/monitoring_data_routes.py` | 2 | `devices:read` and site lookup |
| `/api/v1/flows/analytics` | `api/flow_routes.py` | 2 | flow permission dependency |
| `/api/v1/apm` | `api/apm_routes.py` | 7 | `apm:read` / `apm:ingest` |
| `/api/v1/cmdb` | `api/cmdb_routes.py` | 11 | `cmdb:read/manage` |
| `/api/v1/rca` | `api/rca_routes.py` | 3 | `rca:read/execute` |
| `/api/v1/incidents` | `api/incident_routes.py` | 13 | incidents read/update/manage and RCA |
| `/api/v1/problems` | `api/problem_routes.py` | 6 | problems read/update/manage |
| `/api/v1/changes` | `api/change_routes.py` | 22 | changes read/update/manage |
| `/api/v1/knowledge` | `api/knowledge_routes.py` | 31 | knowledge read/create/update |
| `/api/v1/config-backups` | `api/config_backup_routes.py` | 5 | backups read/execute |
| `/api/v1/config-compliance` | `api/config_compliance_routes.py` | 4 | compliance read/manage/execute |
| `/api/v1/availability` | `api/availability_routes.py` | 4 | `availability:read` |
| `/api/v1/virtualization` | `api/virtualization_routes.py` | 3 | virtualization read/manage |
| `/api/v1/qos` | `api/qos_routes.py` | 2 | qos permissions |
| `/api/v1/bgp` | `api/bgp_routes.py` | 2 | bgp read/ingest |
| `/api/v1/syslog` | `api/syslog_routes.py` | 9 | syslog permissions |
| `/api/v1/linux-servers` | `linux_monitoring/api.py` | 25 | Linux permission dependencies |
| `/windows` | `windows_monitoring/api.py` | 34 | Windows permission/site checks in functions |
| `/windows` | `windows_monitoring/helper_api.py` | included by `main.py` | helper-specific auth/security functions |
| `/api/v1` | `api/remote_access_routes.py` | 15 + WebSocket | explicit `remote_access:*` checks and site checks |
| no added prefix | `api/overview_routes.py`, `legacy_routes.py` | 8 | overview/legacy function-level behavior |

## Schema and permission rules

Request schemas are inline Pydantic classes in feature routers or shared classes in `backend/schemas/nms.py` and `schemas/remote_access.py`; response models are often dictionaries or ORM-derived payloads rather than declared `response_model`s. Central authorization is `get_current_user` → `require_permission(code)` in `backend/dependencies.py`. Remote access additionally checks `get_user_permission_codes` explicitly. `_require_site_scope` is router-level for SNMP, while other families implement device/site checks selectively.

## Verification status

This is source-complete by router-file index, not a generated runtime OpenAPI catalog. Exact request/response shape and permission for every one of 435 declarations should be regenerated from AST/OpenAPI in CI; runtime 401/403 and response validation remain unverified.

