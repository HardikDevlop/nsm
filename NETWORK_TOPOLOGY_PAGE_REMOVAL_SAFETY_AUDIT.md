# Network Topology Page Removal Safety Audit

Audit date: 2026-09-18  
Scope: read-only dependency/removal-safety audit. No application code, route, navigation, backend, database, collector, or scheduler code was changed.

## Executive summary

The target UI is `figma design/src/pages/Topology.tsx`, registered at `/topology`; the repository contains no `/network-topology` route. The sidebar label is `Network Topology` and points to `/topology`.

The page component is not a safe deletion candidate yet without first removing its route/navigation consumers and checking the resulting build. The shared graph authority is **not** page-only: `figma design/src/lib/topologyGraphBuilder.ts` is imported by both `Topology.tsx` and `ManualTopology.tsx`. Manual Topology also imports and invokes the backend `get_snmp_topology()` function during reconciliation. Therefore topology APIs, capability data, SNMP topology collection, and the shared builder must be kept.

The smallest safe product change is to remove the sidebar entry and `/topology` route, then remove the page component only after the build/reference checks below pass. No backend or collector removal is justified by this audit.

## 1. Page identification

| Item | Finding |
|---|---|
| Page component | `figma design/src/pages/Topology.tsx` (`Topology` default export) |
| Route | `figma design/src/routes.tsx`: lazy `Topology` import and `path: "topology"`, guarded by `topology:read`; effective URL `/topology` |
| Requested `/network-topology` route | Not found in source search |
| Sidebar entry | `figma design/src/components/Sidebar.tsx:17`: `{ to: '/topology', label: 'Network Topology', ... }` |
| Localized sidebar label | `figma design/src/components/Sidebar.tsx:68`, `NAV_LABELS['Network Topology']` |
| Role label only | `figma design/src/pages/RoleManagement.tsx:40`, display label for the `topology` permission; not a route consumer |
| Dashboard deep link | `figma design/src/pages/Dashboard.tsx:1252`, `navigate('/topology')` |

The page displays the requested graph/statistics, including confirmed/inferred links, MAC/port summaries, port groups, and the rebuild action. Its graph layout/rendering helpers are local to `Topology.tsx`; the logical graph authority is shared.

## 2. Frontend dependencies

### Imports used by the page

From `Topology.tsx`:

- React hooks: `useCallback`, `useDeferredValue`, `useEffect`, `useMemo`, `useRef`, `useState` — page-local usage.
- `GlassCard` from `figma design/src/components/GlassCard.tsx` — shared component; used by many pages.
- `requestJson`, `updateDevice`, `DeviceRecord` from `figma design/src/lib/api.ts` — shared; consumers include Sidebar, SNMP pages, ISP Monitoring, Manual Topology, Device Port Map and others.
- `persistSNMPTopologySnapshot` from `figma design/src/lib/api.ts` — source search found only `Topology.tsx` as a frontend caller; backend endpoint is still part of the topology persistence API and should not be removed solely from this page.
- `streamTopologyUpdates` from `figma design/src/lib/api.ts` — source search found only `Topology.tsx` as a frontend caller; endpoint may be page-specific at present, but requires runtime/client verification before deletion.
- `agnigateLabel`, `isAgnigateMac` from `figma design/src/lib/deviceIdentity.ts` — verify repository-wide consumers before considering any removal; this audit found no reason to remove the module.
- `useNavigate` from `react-router` — shared framework hook.
- `useQueryClient` from `figma design/src/lib/queryProvider.tsx` — shared query infrastructure.
- `useI18n` from `figma design/src/i18n/I18nContext.tsx` — shared context.
- `formatIST` from `figma design/src/time.ts` — shared utility; source search required before any cleanup.
- `buildLogicalTopologyGraph`, `collectTopologyDevice`, `makeNode`, and graph/types/helpers from `figma design/src/lib/topologyGraphBuilder.ts` — shared; see below.

`Topology.tsx` also defines many page-local helpers and render components, including layout, graph rendering, node details, filtering, local-storage/session view state, and refresh orchestration. Those are candidates for removal only with the page, subject to the import/build check.

