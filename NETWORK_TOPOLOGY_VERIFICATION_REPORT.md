# Network Topology Verification Report

## Scope

Network Topology page only. Runtime/browser verification is deferred to the actual host. Manual Topology, its backend, discovery behavior, SNMP collectors, intervals, and OIDs were not changed.

## NETWORK_TOPOLOGY_GRAPH_PIPELINE

| Stage | File/function | Input → output | Source/filter/dedupe/confidence |
|---|---|---|---|
| Raw graph | Topology.tsx: loadTopology() | /snmp/topology response, /devices inventory, stored module APIs, optional live collection | Inventory filtering and incomplete-layout guards |
| Raw collections | collectDevice() / collectStoredDevice() | MAC/FDB, ARP, LLDP, routing, interfaces, port groups | Promise.allSettled; failed sources become empty evidence |
| Correlated graph | buildGraph() | DeviceCollection[], inventory, topology nodes/links → GraphNode[], GraphLink[] | ID/IP/MAC/exact hostname matching; addNode dedupe; LLDP/CDP confirmed, MAC/ARP inferred |
| Link normalization | normalizePersistedLink(), addLink() | raw observations → canonical UI links | reverse-pair dedupe, confirmed precedence, self-link rejection |
| Final graph | layoutGraph(mergedGraph.nodes, mergedGraph.links) | correlated graph → Layout | deterministic IDs and layout |
| Rendered graph | applyTopologyLayout() → layout state | final Layout → visible graph | incomplete responses do not replace complete cached layout |

## Findings and fixes

- Managed identity uses ID, management IP, normalized MAC, and exact normalized hostname; similar names are not fuzzy-merged.
- LLDP/CDP is the confirmed infrastructure source. MAC/ARP creates inferred port aggregate links and excludes self MACs, gateway paths, uplinks/trunks, and self-links.
- addLink() removes reverse duplicate endpoint pairs. Parallel same-pair links with different ports remain a limitation.
- Unknown remote ports previously rendered fabricated value 1; this now renders PORT UNKNOWN.
- Node status reads raw health.status when available, supporting degraded and stale states.
- No static/mock graph, hardcoded node/link arrays, or Math.random was found.
- Refresh has an in-flight guard, React Query key, no-store requests, timestamp checks, cached-layout hydration, and incomplete-response preservation.

## Required summary

- FINAL GRAPH SOURCE: layout state populated by applyTopologyLayout(layoutGraph(buildGraph(...)))
- RAW GRAPH SOURCE: loadTopology() responses and collectStoredDevice() / optional collectDevice()
- CORRELATED GRAPH SOURCE: buildGraph()
- FINAL GRAPH != RAW GRAPH: YES
- NODE CORRELATION: PASS
- NODE DEDUPLICATION: PASS/PARTIAL
- LLDP: PASS source; runtime pending
- CDP: PARTIAL
- FDB+ARP CORRELATION: PASS/PARTIAL
- FALSE-LINK PROTECTION: PASS/PARTIAL
- SELF-LINK PROTECTION: PASS
- PARALLEL LINKS: PARTIAL
- LINK DEDUPLICATION: PASS/PARTIAL
- PORT CORRELATION: PASS/PARTIAL
- DERIVED NODE HEALTH: PASS/PARTIAL
- TOPOLOGY FRESHNESS: PARTIAL
- AUTO REFRESH: PASS/PARTIAL
- MANUAL REFRESH: PASS source
- GRAPH IDENTITY STABILITY: PASS/PARTIAL
- NODE DETAILS: PASS
- LINK DETAILS: PASS
- FINAL NODE/LINK COUNTS: PASS source; runtime pending
- PARTIAL DATA HANDLING: PASS
- EMPTY/ERROR STATES: PASS/PARTIAL
- STATIC/MOCK PRODUCTION DATA: NONE
- API/PERFORMANCE: PARTIAL
- PYTHON COMPILE: PASS
- FRONTEND BUILD: PASS
- RUNTIME/BROWSER: DEFERRED TO ACTUAL HOST

## P0 Network Topology issues

- None confirmed from static inspection.

## P1 Network Topology issues

- Preserve genuinely parallel physical links by including ports in canonical identity.
- Add visible current/stale/unknown freshness metadata to topology evidence.
- Adopt derived health in remaining topology detail API paths.
- Verify final counts and refresh stability on the actual host.

## Files changed

- figma design/src/pages/Topology.tsx
- NETWORK_TOPOLOGY_VERIFICATION_REPORT.md

## Network Topology code ready

YES, with documented P1 limitations and pending runtime verification.

## Safe to move to Manual Topology

YES. Manual Topology was not modified.

