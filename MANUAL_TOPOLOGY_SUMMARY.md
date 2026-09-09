# Manual Topology Page Summary

## 1. Purpose

The manual topology feature lets users build and maintain a network diagram by hand, then compare that diagram against live SNMP topology data.

It is designed as a hybrid workflow:

- The manual canvas is the editable source of truth.
- Live SNMP data is used for device import, port discovery, health checks, and reconciliation alerts.
- The backend stores the manual baseline and any detected differences.

## 2. Frontend Entry Point

- Page component: [`figma design/src/pages/ManualTopology.tsx`](figma%20design/src/pages/ManualTopology.tsx)
- Route guard: `topology:read`
- Sidebar label: `Manual Topology`
- Route path: `/manual-topology`

The page is rendered inside the existing app shell and uses the shared glass-style UI system from the frontend.

## 3. Frontend Data Model

The page works with two main client-side objects:

- `Device`
- `Link`

The current workspace shape is:

```ts
type Workspace = {
  devices: Device[]
  links: Link[]
}
```

Important device fields:

- `id`
- `name`
- `subtitle`
- `type`
- `tone`
- `x`, `y`
- `backendId`
- `ports`
- `portStatuses`
- `status`
- `ipAddress`
- `macAddress`
- `location`
- `width`
- `height`

Important link fields:

- `id`
- `from`
- `to`
- `label`
- `fromPort`
- `toPort`
- `geometry`

## 4. Frontend State And Persistence

The page keeps state in both memory and browser storage.

Storage keys:

- `nms.manual-topology.workspace.v2`
- legacy cleanup key `nms.manual-topology.workspace.v1`
- offline alert state `nms.device-health.offline-alerts.v1`

Behavior:

- The page loads the latest server snapshot on first render.
- The local workspace remains the editing source.
- Workspace changes are debounced and saved to the backend after about 900 ms.
- If the local v1 workspace exists, it is removed during migration/cleanup.
- If all backend devices disappear, the workspace is cleared locally and the server snapshot is also updated to an empty topology.

## 5. Frontend Initial Workspace

The page starts with a sample topology if nothing is stored yet. The seed diagram includes:

- Internet / ISP
- Firewall
- Core switch
- Two access switches
- User and server segments

This gives users a visible starting point instead of a blank canvas.

## 6. Frontend SNMP Integration

The page imports and syncs real devices from SNMP inventory.

Main frontend API calls:

- `listSNMPDevicesOptimized({ page: 1, page_size: 200 })`
- `getSNMPInterfaces(deviceId)`
- `getLatestInterfaces(deviceId)`
- `pingIps(ips, 1000)`
- `updateDevice(deviceId, payload)`

What happens:

- Real devices are loaded from the SNMP device list.
- Deleted backend devices are removed from the manual workspace.
- Selected backend-linked devices load their ports from live SNMP first, then cached interface data if needed.
- Virtual interfaces are filtered out.
- Duplicate ports are removed.
- Device health is checked with ping every 120 seconds.
- Offline devices trigger a toast once per IP per session.

## 7. Frontend Editing Features

The page supports a full manual topology editor.

Users can:

- Import a real SNMP device into the canvas
- Create a new manual device card
- Edit name, IP, MAC, location, type, size, and position
- Drag and resize devices
- Connect ports in pen/connect mode
- Remove links
- Remove devices and their attached links
- Toggle link geometry between straight and curved
- Switch between manual, actual, and compare views
- Zoom, pan, and use fullscreen canvas mode
- Search and filter by device/link attributes
- Review verification warnings and reconciliation status

## 8. Frontend Verification Logic

The page computes a comparison between:

- the manual workspace
- the live SNMP topology returned by the backend

Verification statuses:

- `VERIFIED`
- `DISCONNECTED`
- `UNEXPECTED`
- `PORT_MISMATCH`
- `DEVICE_OFFLINE`
- `UNKNOWN`

The UI shows:

- total link count
- verified count
- issue count
- unexpected link count
- offline device count

Matching logic checks:

- device pairs
- port pairs
- device health
- whether the live topology contains the same connection

## 9. Frontend Reconciliation Flow

When a snapshot exists, the page reconciles automatically:

- immediately after load
- every 120 seconds

Frontend call:

- `reconcileManualTopology(snapshotId)`

The response is used to:

- refresh the pending change list
- update live topology comparison state
- show any detected drift between baseline and reality

Supported change types shown in the UI:

