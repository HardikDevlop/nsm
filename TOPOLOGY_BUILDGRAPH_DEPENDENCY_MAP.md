# Topology `buildGraph()` Dependency Map

## 1. Location

The authoritative function is in `figma design/src/pages/Topology.tsx`, lines **396–734** (inclusive; 339 lines). `groupMacEntries()` follows it at lines 736–754 and is called by `buildGraph()`.

## 2. Signature

```ts
function buildGraph(
  collections: DeviceCollection[],
  inventory: DeviceRecord[],
  topologyNodes: any[],
  topologyLinks: any[],
): { nodes: GraphNode[]; links: GraphLink[] }
```

Parameters are `DeviceCollection[]`, `DeviceRecord[]`, persisted/raw topology node rows (`any[]`), and persisted/raw topology link rows (`any[]`). The return value is the correlated logical graph `{ nodes: GraphNode[]; links: GraphLink[] }`.

## 3. External variables read

No mutable React, DOM, storage, or API variables are read directly. The function reads only its four parameters and module-scope types/helpers/constants listed below. `byId`, `nodes`, `links`, and `linkPairs` are local variables.

## 4. Helper dependency classification

| Helper | Classification | Use |
|---|---|---|
| `findByIdentity` | PURE / TOPOLOGY-CORRELATION | ID, IP, MAC, hostname node matching |
| `cleanMac` | DATA-NORMALIZATION | MAC canonicalization |
| `lower` | DATA-NORMALIZATION | case-insensitive matching |
| `str` | DATA-NORMALIZATION | first non-empty field selection |
| `makeNode` | TOPOLOGY-CORRELATION / DATA-NORMALIZATION | node creation and field normalization |
| `classifyDevice` | DATA-NORMALIZATION | device type classification |
| `statusOf` | DATA-NORMALIZATION | status normalization |
| `displayMac` | DATA-NORMALIZATION | display MAC formatting |
| `inventoryMatch` | TOPOLOGY-CORRELATION | persisted row to inventory matching |
| `normalizeLldp` | DATA-NORMALIZATION / TOPOLOGY-CORRELATION | LLDP/CDP evidence normalization |
| `portKey` | DATA-NORMALIZATION | interface/port matching |
| `unique` | PURE | array dedupe |
| `isMac` | DATA-NORMALIZATION | MAC validation |
| `isAgnigateMac` | DATA-NORMALIZATION | special MAC labeling |
| `agnigateLabel` | DATA-NORMALIZATION | special node label |
| `groupMacEntries` | TOPOLOGY-CORRELATION | FDB/MAC rows grouped by port |

`addNode`, `addSyntheticNode`, `addLink`, `managedFor`, and `remoteFor` are nested helpers and therefore part of the function's extraction, not external dependencies. `addSyntheticNode` is currently defined but not called in the shown implementation.

## 5. Type dependencies

Direct type dependencies are `DeviceCollection`, `DeviceRecord`, `GraphNode`, and `GraphLink`. `DeviceType` and `DeviceStatus` are embedded through those types and their helper signatures. `ReturnType<typeof normalizeLldp>` is used by nested `remoteFor`. `Layout` is not used by `buildGraph()`.

## 6. Constant dependencies

No module constant is read by the body. String literals encode the source/confidence values (`LLDP/CDP`, `MAC/ARP`, `CONFIRMED`, `INFERRED`) and synthetic ID prefixes (`inventory-`, `managed-`, `topology-`, `neighbor-`, `port-`, `lldp-`, `verified-`). `CLOSED_PORT_STATES` and layout constants are not dependencies of `buildGraph()`.

## 7. Evidence structures consumed

