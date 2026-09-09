# Manual Topology

## 1. Purpose

Manual Topology is a visual network design workspace. It lets an operator create a desired topology manually, attach real monitored devices, connect device ports, save the design as a user-owned snapshot, and compare the design with automatically discovered SNMP topology.

Frontend entry point: `figma design/src/pages/ManualTopology.tsx`

Backend entry point: `hardik/backend/api/manual_topology_routes.py`

Route: `/manual-topology`

Required permission: `topology:read`

## 2. Topology Views

The canvas has three modes:

| View | What it shows | Editing |
| --- | --- | --- |
| `MANUAL` | The saved operator design, including manually added devices and links | Enabled |
| `ACTUAL` | The automatically discovered SNMP topology from `/snmp/topology` | Read-only |
| `COMPARE` | The manual design plus actual links that are not present in the manual design | Manual canvas remains the baseline |

The actual topology is loaded when the page opens and refreshed every 30 seconds. If a saved manual snapshot exists, its reconciliation process can also refresh the actual data every 120 seconds.

## 3. Device Management

### Add a custom device

1. Open `More ...` or `Devices`.
2. Choose a device type: Firewall, Router, Switch, Server, Wireless, or Generic Device.
3. Enter name, optional IP, optional MAC, and optional location.
4. The device is added with a local `manual-<timestamp>` ID and a fallback port named `Manual Port 1`.

IP and MAC values are validated before the device is created.

### Import a monitored device

The device palette loads up to 200 devices from the optimized SNMP device list. Selecting a device imports its backend ID, hostname, IP, MAC, type, status, vendor data, model, serial, firmware, SNMP version, monitoring state, and last-seen value.

Imported devices use IDs such as `device-12` and retain `backendId: 12`, which is required for interface lookup and live reconciliation.

### Edit or remove a device

- Select a device to open its details panel.
- `Edit Device` changes the displayed hostname and updates the backend device hostname when the device has a backend ID.
- `Remove From Topology` removes only the device from the manual workspace and removes its attached manual links. It does not delete the monitored backend/SNMP device.

## 4. Port and Interface Discovery

When a monitored device is selected, the page requests:

- Current interfaces from `/snmp/devices/{device_id}/interfaces`.
- Latest persisted interfaces from `/snmp/devices/{device_id}/interfaces/latest`.

The current SNMP response is preferred; the latest persisted response is used as a fallback. Virtual or non-physical interfaces are excluded from the Physical Ports view. The All Interfaces view includes the complete available interface list.

Each port displays:

- Interface name
- `ifIndex`
- Operational status
- Speed
- Data source: `SNMP`, `LATEST`, or `MANUAL PORT`

Port search and status filters support `ALL`, `UP`, and `DOWN`.

If no interface data is available, the page exposes `Manual Port 1` so a custom design can still be created.

## 5. Connecting Devices

1. Select `CONNECT`.
2. Select a source device port.
3. Select a different destination device.
4. Select the destination port.
5. Review the port-to-port preview.
6. Select `Create & Save Link`.

The created link stores:

- Source and destination device IDs
- Source and destination port names
- Source and destination interface indexes when available
- Whether each port came from SNMP, latest persisted data, or manual fallback
- Initial status `VERIFYING`

Duplicate links with the same direction and ports are rejected. A device cannot be connected to itself.

After saving, the page requests reconciliation and updates the link status using the available physical evidence:

- `VERIFIED`: matching physical evidence was found.
- `DISCONNECTED`: reconciliation reported a mismatch.
- `DEVICE_OFFLINE`: a related device is offline.
- `UNKNOWN`: physical evidence was not sufficient.

## 6. Link Editing

Select a link to access its editing toolbar:

- `+ Bend`: adds a routing point at the midpoint.
- Drag a routing point to change the path.
- `Remove Bend`: removes the last routing point.
- `Reset Route`: removes all routing points.
- `Delete Link`: removes the selected manual link.

Link colors are status-based:

- Green: verified
- Gold: mismatch or port mismatch
- Red: unexpected or disconnected
- Gray: unknown or offline

Unknown and disconnected links use a dashed line.

## 7. Saving and Persistence

Changes are persisted in two places:

1. Browser `localStorage` under `nms.manual-topology.workspace.v2` for immediate reload recovery.
2. Backend manual topology snapshot APIs for user-owned persistent storage.

Workspace saves are debounced by approximately 900 ms. The first save creates a snapshot. Later saves update the same snapshot ID.

The page restores the latest snapshot owned by the current user on mount. If the API is unavailable, the browser cache still provides the last local workspace where available.

The following edits are saved:

- Device creation, import, rename, removal
- Device movement
- Link creation, deletion, and status changes
- Link routing points
- Auto-layout positions

## 8. Automatic Topology Integration

The page calls `getSNMPTopology()` and converts the result into the read-only Actual workspace. It accepts both common backend link shapes:

- `from` / `to`
- `source_node` / `target_node`
- `source_device_id` / `target_device_id`

Ports are read from `fromPort` / `toPort`, `source_port` / `target_port`, or `local_port` / `remote_port`.