### Shared graph builder — must keep

`figma design/src/lib/topologyGraphBuilder.ts` exports and consumers:

- `Topology.tsx` imports the builder and supporting graph/correlation helpers.
- `ManualTopology.tsx:30` imports `buildLogicalTopologyGraph`, `collectTopologyDevice`, and `makeNode`.
- `ManualTopology.tsx:1907` invokes `buildLogicalTopologyGraph()`.
- `figma design/tests/topology-graph-accumulator.test.mjs` loads and tests the builder directly.

Conclusion: `buildLogicalTopologyGraph()` and the builder module are shared topology authority and **must keep**. Do not delete or simplify them as part of page removal.

## 3. Backend endpoints used by the page

The page uses these request paths directly or through imported helpers:

| Endpoint/path | Page use | Classification | Other consumers/evidence |
|---|---|---|---|
| `GET /snmp/topology` | Normal topology load and post-refresh revalidation | **B/C/D/E shared** | Manual Topology reconciliation calls backend `get_snmp_topology`; API docs/tests and manual-topology docs reference it. |
| `GET /snmp/topology?refresh=true` | Rebuild Topology action | **B/D shared** | `hardik/backend/api/manual_topology_routes.py:212` calls `get_snmp_topology(..., refresh=True)` for reconciliation. |
| `GET /devices` | Inventory used to build graph | **E shared** | General device inventory consumers; not a topology-only API. |
| `GET /snmp/devices?page=...` | Inventory fallback | **E shared** | SNMP Devices module uses the same device domain/API. |
| `GET /snmp/devices/{id}/{mac|arp|lldp|cdp|routing|...}` | Stored/live module collection through `collectTopologyDevice` and local `collectModule` | **D/E shared data sources** | SNMP monitoring/module infrastructure and collection services; exact module paths are constructed in the shared builder/page. |
| `GET /snmp/devices/{id}` | Node detail panel | **E shared** | SNMP device detail/module routes. |
| `POST /snmp/topology/snapshot` | Persists assembled live graph after refresh | **Possibly page-specific caller; backend shared topology persistence** | Backend persistence is used by later `GET /snmp/topology` responses and is covered by topology tests. Keep pending runtime verification. |
| `GET /snmp/topology/stream` | Cross-client topology update stream | **Possibly page-specific frontend caller; runtime verification required** | Backend docstring says it notifies every client; source search found only `Topology.tsx` frontend subscription. Do not delete endpoint in this audit. |
| device update endpoint via `updateDevice` | Edits selected node metadata | **E shared** | ISP Monitoring, SNMP Monitoring, SNMP Devices, Manual Topology and others call `updateDevice`. |

The page also navigates to `/snmp/devices/:deviceId` for node details. That target route is not page-specific and must remain.

Backend definitions are in `hardik/backend/api/snmp_device_routes.py` around lines 2055, 2130, 2413 and 2443. Manual Topology imports `get_snmp_topology` directly from that module at `hardik/backend/api/manual_topology_routes.py:10` and invokes it at line 212.

## 4. Data producers and reuse

The graph is assembled from persisted and/or live data including:

- SNMP topology capability snapshots (`DeviceCapabilities.capability_detail["topology"]`).
- LLDP/CDP neighbor evidence.
- MAC/FDB and ARP evidence, plus routes and port groups where available.
- Device inventory and device identity/capability records.
- The backend topology collector and `GET /snmp/topology` aggregation.
- The shared frontend `topologyGraphBuilder.ts` correlation/deduplication logic.

These producers are not page-owned:

- Manual Topology reconciliation calls the backend topology function with `refresh=True` and compares live links against manual snapshots.
- Manual Topology uses the shared builder and collection helpers.
- Device Port Map uses manual-topology snapshots and SNMP interface APIs; it must not be affected by removing the automatic graph page.
- Overview/Dashboard reads network/topology summary data and contains a direct navigation card to `/topology`.
- SNMP monitoring/device modules use the same device, capability, interface and collector infrastructure.
- CMDB reconciliation reads topology/LLDP-derived relationships in `hardik/backend/cmdb/service.py`; topology data is therefore not safe to disable as a page cleanup.

