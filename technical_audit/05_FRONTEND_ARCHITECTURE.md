# Frontend Architecture

The frontend is a React 19/TypeScript SPA built with Vite 8 and Tailwind CSS v4. `src/main.tsx` mounts `App.tsx`; `routes.tsx` uses React Router with lazy loading and a protected layout. `AuthContext`, `ProtectedLayout`, `PermissionGuard`, `RealtimeController`, and `lib/api.ts` provide authentication, authorization, API access and realtime behavior.

## UI surface

There are 53 page components plus a substantial SNMP feature subtree. Routes cover dashboard, devices, Windows/Linux, SNMP, topology, alerts/events, reports, syslog, remote access, administration, ITSM, CMDB/APM/RCA, flow/QoS/BGP, compliance and help/knowledge.

| UI area | Route/source | Backend evidence | Status |
|---|---|---|---|
| Core dashboard/devices | `routes.tsx`, `Dashboard.tsx`, `AllDevices.tsx` | `/api/v1` core/overview routes | IMPLEMENTED — UNVERIFIED |
| SNMP | `features/snmp/routes.tsx`, hooks/modules | `snmp_device_routes.py`, SNMP services | IMPLEMENTED — UNVERIFIED |
| Windows/Linux | Windows and Linux pages/components | Windows and Linux API routers | IMPLEMENTED — UNVERIFIED |
| Remote access | `RemoteAccess.tsx` | REST plus authenticated terminal WebSocket | IMPLEMENTED — UNVERIFIED |
| Admin/RBAC | users, roles, sites, credentials, audit pages | core routes/auth/dependencies | IMPLEMENTED — UNVERIFIED |
| Reports/ITSM | reports, incidents, problems, changes, knowledge | dedicated routers/services | IMPLEMENTED — UNVERIFIED |

The client contains typed API wrappers and direct `fetch` use in some feature components, so API access is not completely centralized. Frontend tests are present but were not executed; route/API availability and build correctness remain unverified.