- `collections`: managed device plus `interfaces`, `lldpNeighbors`/CDP, `macEntries`/FDB, `portGroups`, and `arpEntries`.
- `inventory`: managed device identity and authoritative device fields.
- `topologyNodes`: persisted topology nodes, excluding persisted `port-*` aggregates.
- `topologyLinks`: verified persisted LLDP/CDP links used as fallback.
- Routing: present in `DeviceCollection.routes`, but not read by the current `buildGraph()` body.
- Direct persisted topology processing: node normalization and verified LLDP/CDP link fallback.

## 8. Responsibility map

- Device correlation: `findByIdentity`, `inventoryMatch`, `addNode`, `remoteFor`.
- LLDP/CDP peer correlation: `normalizeLldp`, `remoteFor`, and the first `collections.forEach` link loop (lines 539–568).
- FDB + ARP correlation: `arpByMac`, `groupMacEntries`, and the port-group loop (lines 594–731).
- Port correlation: `portKey`, `groupsByPort`, interface lookup, and endpoint matching by learned MAC/IP.
- Node creation: `makeNode`, nested `addNode`, nested `addSyntheticNode`, and port endpoint construction.
- Link creation: nested `addLink`, LLDP/CDP loop, verified persisted-link loop, and MAC/ARP port loop.
- Link dedupe: nested `addLink`, keyed by sorted endpoint pair.
- Evidence/confidence precedence: nested `addLink`; LLDP/CDP is `CONFIRMED`, MAC/ARP is `INFERRED`, and confirmed links replace inferred links while preserving useful ports/counts.

## 9. UI/API dependency check

`buildGraph()` directly uses none of `setState`, `useState`, `useEffect`, React refs, DOM, `layoutGraph`, `localStorage`, or `sessionStorage`. API/data fetching is outside the function; `collectDevice` and `collectStoredDevice` prepare its `DeviceCollection` inputs.

## 10. Minimum safe extraction order

**Chunk 1:** Move/export `DeviceType`, `DeviceStatus`, `GraphNode`, `GraphLink`, and `DeviceCollection`; add `DeviceRecord` as a type import. Move pure primitives `str`, `lower`, `cleanMac`, `isMac`, `displayMac`, `unique`, and `portKey`.

**Chunk 2:** Move `classifyDevice`, `statusOf`, `makeNode`, `inventoryMatch`, `findByIdentity`, `normalizeLldp`, and `groupMacEntries`.

**Chunk 3:** Move nested node/link state (`nodes`, `byId`, `links`, `linkPairs`) and `addNode`/`addLink`; preserve exact dedupe and precedence behavior.

**Chunk 4:** Move persisted node/link seeding and `remoteFor`, then the LLDP/CDP correlation loop.

**Chunk 5:** Move `arpByMac` and the complete FDB/ARP port-group loop, including interface/port correlation and endpoint updates.

**Chunk 6:** Change Network to call the shared function with the same four evidence arguments, delete the page-local implementation, and run the build plus focused graph fixtures.

## Final status

BUILDGRAPH LOCATION: `figma design/src/pages/Topology.tsx:396–734`

BUILDGRAPH SIZE: 339 lines (plus external helper `groupMacEntries`: 19 lines)

DIRECT DEPENDENCIES: 20 (16 module helpers/constants/functions identified above, 4 input/type dependencies counted as data/type contracts)

PURE/NON-UI DEPENDENCIES: 20

REACT/UI DEPENDENCIES: 0

CAN buildGraph BE MOVED WITHOUT UI LOGIC: YES

BLOCKING DEPENDENCIES: `DeviceRecord` import/type contract; `GraphNode`, `GraphLink`, and `DeviceCollection` visibility; `groupMacEntries`; `agnigateLabel`/`isAgnigateMac` imports; exact preservation of nested `addNode`/`addLink` closure behavior.

SAFEST FIRST EXTRACTION CHUNK: `DeviceType`, `DeviceStatus`, `GraphNode`, `GraphLink`, `DeviceCollection`, `str`, `lower`, `cleanMac`, `isMac`, `displayMac`, `unique`, and `portKey`.

CODE CHANGES: NONE