No evidence supports removing SNMP LLDP/CDP, MAC/FDB, ARP, capability persistence, topology scheduling, or collector code. The requested scope is page removal only.

## 5. Manual Topology, Port Map, and Overview impact

### Manual Topology

Impact is shared and material. `ManualTopology.tsx` imports the shared graph builder and collection helpers. Its backend reconciliation route imports and invokes `get_snmp_topology`. Removing the page route/component does not justify removing either the builder or the backend topology endpoint.

### Manual Topology Port Map

`DevicePortMap.tsx` uses `getLatestManualTopologySnapshot`, `updateManualTopologySnapshot`, `getSNMPInterfaces`, and `getLatestInterfaces`. It does not import `Topology.tsx` or the shared graph builder in the source search. Keep its snapshot/interface APIs and route unchanged.

### Overview/Dashboard

`Dashboard.tsx:1252` has a direct `navigate('/topology')` action on the Network Information panel. If `/topology` is removed, this is a dead-link risk and must be removed, retargeted, or made non-navigable as part of the UI cleanup. Dashboard network counts are independently backed by overview APIs and must remain.

## 6. Route/navigation/deep-link audit

Repository search found:

- Route registration: `figma design/src/routes.tsx` (`path: "topology"`).
- Sidebar: `figma design/src/components/Sidebar.tsx` (`/topology`, `Network Topology`).
- Dashboard link: `figma design/src/pages/Dashboard.tsx:1252` (`navigate('/topology')`).
- Page-local device detail navigation: `Topology.tsx` -> `/snmp/devices/:deviceId`, which is a retained route.
- No source references to `/network-topology`.
- No additional `Link`, breadcrumb, back-button, or redirect references to `/topology` found by source search beyond the route, sidebar, and dashboard card.

The dashboard card is the primary known dead-link risk after route removal. Browser bookmarks/external deep links cannot be proven safe by source search and should be covered by runtime verification.

## 7. File/symbol classifications

### SAFE TO REMOVE WITH PAGE

Only after the route/navigation references are removed and the build passes:

- Page-local code in `figma design/src/pages/Topology.tsx`.
- Page-local layout/graph rendering helpers and types defined only inside `Topology.tsx`.
- Page-only imports that become unused after removing the page.

The whole `Topology.tsx` file is classified **UNPROVEN until route/build cleanup**, because source search alone does not prove dynamic imports, tests, or deployment manifests absent.

### REMOVE ONLY NAV/ROUTE

- `figma design/src/components/Sidebar.tsx` Network Topology entry.
- `figma design/src/routes.tsx` lazy `Topology` import and `topology` route.
- `figma design/src/pages/Dashboard.tsx` direct `/topology` navigation behavior/card action; retain the network information data unless product direction says otherwise.

### MUST KEEP SHARED

- `figma design/src/lib/topologyGraphBuilder.ts`, especially `buildLogicalTopologyGraph`, `collectTopologyDevice`, `makeNode`, and correlation helpers.
- `figma design/src/lib/api.ts` shared `requestJson`, `updateDevice`, device/interface/manual-topology helpers.
- Manual Topology page and its shared builder/API dependencies.
- Device Port Map page and its snapshot/interface dependencies.
- Overview/Dashboard network summary logic.
- SNMP device/module/capability infrastructure.

### BACKEND MUST KEEP

- `hardik/backend/api/snmp_device_routes.py:get_snmp_topology`.
- `GET /snmp/topology`, including refresh behavior.
- `GET /snmp/devices/{device_id}/device-topology` and topology module support used by SNMP modules.
- Topology snapshot persistence and `DeviceCapabilities` topology data used by Manual Topology and subsequent topology reads.
- Backend topology stream until runtime consumer/operational verification is complete.
- Collector, scheduler, Redis/SNMP/ICMP and topology reconciliation infrastructure.

