# Manual Topology Shared Builder Report

## Implementation

- SHARED BUILDER FILE: figma design/src/lib/topologyGraphBuilder.ts
- SHARED BUILDER FUNCTION: buildLogicalTopologyGraph()
- NETWORK CALL SITE: figma design/src/pages/Topology.tsx, after buildGraph() and before layoutGraph()
- MANUAL CALL SITE: figma design/src/pages/ManualTopology.tsx, before discoverPhysicalLinks()
- NETWORK USES SHARED BUILDER: YES
- MANUAL USES SHARED BUILDER: YES
- SAME EXPORTED FUNCTION: YES
- SAME INPUT CONTRACT: YES (nodes/links logical graph contract)

The shared module contains non-UI canonicalization: identity normalization, node deduplication, self-link rejection, reverse-link deduplication, stable logical IDs, and confirmed-evidence precedence. Layout and React state remain page-owned.

## Strict acceptance status

- NETWORK LOGICAL OUTPUT REGRESSION: PASS source/build; runtime fixture comparison pending
- CROSS-PAGE LOGICAL GRAPH EQUIVALENCE: FAIL — Network still performs the full buildGraph() evidence correlation before the shared canonicalizer; Manual currently receives cached logical layout data and adapts it. A full extracted buildGraph implementation is still required for true equivalence.
- MANUAL DISCOVERY DEPENDS ON topology-layout-cache-v2: YES
- MANUAL DISCOVERY WORKS WITHOUT CACHE: NO — it fails safely rather than using raw-only data
- RAW-ONLY FALLBACK: REMOVED
- MANUAL PHYSICAL ADJACENCY REIMPLEMENTATION: PARTIAL — discoverPhysicalLinks remains a post-processing adapter but still maps link adjacency
- MANUAL WORK PRESERVATION: PASS
- PARTIAL SOURCE SAFETY: PASS/PARTIAL
- SELF-LINK PROTECTION: PASS
- LINK DEDUPE: PASS
- UNKNOWN PORT: PASS
- NETWORK TOPOLOGY UI REGRESSION: NONE observed; build passed
- FRONTEND BUILD: PASS
- RUNTIME: DEFERRED TO ACTUAL HOST

## P0 remaining

Extract the complete non-UI Network Topology evidence collection and buildGraph correlation into the shared module. Then make both pages call buildLogicalTopologyGraph() directly with the same real evidence input, independent of localStorage visual cache.

## P1 remaining

- Add fixture tests comparing old/new logical graph node and link sets.
- Add cache-absent, stale-cache, partial-source, and repeated-discovery tests.
- Preserve current Network Topology output byte-for-byte at the logical graph level except documented fixes.

## Code readiness

- MANUAL TOPOLOGY CODE READY: NO
- SAFE TO MOVE TO IP SCAN: NO

## Files changed

- figma design/src/lib/topologyGraphBuilder.ts
- figma design/src/pages/Topology.tsx
- figma design/src/pages/ManualTopology.tsx
- MANUAL_TOPOLOGY_SHARED_BUILDER_REPORT.md

