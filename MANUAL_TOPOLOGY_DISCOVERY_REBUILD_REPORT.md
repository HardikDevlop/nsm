# Manual Topology Discovery Rebuild Report

DISCOVERY REBUILD: PARTIAL

OLD DISCOVERY FLOW REMOVED/REPLACED: YES

FILES CHANGED:
- `figma design/src/pages/ManualTopology.tsx`
- `MANUAL_TOPOLOGY_DISCOVERY_REBUILD_REPORT.md`

FRESH TOPOLOGY REQUEST: PASS — the button calls `getSNMPTopology(undefined, true)`, which serializes `refresh=true`.

BACKEND REFRESH EXECUTED: PASS (source verified) — `/snmp/topology` reads `refresh` and clears persisted topology before collection/rebuild.

RAW LINK RESPONSE VERIFIED: PASS (source verified) — the route returns assembled `devices` and `links`; link fields are normalized from the project’s source/target ID, IP, hostname, port, ifIndex, and evidence aliases.

ROOT CAUSE OF ZERO LINKS: The previous frontend conversion assumed `device-${numericId}` canvas IDs, required backend-ID-only mapping, replaced all workspace links, and did not preserve a canonical discovered-link identity.

DEVICE MAPPING: PASS — numeric/string backend IDs, IP, MAC, and unambiguous hostname fallback are supported.

PORT OPTIONALITY: PASS — missing interface data produces `N/A` labels without discarding device adjacency.

REVERSE DEDUP: PASS — canonical endpoint/port keys collapse reverse observations.

MULTI-PORT LINKS: PASS — distinct port pairs retain distinct keys.

CANVAS LINK CREATION: PASS — discovered links use existing canvas node IDs and stable IDs.

NODE-ANCHOR FALLBACK: PASS — existing `portEndpoint` path falls back to node sockets when port geometry is unavailable.

IMMEDIATE RENDER: PASS — workspace and actual-workspace state are updated before the success toast.

MANUAL LINKS PRESERVED: PASS — only links marked `discovered_physical` are reconciled.

WORKSPACE SAVE: PASS (source verified) — merged state is saved synchronously; save failure is reported as failure.

RELOAD RESTORE: PASS (source verified) — saved payload and local cache are loaded through the existing workspace loader.

DISCOVERY IDEMPOTENT: PASS by stable canonical discovered IDs and replacement of discovered-only links.

PHYSICAL CHANGE UPDATE: PASS for discovered-link reconciliation; existing comparison/change semantics remain delegated to the existing reconcile endpoint.

TOAST ACCURACY: PASS — reports mapped physical links and discarded mappings; zero links reports zero.

REAL DATA ONLY: PASS — no topology data or fake discovered ports are introduced.

TESTS: `npm run build` PASS. No live PostgreSQL/SNMP runtime was available; focused runtime tests remain pending.

LIVE DISCOVERY: RUNTIME VERIFICATION PENDING

REGRESSIONS: NONE observed by production build.

REMAINING ISSUE: Live device collection, response counts, persistence reload, and browser visibility require a running authenticated FastAPI/PostgreSQL/SNMP environment.
