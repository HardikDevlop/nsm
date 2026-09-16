# Topology Extraction Chunk 1 Report

DeviceType moved: YES
DeviceStatus moved: YES
GraphNode moved: YES
GraphLink moved: YES
DeviceCollection moved: YES
str moved: YES
lower moved: YES
cleanMac moved: YES
isMac moved: YES
displayMac moved: YES
unique moved: YES
portKey moved: YES

DUPLICATE DEFINITIONS REMAIN: NO
buildGraph changed: NO
Topology behavior intentionally changed: NO
ManualTopology changed: NO
CIRCULAR IMPORT: NO
FRONTEND BUILD: PASS

FILES CHANGED:

- `figma design/src/lib/topologyGraphBuilder.ts`
- `figma design/src/pages/Topology.tsx`
- `TOPOLOGY_EXTRACTION_CHUNK1_REPORT.md`

All requested Chunk 1 types and pure helpers now have one authoritative shared implementation. `DeviceRecord` remains sourced from `../lib/api`. Chunk 2 and all correlation extraction were not started.
