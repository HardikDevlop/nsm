# API Inventory

Static extraction found 435 `@router` declarations across 26 backend files. The complete route source of truth is the router files; no runtime OpenAPI document was generated.

| API family | Prefix/source | Count |
|---|---|---:|
| Core auth/users/devices/metrics/alerts/reports | `/api/v1`, `api/routes.py` | 131 |
| SNMP/device monitoring | `/api/v1`, `api/snmp_device_routes.py` | 45 |
| Discovery | `/api/v1`, `api/discovery_routes.py` | 42 |
| Windows monitoring/helpers | `/windows`, `windows_monitoring/api.py` | 34 |
| Linux monitoring | `/api/v1/linux-servers` | 25 |
| Knowledge | `/api/v1/knowledge` | 31 |
| Change/incident/problem | dedicated `/api/v1/...` routers | 41 |
| Remote access | `/api/v1` | 15 + WebSocket |
| CMDB/APM/RCA | dedicated `/api/v1/...` routers | 21 |
| Flow/syslog/BGP/QoS | dedicated `/api/v1/...` routers | 15 |
| Other feature routers | backups, compliance, availability, virtualization, topology, overview, legacy | remainder |

Request/response schemas are primarily inline Pydantic models plus `schemas/nms.py` and `schemas/remote_access.py`. Authentication and permissions are applied through dependencies and router-specific checks; exact permission per endpoint must be read from each function and is not inferred from route presence. The separate WebSocket is `@router.websocket("/remote-access/sessions/{session_uuid}/terminal")` in `api/remote_access_routes.py`.