- `CONNECTION_DISCONNECTED`
- `CONNECTION_ADDED`
- `DEVICE_OFFLINE`
- `DEVICE_ONLINE`

## 10. Frontend Change Resolution

Users can resolve each pending reconciliation change in one of two ways:

- `accept_real_change`
- `keep_manual`

Frontend call:

- `resolveManualTopologyChange(snapshotId, changeId, action, note?)`

Behavior:

- Accepting a real connection change updates the baseline links.
- Accepting a device status change updates the baseline device status.
- Keeping manual preserves the baseline and marks the change as manually retained.

## 11. Backend Entry Point

- Main backend file: [`hardik/backend/main.py`](hardik/backend/main.py)
- Route module: [`hardik/backend/api/manual_topology_routes.py`](hardik/backend/api/manual_topology_routes.py)
- Models: [`hardik/backend/models/manual_topology.py`](hardik/backend/models/manual_topology.py)

The router is included directly in the FastAPI app and is served under `/api/v1`.

## 12. Backend Authorization

All manual topology endpoints require:

- authenticated access
- `topology:read` permission

This means the feature is not public and is tied to the existing RBAC model.

## 13. Backend API Endpoints

### Create Snapshot

- `POST /api/v1/manual-topology/snapshots`

Request body:

```json
{
  "name": "Manual topology",
  "payload": {}
}
```

Purpose:

- create a new manual topology baseline
- store the workspace JSON in PostgreSQL

### Update Snapshot

- `PUT /api/v1/manual-topology/snapshots/{snapshot_id}`

Purpose:

- replace the saved baseline with the current workspace

### Get Latest Snapshot

- `GET /api/v1/manual-topology/snapshots/latest`

Purpose:

- fetch the most recently updated snapshot for the current user

### Reconcile Snapshot

- `POST /api/v1/manual-topology/snapshots/{snapshot_id}/reconcile`

Purpose:

- fetch live SNMP topology
- compare it with the manual baseline
- record any detected drift
- return the baseline plus live topology

### Resolve Change

- `POST /api/v1/manual-topology/snapshots/{snapshot_id}/changes/{change_id}/resolve`

Request body:

```json
{
  "action": "accept_real_change",
  "note": "optional note"
}
```

Purpose:

- mark a detected change as accepted or manually retained
- optionally update the snapshot payload if the real-world change is accepted

## 14. Backend Snapshot Model

### `ManualTopologySnapshot`

Table: `manual_topology_snapshots`

Columns:

- `name`
- `payload`
- `last_reconciled_at`
- `reconcile_status`
- `created_by`

Notes:

- `payload` stores the full workspace JSON
- `created_by` links the snapshot to the owning user
- `reconcile_status` tracks sync state such as `not_checked`, `changes_found`, `in_sync`, or `error`

### `ManualTopologyChange`

Table: `manual_topology_changes`

Columns:

- `snapshot_id`
- `change_type`
- `signature`
- `expected_state`
- `observed_state`
- `status`
- `detected_at`
- `resolved_at`
- `resolved_by`
- `resolution_note`

Notes:

- `status` starts as `pending`
- resolution updates the row with who handled it and how
- the change record keeps an audit trail of baseline drift

## 15. Backend Reconciliation Logic

The reconcile endpoint works in three main stages:

1. It pulls live topology from `get_snmp_topology(device_id=None, refresh=True, db=db, _=current_user)`.
2. It maps live devices and links back into the manual snapshot using device IDs, names, and backend IDs.
3. It compares baseline links and device status with the live network.

Detected differences include:

- missing baseline links
- newly observed live links
- device online/offline flips

Implementation details:

- Links are normalized through a link key built from device and port pairs.
- Only links that have both `fromPort` and `toPort` are treated as baseline links.
- Device health is compared using online/offline semantics instead of raw status strings.
- Duplicate unresolved changes are not inserted again if a matching pending/accepted/kept record already exists.

## 16. Change Resolution Behavior

When a change is resolved:

- connection changes may rewrite the snapshot `links`
- device status changes may rewrite the snapshot `devices`
- a note can be attached
- the current user is stored as `resolved_by`

Accepted states:

- `accepted`
- `kept_manual`

This design keeps manual edits explicit while still allowing the baseline to follow reality when the operator approves it.

## 17. Live Topology Source

The backend does not invent its own live view for manual topology.

Instead it reuses:

- `get_snmp_topology(...)` from the SNMP device routes

That means manual topology reconciliation is built on top of the existing SNMP topology stack and does not require a separate discovery pipeline.

