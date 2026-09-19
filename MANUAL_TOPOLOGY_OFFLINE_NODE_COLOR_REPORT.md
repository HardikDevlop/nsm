# Manual Topology Offline Node Color Report

Implemented the offline visual overlay in `figma design/src/pages/ManualTopology.tsx`.

## Behavior

- Managed `offline` health now uses `renderedToneFor(device)` to render the node border and device illustration in the semantic offline red `#d9646a`.
- The status dot remains red through the existing authoritative health mapping.
- Online recovery automatically returns to `device.tone`, the configured/manual color, with a green status dot.
- `degraded` remains amber only in the indicator; `stale` and `unknown` remain neutral. They do not make the node red.
- Unmanaged nodes have no backend ID, remain `Unknown`, and retain their configured tone.
- The runtime overlay does not mutate `device.tone`, workspace state, or topology snapshots.

## Palette safety

The existing Manual Topology palette contained `#d9646a`; that option was removed. Other palette colors remain unchanged. Existing saved nodes with a red `tone` remain load-compatible because saved values are not migrated or rewritten.

## Preserved behavior

- Existing authoritative `GET /overview` health polling remains unchanged at 10 seconds.
- No alert code, backend health authority, topology builder, reconciliation, Port Map, or snapshot persistence was changed.
- No frontend alert or snapshot mutation was introduced.

## Tests and build

- Manual Topology regression tests: **PASS**
- Shared topology graph test: **PASS**
- Device identity regression test: **PASS**
- Frontend build: **PASS**
- Runtime/browser verification: **NOT RUN**

## Final status

```text
RED REMOVED FROM MANUAL COLOR OPTIONS: PASS
ONLINE USES CONFIGURED COLOR: PASS
OFFLINE NODE RED: PASS
OFFLINE DOT RED: PASS
OFFLINE HOVER STATUS: PASS
RECOVERY RESTORES ORIGINAL COLOR: PASS (rendering path; browser runtime not verified)
DEGRADED/STALE/UNKNOWN AVOID RED: PASS
SNAPSHOT MUTATED BY HEALTH: NO
ALERT PIPELINE CHANGED: NO
BACKEND CHANGED: NO
RUNTIME VERIFIED: NO
```
