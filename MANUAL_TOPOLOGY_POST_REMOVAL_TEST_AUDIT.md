# Manual Topology Post-Removal Test Audit

Audit scope: read-only verification. No code or tests were modified.

## Conclusion

The Manual Topology route is present and correctly registered. The Network Topology removal did not alter `ManualTopology.tsx`, `DevicePortMap.tsx`, or the shared topology builder. The reported failure is a stale/brittle regression-test failure, not a Manual Topology route regression.

## Failing test and exact assertion

Test file: `figma design/tests/manual-topology-route-regressions.test.mjs`.

The route assertion is at lines 22–30:

```js
assert.match(
  routes,
  /path: ['"]manual-topology['"][\s\S]*withPermission\(ManualTopology, ['"]topology:read['"]\)/,
)
```

This assertion is **not** the failing assertion after the removal: it passes when the test module is imported directly, and the current route source contains the expected route.

The unchanged test file contains additional brittle source-text assertions. The detailed rerun identifies failures in the test cases at:

- line 72: `/DEVICES.*LINKS.*ONLINE.*ISSUES/s`; the current page source does not contain that exact sequence in active source text.
- line 194: `/endpointLabelsVisible/`; the current page source does not contain that exact identifier.

The normal Node test runner reports the file as one failing top-level module and does not print individual assertion details. Direct module execution exposed the individual subtests; 12 passed and 4 failed. The route/navigation subtest passed.

These failures are assertions about Manual Topology UI/source contracts, not route registration, and are unrelated to deleting `Topology.tsx`.

## Current route source

`figma design/src/routes.tsx` contains:

```tsx
const ManualTopology = lazyRetry(() => import("./pages/ManualTopology"))
const DevicePortMap = lazyRetry(() => import("./pages/DevicePortMap"))
```

and:

```tsx
{
  path: "manual-topology",
  Component: withPermission(ManualTopology, "topology:read"),
},
{
  path: "manual-topology/device/:deviceId/ports",
  Component: withPermission(DevicePortMap, "topology:read"),
},
```

Therefore the effective routes remain:

- `/manual-topology`
- `/manual-topology/device/:deviceId/ports`

## Component and shared-builder verification

`ManualTopology.tsx` remains imported by `routes.tsx` and imports from `../lib/topologyGraphBuilder`:

- `buildLogicalTopologyGraph`
- `collectTopologyDevice`
- `makeNode`

The same file uses them at approximately lines 1905–1907. `topologyGraphBuilder.ts` itself is unchanged and still exports all three symbols.

`DevicePortMap` remains imported and registered by `routes.tsx`; its source file is unchanged.

## Removal diff verification

The application diff from the Network Topology removal contains changes to Sidebar, keyboard shortcuts, Dashboard, routes, deletion of `Topology.tsx`, and test cleanup. There are no changes to:

- `figma design/src/pages/ManualTopology.tsx`
- `figma design/src/pages/DevicePortMap.tsx`
- `figma design/src/lib/topologyGraphBuilder.ts`
- any backend file

The only `routes.tsx` diff removes the obsolete `Topology` lazy import and `/topology` route. The Manual Topology and Port Map route blocks are unchanged.

## Rerun result

Command:

```bash
cd "figma design"
node --test tests/manual-topology-route-regressions.test.mjs
```

Result: file-level **FAIL**. Direct module execution shows 12 passing subtests and 4 failing brittle UI/source assertions; the route assertion passes.

## Smallest proposed correction (not implemented)

Do not change application routing. Update only the stale test expectations to assert the current active Manual Topology contract, preferably using stable route/source markers rather than exact historical UI text or identifiers. At minimum, replace/remove the obsolete expectations for the `DEVICES...LINKS...ONLINE...ISSUES` sequence and `endpointLabelsVisible` after confirming the intended current UI contract.

No test correction was implemented in this audit.

## Final status

```text
MANUAL TOPOLOGY ROUTE PRESENT: YES
PORT MAP ROUTE PRESENT: YES
MANUAL TOPOLOGY COMPONENT IMPORTED: YES
SHARED BUILDER STILL USED: YES
NETWORK TOPOLOGY REMOVAL BROKE ROUTE: NO
FAILURE TYPE: STALE TEST
APPLICATION CODE FIX REQUIRED: NO
TEST FIX REQUIRED: YES (proposed only; not implemented)
CODE CHANGED: NO
```