## 18. Important UX And Data Rules

- Manual topology remains editable even when live topology differs.
- Live SNMP data never silently overwrites the full canvas.
- Only an explicit resolve action updates the baseline to match reality.
- Backend-linked devices can update their stored device record through the normal device update API.
- Manual-only devices stay in the workspace JSON unless deleted by the user.

## 19. Practical Summary

If you want the shortest possible explanation:

- The React page is a visual topology editor backed by localStorage and PostgreSQL.
- It imports live SNMP devices and ports.
- It pings devices and reconciles the manual diagram against real network state.
- The FastAPI backend persists snapshots and drift records.
- Operators can accept real changes or keep the manual baseline.

## 20. Related Files

- [`figma design/src/pages/ManualTopology.tsx`](figma%20design/src/pages/ManualTopology.tsx)
- [`figma design/src/lib/api.ts`](figma%20design/src/lib/api.ts)
- [`hardik/backend/api/manual_topology_routes.py`](hardik/backend/api/manual_topology_routes.py)
- [`hardik/backend/models/manual_topology.py`](hardik/backend/models/manual_topology.py)
- [`hardik/backend/main.py`](hardik/backend/main.py)
- [`manual_topology_guide.md`](manual_topology_guide.md)

## 21. End-To-End Audit Completion

The Manual Topology page was completed within its existing frontend/backend flow.

### Function Matrix

| Feature | Status |
|---|---|
| Real SNMP inventory import | WORKING |
| Add/remove devices and links | WORKING |
| Port-aware connection mode | WORKING |
| Drag, resize, snap, layout | FIXED |
| Autosave and reload persistence | WORKING |
| Manual / Actual / Compare views | WORKING |
| Reconciliation and explicit resolution | FIXED |
| Search and filters | WORKING |
| Pan, zoom, fit, reset, fullscreen | FIXED |
| Undo/redo | WORKING |
| Connection-level verification details | FIXED |
| Double-click device details modal | FIXED |

### Physical Verification Rules

- Reconciliation reuses the existing live SNMP topology collector.
- Device and port pairs are normalized and reverse direction is treated as equivalent.
- A matching live endpoint pair is `VERIFIED`.
- The same devices on different ports are `PORT_MISMATCH` and retain the detected ports as the suggested connection.
- A live link with no sufficient physical evidence is not treated as proof by ping alone.
- Missing evidence produces `UNKNOWN`; it does not produce a false `DISCONNECTED` result.
- `KEEP MANUAL` leaves the baseline unchanged and persists a retained warning.
- `ACCEPT REAL CHANGE` updates only the affected baseline connection or device status.

### UI Changes In This Audit

- Device details are opened with double-click; single-click selects only.
- The permanent left palette and right details sidebar were removed from the canvas layout.
- The device palette is now compact and horizontal above the canvas.
- Cards use smaller defaults, hostname/IP-first content, health state, port summary, and dynamic type glyphs.
- Empty canvas drag pans naturally; Shift-drag selects a region.
- Wheel zoom is bounded and centered around the pointer; reset clears pan and zoom.
- Connected lines continue to derive their endpoints from persisted device coordinates.

### Files Changed

- `figma design/src/pages/ManualTopology.tsx`
- `hardik/backend/api/manual_topology_routes.py`
- `hardik/tests/test_topology_persistence.py`
- `MANUAL_TOPOLOGY_SUMMARY.md`

### Database Migration

NO. Existing `manual_topology_snapshots` and `manual_topology_changes` tables already support the required audit fields.

### Verification Results

- Frontend `npm run build`: PASS
- Frontend `npm test`: PASS, 17 tests
- Python `compileall`: PASS
- `git diff --check`: PASS
- Backend `pytest`: NOT RUN, `pytest` is not installed in this environment.

### Browser Verification Steps

1. Open `/manual-topology` with a user that has `topology:read`.
2. Import two real SNMP devices and open each card to confirm real interface names.
3. Connect selected physical ports and inspect the status directly on the link.
4. Use Compare and Reconcile to review live evidence and suggested port changes.
5. Test `KEEP MANUAL` and confirm the warning remains after reload.
6. Double-click a card to open details, close the modal, and confirm selection/layout did not change.
7. Test empty-canvas pan, pointer-centered wheel zoom, `FIT`, `RESET`, fullscreen, card drag, resize, and reload persistence.

Physical verification is only a PASS when the persisted/live SNMP topology contains sufficient physical evidence. This implementation does not claim a live-device verification result without that evidence.
