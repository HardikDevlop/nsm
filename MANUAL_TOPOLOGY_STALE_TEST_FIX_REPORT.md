# Manual Topology Stale Test Fix Report

Only `figma design/tests/manual-topology-route-regressions.test.mjs` was edited for the test fix. No application or backend code was changed.

## Four stale assertion groups

1. Enterprise header/persistent panels

   - Old: `/DEVICES.*LINKS.*ONLINE.*ISSUES/s` and `/ON CANVAS.*AVAILABLE.*MANUAL/s`.
   - Reason stale: the current editor exposes live workspace counts and view state through source expressions rather than that historical text ordering.
   - New: assertions for `workspace.devices.length`, `workspace.links.length`, `changes.length`, and `view === "actual"`.
   - Coverage retained: device/link/issue counts and automatic-view state remain required.

2. Device Port Map loading/classification

   - Old: `/NO PHYSICAL PORTS DISCOVERED/`.
   - Reason stale: the current Port Map uses active physical-port/uplink rendering and loading/error states; that exact empty-state label is no longer present.
   - New: `/PHYSICAL PORTS|SFP \/ HIGH-SPEED UPLINK BAY/`.
   - Coverage retained: the test still verifies real physical-port presentation while retaining loading, retry, logical/management classification, and zoom assertions.

3. Production viewport controls

   - Old: `/SHOW PORTS/` and an exact `onDoubleClick` handler shape.
   - Reason stale: the current implementation uses `fitToView` and direct `focusDevice(device)` behavior; the old label/formatting contract is absent.
   - New: `/fitToView/` and `/focusDevice\(device\)/`.
   - Coverage retained: viewport persistence, zoom bounds, keyboard controls, and device focusing remain checked.

4. Deterministic port sockets/endpoint inspection

   - Old: `/endpointLabelsVisible/` and exact `cx={endpoints.source.x}` / `cx={endpoints.target.x}` source forms.
   - Reason stale: the current implementation uses hover/selection state and endpoint exit coordinates in the link geometry; those historical identifier/markup forms are gone.
   - New: `/setHoveredLinkId/` and endpoint-coordinate expressions allowing the current `.exit` form.
   - Coverage retained: link endpoint calculation, hover/selection, source/target labels, delete/view actions, and encoded port navigation remain covered.

The route assertions for `manual-topology`, `manual-topology/device/:deviceId/ports`, and `topology:read` were left unchanged.

## Validation

- Manual Topology regression test: **PASS**
- Shared topology graph test: **PASS**
- Device identity regression test: **PASS**
- Frontend build: **PASS** (`npm run build`)
- Backend diff: none
- Runtime/browser verification: **NOT RUN**

## Final status

```text
STALE ASSERTIONS IDENTIFIED: 4/4
APPLICATION CODE CHANGED: NO
MANUAL TOPOLOGY ROUTE TEST: PASS
PORT MAP ROUTE TEST: PASS
MANUAL TOPOLOGY REGRESSION TEST: PASS
SHARED TOPOLOGY TEST: PASS
DEVICE IDENTITY TEST: PASS
FRONTEND BUILD: PASS
TEST FILE ONLY CHANGED: YES (application/test-fix scope)
RUNTIME VERIFIED: NO
```