Auto-discovered devices are normalized to the same UI ID format used by imported devices: `device-<backend_id>`. This allows the Actual canvas to draw links correctly even when the backend returns numeric IDs.

The Actual view is read-only so automatic polling cannot overwrite the manual design.

## 9. Reconciliation and Differences

Reconciliation is available after a manual snapshot exists. The backend:

1. Loads the saved manual snapshot.
2. Performs a live topology collection through the SNMP topology service.
3. Normalizes observed links to the manual device IDs.
4. Compares port-to-port links using an order-independent endpoint key.
5. Detects disconnected links, added links, and device online/offline changes.
6. Stores unresolved changes against the snapshot.

The page displays unresolved changes in the `Connectivity mismatch` panel.

Each difference can be opened to inspect:

- Manual connection
- Actual physical connection
- Status
- Evidence source
- Confidence
- Last verification time

Resolution options:

- `Keep Manual`: keep the saved design as the intended baseline.
- `Accept Real Change`: update the saved snapshot to the observed connection or device status.

## 10. Canvas and Navigation Controls

- `Auto Layout`: places devices into a grid.
- `Fit to View`: resets zoom and pan.
- `Undo` / `Redo`: maintains up to 40 workspace history states.
- `Snap On/Off`: snaps moved devices to a 20-pixel grid when enabled.
- Zoom controls: zoom in, zoom out, and fit.
- Canvas drag: pans the workspace.
- Search: filters visible manual devices by name, subtitle, IP, MAC, or type.
- Type filter: limits devices to one device type.
- Health filter: shows all, online, or offline devices.
- Sidebar: toggles the overview panel.
- Mini-map: shows device/link positions and the current viewport.

Keyboard shortcuts:

| Shortcut | Action |
| --- | --- |
| `Ctrl/Cmd + Z` | Undo |
| `Ctrl/Cmd + Shift + Z` or `Ctrl/Cmd + Y` | Redo |
| `Delete` / `Backspace` | Remove selected device or link |
| `Escape` | Clear selection or cancel connection mode |
| `/` | Focus device search |
| `F` | Fit to view |
| `L` | Auto-layout |

## 11. Export

- `SVG` downloads the current SVG canvas.
- `PNG` rasterizes the current SVG canvas and downloads it as PNG.
- `PDF` opens the browser print flow for PDF export.

## 12. API Contract

Frontend API wrappers are in `figma design/src/lib/api.ts`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/snmp/topology` | Load automatic topology |
| `GET` | `/manual-topology/snapshots/latest` | Load the current user's latest manual snapshot |
| `POST` | `/manual-topology/snapshots` | Create the first manual snapshot |
| `PUT` | `/manual-topology/snapshots/{snapshot_id}` | Save later workspace changes |
| `POST` | `/manual-topology/snapshots/{snapshot_id}/reconcile` | Collect live topology and detect differences |
| `POST` | `/manual-topology/snapshots/{snapshot_id}/changes/{change_id}/resolve` | Keep manual or accept the real change |
| `GET` | `/devices` optimized list | Load devices available for import |
| `GET` | `/snmp/devices/{device_id}/interfaces` | Load current interfaces |
| `GET` | `/snmp/devices/{device_id}/interfaces/latest` | Load persisted interface fallback |

All manual topology endpoints require `topology:read` through the backend permission dependency.

## 13. Review Notes and Known Limitations

### Current strengths

- Manual and automatic topology are separated, so polling does not overwrite the operator design.
- Workspace persistence has both browser and backend recovery paths.
- Link comparison is port-aware and direction-independent.
- Interface fallback allows manual connections even when live SNMP interface data is unavailable.
- The page supports real device metadata, physical ports, statuses, evidence, and change resolution.

### Items to monitor or improve

1. **Actual data has two refresh paths.** The direct automatic topology sync runs every 30 seconds, while snapshot reconciliation runs every 120 seconds after a snapshot exists. These paths can update `actualWorkspace` from different response shapes. A future cleanup should use one shared normalizer for both paths.

2. **Compare currently detects unexpected links by endpoint IDs only.** The comparison at the page layer compares sorted device IDs and does not include ports. Backend reconciliation is port-aware, but the red Compare overlay can therefore group two links between the same devices together even when their ports differ.

3. **Manual device IDs cannot be reconciled to live devices without `backendId`.** Custom devices are intentionally manual-only. They will not produce physical evidence until an imported monitored device with a backend ID is used.

4. **Port lists are capped visually.** Device nodes render the first eight ports in the canvas. The port panel remains the place to access the full interface list.

5. **Save errors are shown as a toast only.** The workspace remains in browser state, but there is no persistent retry queue for a failed backend save.

6. **Automatic sync is polling-based.** There is no websocket or server-push update. The page can be up to 30 seconds behind the automatic topology service.

## 14. Verification

The page behavior is covered by:

`figma design/tests/manual-topology-route-regressions.test.mjs`

The frontend production bundle can be verified with:

```bash
cd "figma design"
npm run build
```

