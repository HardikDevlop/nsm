# Manual Topology Shared Pipeline Final Report

## Scope

Step 8C only. No backend, collector, OID, scheduler, interval, topology layout, or port-map changes were made.

## Current pipeline

- SHARED EVIDENCE SERVICE: Not extracted; current page-local collection remains in Topology.tsx.
- SHARED LOGICAL BUILDER: figma design/src/lib/topologyGraphBuilder.ts:buildLogicalTopologyGraph()
- NETWORK PIPELINE: loadTopology() → page-local collectStoredDevice/collectDevice → buildGraph() → buildLogicalTopologyGraph() → layoutGraph() → applyTopologyLayout()
- MANUAL PIPELINE: runPhysicalDiscovery() → fresh getSNMPTopology() response → buildLogicalTopologyGraph() → discoverPhysicalLinks() → manual reconciliation/layout

## Required summary

- Topology.tsx FULL buildGraph REMAINING: YES
- NETWORK PERFORMS CORRELATION BEFORE SHARED BUILDER: YES
- MANUAL DEPENDS ON topology-layout-cache-v2: NO for discovery authority
- MANUAL WORKS WITH CACHE ABSENT: YES at source level
- MANUAL USES RAW-ONLY FALLBACK: NO — raw response passes through shared builder, though full evidence parity is incomplete
- MANUAL ADAPTER INFERS PHYSICAL LINKS: YES/PARTIAL
- SAME RAW EVIDENCE CONTRACT: NO
- SAME EXPORTED LOGICAL BUILDER: YES
- CROSS-PAGE NODE SET: FAIL
- CROSS-PAGE LINK SET: FAIL
- CROSS-PAGE PORTS: FAIL
- CROSS-PAGE EVIDENCE: FAIL
- CROSS-PAGE CONFIDENCE: FAIL
- NETWORK LOGICAL REGRESSION: PENDING
- CACHE-ABSENT TEST: PASS source-level
- STALE-CACHE TEST: PASS source-level
- LLDP-MISSING PARTIAL SOURCE: PENDING
- FDB-MISSING PARTIAL SOURCE: PENDING
- DISCOVERY FAILURE PRESERVES MANUAL WORK: PASS source-level
- SELF-LINK: PASS
- REVERSE DEDUPE: PASS
- UNKNOWN PORT: PASS
- FRONTEND BUILD: PASS
- RUNTIME: DEFERRED TO ACTUAL HOST

## P0 remaining

The complete Network Topology buildGraph correlation and evidence collection have not been moved into the shared module. Manual and Network do not yet consume one identical raw evidence contract, so cross-page logical equivalence is not proven.

## P1 remaining

- Extract the minimum reusable evidence collection service.
- Move full buildGraph correlation rules into buildLogicalTopologyGraph().
- Reduce discoverPhysicalLinks() to identity/port/UI adaptation only.
- Add fixture tests for equivalence, partial sources, cache behavior, and Network regression.

## Files changed

- figma design/src/lib/topologyGraphBuilder.ts
- figma design/src/pages/Topology.tsx
- figma design/src/pages/ManualTopology.tsx
- MANUAL_TOPOLOGY_SHARED_PIPELINE_FINAL_REPORT.md

## Hard acceptance

- MANUAL TOPOLOGY CODE READY: NO
- SAFE TO MOVE TO IP SCAN: NO