### POSSIBLY ORPHANED BUT DO NOT DELETE YET

- `streamTopologyUpdates()` frontend API helper and `/snmp/topology/stream` endpoint: only one frontend caller found, but backend describes it as a shared client notification stream.
- `persistSNMPTopologySnapshot()` frontend helper and `POST /snmp/topology/snapshot`: only the page called the helper in source search, but the persisted data is consumed by the shared GET/backend/manual reconciliation path.
- Any page-only CSS classes found only by visual/source inspection after the page removal; run the CSS/build audit first.

### RUNTIME VERIFICATION REQUIRED

- External bookmarks/deep links and deployment-level route manifests.
- Whether another client, packaged frontend, or operational script consumes the topology stream/snapshot endpoints.
- Whether production permissions, telemetry, or scheduled jobs expect the route to exist.

## 8. Safest minimal removal plan (not implemented)

1. Remove the `Network Topology` sidebar item pointing to `/topology`.
2. Remove the `/topology` route and lazy page import.
3. Remove or retarget the Dashboard Network Information panel's `/topology` navigation.
4. Run the validation checks below.
5. Delete `Topology.tsx` only after no import/build/reference remains.
6. Remove only page-exclusive frontend helpers proven unused by repository-wide search.
7. Keep `topologyGraphBuilder.ts`, Manual Topology, Port Map, Overview data paths, backend APIs/services, capability persistence, collectors, and scheduler.
8. Do not change database state or remove APIs in this page-only change.

## 9. Validation plan after removal

Run from the repository root:

```bash
cd "figma design"
npm run build
rg -n --glob '!node_modules' --glob '!dist' 'NetworkTopology|from ["'"']\.\/pages\/Topology|pages\/Topology|/topology|network-topology' src tests
rg -n --glob '!node_modules' --glob '!dist' 'topologyGraphBuilder|buildLogicalTopologyGraph|collectTopologyDevice' src tests
rg -n --glob '!node_modules' --glob '!dist' 'get_snmp_topology|/snmp/topology|snmp/topology' ../hardik backend src ../*.md
```

Then specifically verify:

- Manual Topology still imports/builds with `topologyGraphBuilder.ts` and can load/reconcile its snapshot.
- Manual Topology Port Map still resolves snapshot and interface APIs.
- Dashboard/Overview no longer emits a dead `/topology` navigation while its network information data still renders.
- SNMP Devices, Device Monitoring, Packet Analysis, Linux Server Monitoring, alerts/events, and other modules have no removed imports or route assumptions.
- Backend compile/tests are required only if backend code is changed; for a frontend-only removal, run the existing frontend build/test suite and the focused topology/manual-topology tests as available.
- Runtime-authenticated checks should confirm `/manual-topology`, its port-map route, Overview, SNMP Devices, and Manual Topology reconciliation continue working.

## Final status

```text
NETWORK TOPOLOGY PAGE IDENTIFIED: YES
ROUTE IDENTIFIED: YES (/topology; requested /network-topology does not exist)
SIDEBAR ENTRY IDENTIFIED: YES
SHARED BUILDER USED: YES
MANUAL TOPOLOGY DEPENDENCY FOUND: YES
PORT MAP DEPENDENCY FOUND: YES (separate manual snapshot/interface APIs; no page import)
OVERVIEW DEPENDENCY FOUND: YES (network summary plus direct /topology navigation)
BACKEND SHARED DEPENDENCIES FOUND: YES
COLLECTOR SHARED DEPENDENCIES FOUND: YES
PAGE COMPONENT SAFE TO DELETE: UNPROVEN until route/nav removal and build/reference validation
PAGE-ONLY HELPERS SAFE TO DELETE: UNPROVEN until post-route repository/build check
BACKEND ENDPOINTS SAFE TO DELETE: NO / UNPROVEN
TOPOLOGY COLLECTOR SAFE TO DELETE: NO
SAFE MINIMAL REMOVAL POSSIBLE: YES, frontend route/navigation removal only
CODE CHANGED: NO (audit report created as requested)
```
