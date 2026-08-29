# Manual Topology: Small Flow Summary

## Page Entry

- Frontend route: `/manual-topology`
- File: `figma design/src/pages/ManualTopology.tsx`
- Access requires the `topology:read` permission.
- The page keeps the editable workspace in browser `localStorage` under `nms.manual-topology.workspace.v2`.
- The old `v1` local-storage key is removed when the workspace loads.

## Initial Loading

1. The page loads the latest server snapshot from `GET /api/v1/manual-topology/snapshots/latest`.
2. It loads up to 200 active SNMP devices from `GET /api/v1/snmp/devices`.
3. Devices deleted from the backend are removed from the local workspace, along with their links.
4. If no active backend devices exist, the page clears the local workspace and updates the server snapshot to an empty workspace.
5. When a real device is selected, its physical ports are loaded from live SNMP data first and cached interface data second. Virtual interfaces are filtered out and duplicate ports are removed.

## Editing The Canvas

- Import an existing backend device onto the canvas.
- Create a manual device card.
- Edit device name, IP, MAC, location, type, size, and position.
- Move and resize cards by pointer interaction.
- Connect two device ports with the pen/connect mode.
- Prevent duplicate links on the same port.
- Disconnect a selected link or switch its line between straight and curved geometry.
- Switch between `physical` and `logical` views, zoom, and fullscreen canvas mode.
- Remove a device; its connected links are removed as well.
- A five-item topology verification checklist is stored in component state for the current page session.

## Persistence

- Every workspace change is saved locally to `localStorage`.
- After a 900 ms debounce, the workspace is saved to PostgreSQL:
  - New workspace: `POST /api/v1/manual-topology/snapshots`
  - Existing workspace: `PUT /api/v1/manual-topology/snapshots/{snapshot_id}`
- Imported backend devices can also update their name, IP, MAC, and location through the normal device update API.
- Manual-only cards remain browser/workspace data; backend-linked cards use their `backendId` for database updates.

## Health And Reconciliation

- Active backend devices are pinged through `POST /api/v1/discovery/icmp` on page load and every 120 seconds.
- Offline devices are shown with offline status and a session-level toast is shown once per IP.
- Once a server snapshot exists, live topology reconciliation runs immediately and every 120 seconds.
- Reconciliation calls `POST /api/v1/manual-topology/snapshots/{id}/reconcile`.
- The backend obtains live SNMP topology, compares links and linked-device status with the manual baseline, and records pending changes.
- Supported change types include:
  - `CONNECTION_DISCONNECTED`
  - `CONNECTION_ADDED`
  - `DEVICE_OFFLINE`
  - `DEVICE_ONLINE`

## Change Resolution

For each pending change, the user can:

- `accept_real_change`: update the manual baseline to match live topology.
- `keep_manual`: retain the manual baseline and mark the change as manually kept.

The action is sent to:
`POST /api/v1/manual-topology/snapshots/{snapshot_id}/changes/{change_id}/resolve`

## Backend Storage

- `manual_topology_snapshots` stores the workspace JSON, owner, and reconciliation status.
- `manual_topology_changes` stores detected differences, expected state, observed state, resolution status, and notes.
- Backend routes are registered in `hardik/backend/main.py` through `manual_topology_routes.py`.
- Live topology data comes from the existing SNMP topology endpoint and does not change the database schema during page usage.

## Important Behavior

The manual workspace is the editing source of truth. Live SNMP data is used to populate real devices, ports, health status, and reconciliation alerts; it does not automatically overwrite the complete manual canvas unless the user accepts a detected real change.
