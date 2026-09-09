import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const page = await readFile(new URL('../src/pages/Topology.tsx', import.meta.url), 'utf8')

test('topology does not overwrite a live refresh with the same cached inventory', () => {
  assert.match(page, /const topologyQueryKey = \['snmp-topology'\] as const/)
  assert.match(page, /queryClient\.fetchQuery\(/)
  assert.match(page, /staleTime: 0/)
  assert.match(page, /const liveLayoutRef = useRef<Layout \| null>\(null\)/)
  assert.match(page, /const liveInventoryKeyRef = useRef\(''\)/)
  assert.match(page, /topologyResult\?\.cached === true/)
  assert.match(page, /liveInventoryKeyRef\.current === inventoryKey/)
  assert.match(page, /const liveTopologyEvidence = liveCollections\.some\(/)
  assert.match(page, /if \(forceRefresh && liveTopologyEvidence && root && Number\.isFinite\(Number\(root\.id\)\)\)/)
  assert.match(page, /persistSNMPTopologySnapshot\(Number\(root\.id\)/)
  assert.match(page, /const collectedAt = new Date\(\)\.toISOString\(\)/)
  assert.match(page, /source: 'live_refresh'/)
  assert.match(page, /refresh=true&requested_at=\$\{Date\.now\(\)\}/)
  assert.match(page, /queryClient\.setQueryData\(topologyQueryKey, latestSnapshot\)/)
  assert.match(page, /route-remount layout hydration/)
  assert.doesNotMatch(page, /queryClient\.invalidateQueries\(\{ queryKey: topologyQueryKey, refetchType: 'none' \}\)/)
})

test('normal topology navigation reuses the cached graph briefly', () => {
  assert.match(page, /staleTime: 0/)
  assert.match(page, /queryFn: \(\) => requestJson<any>\(requestUrl, \{ cache: 'no-store' \}\)/)
  assert.match(page, /completed layout stays visible/)
  assert.match(page, /requestJson<DeviceRecord\[]>\('\/devices', \{ cache: 'no-store' \}\)/)
})

test('topology keeps a remount-safe response cache outside the route component', () => {
  assert.match(page, /let topologyResponseCache: any = readTopologySnapshot\(\)/)
  assert.match(page, /let topologyLayoutCache: Layout \| null = readTopologyLayoutCache\(\)/)
  assert.match(page, /useState<Layout \| null>\(topologyLayoutCache\)/)
  assert.match(page, /useRef\(topologyLayoutCache !== null\)/)
  assert.match(page, /if \(Array\.isArray\(topologyResult\?\.devices\) && Array\.isArray\(topologyResult\?\.links\)\)/)
  assert.match(page, /topology-layout-cache-v1/)
  assert.match(page, /snmp-topology-layout/)
  assert.match(page, /queryClient\.setQueryData\(TOPOLOGY_LAYOUT_QUERY_KEY, preservedLayout\)/)
  assert.match(page, /route-remount layout hydration/)
  assert.match(page, /function readTopologyLayoutCache\(\): Layout \| null/)
  assert.match(page, /function writeTopologyLayoutCache\(layout: Layout\)/)
  assert.match(page, /writeTopologyLayoutCache\(preservedLayout\)/)
  assert.match(page, /const isCompleteTopologyLayout = \(layout: Layout \| null \| undefined\)/)
  assert.match(page, /incomplete layout ignored/)
  assert.match(page, /void loadTopology\(false\)/)
})

test('topology never leaves an indefinite loading overlay', () => {
  assert.doesNotMatch(page, /Loading topology[.…]/)
  assert.match(page, /No saved topology snapshot available\. Use REFRESH to collect one\./)
  assert.match(page, /!visible\.nodes\.length && !loading && !refreshing/)
})

test('topology restores the last complete snapshot after a browser reload', () => {
  assert.match(page, /topology-last-snapshot-v1/)
  assert.match(page, /window\.localStorage\.getItem\(TOPOLOGY_LAST_SNAPSHOT_KEY\)/)
  assert.match(page, /window\.localStorage\.setItem\(TOPOLOGY_LAST_SNAPSHOT_KEY, JSON\.stringify\(topologyResult\)\)/)
})

test('topology uses persisted device inventory without ICMP visibility loss', () => {
  assert.match(page, /const storedInventoryResult = Array\.isArray\(inventoryResult\) \? inventoryResult : \[\]/)
  assert.match(page, /device table is the authoritative source for topology visibility/)
  assert.match(page, /const inventory = storedInventory\.filter\(device => device\.status !== 'offline'\)/)
  assert.doesNotMatch(page, /const health = await pingIps\(/)
  assert.match(page, /const allCollections = forceRefresh && liveTopologyEvidence \? liveCollections : currentStoredCollections/)
  assert.match(page, /responseTimestamp < topologyTimestampRef\.current/)
  assert.match(page, /Do not abort here/)
  assert.doesNotMatch(page, /sessionStorage\.setItem\(CACHE_KEY/)
})

test('empty device inventory clears stale topology snapshots', () => {
  assert.match(page, /if \(storedInventory\.length === 0\)/)
  assert.match(page, /topologyLayoutCache = null/)
  assert.match(page, /topologyResponseCache = null/)
  assert.match(page, /queryClient\.removeQueries\(\{ queryKey: topologyQueryKey \}\)/)
  assert.match(page, /window\.localStorage\.removeItem\(TOPOLOGY_LAST_SNAPSHOT_KEY\)/)
  assert.match(page, /window\.localStorage\.removeItem\(TOPOLOGY_LAYOUT_CACHE_KEY\)/)
  assert.match(page, /applyTopologyLayout\(emptyLayout, 'empty inventory',[\s\S]*true, true\)/)
})

test('normal topology builds the final graph from inventory and DB-backed port data', () => {
  assert.match(page, /function normalizeGraphNode\(raw: any, fallbackId: string\): GraphNode/)
  assert.match(page, /type: node\.type \|\| 'unknown'/)
  assert.doesNotMatch(page, /applyTopologyLayout\(persistedLayout, 'persisted topology hydration'/)
  assert.match(page, /const currentMac = await collectModule\(Number\(root\.id\), 'mac', true\)/)
})

test('persisted topology uses a dynamic switch root and port groups', () => {
  assert.match(page, /const root = nodes\s+\.filter\(node => node\.type === 'switch'\)/)
  assert.match(page, /\.sort\(\(a, b\) => degree\(b\) - degree\(a\)\)\[0\]/)
  assert.match(page, /const groups = new Map<string, string\[\]>/)
  assert.match(page, /const port = link\.from === root\.id \? link\.localPort : link\.remotePort/)
  assert.match(page, /return \{ nodes, links, positions, width, height: maxY, rootId: root\.id \}/)
  assert.match(page, /const rootPort = layout\.rootId && link\.from === layout\.rootId \? link\.localPort : layout\.rootId && link\.to === layout\.rootId \? link\.remotePort : link\.localPort/)
})

test('live topology updates merge into the persisted port-based baseline', () => {
  assert.match(page, /function mergeTopologyGraph\(base: Layout \| null, delta: \{ nodes: GraphNode\[\]; links: GraphLink\[\] \}\)/)
  assert.match(page, /const topologyGraphRef = useRef<Layout \| null>\(null\)/)
  assert.match(page, /topologyGraphRef\.current = next/)
  assert.match(page, /const mergedGraph = forceRefresh\s+\? mergeTopologyGraph\(topologyGraphRef\.current, result\)/)
  assert.match(page, /devices: mergedGraph\.nodes,\s+links: mergedGraph\.links/)
  assert.match(page, /const existingIndex = links\.findIndex\(link =>/)
  assert.match(page, /if \(existingIndex >= 0\) \{[\s\S]*links\[existingIndex\][\s\S]*else links\.push\(merged\)/)
  assert.match(page, /candidate\.ips \|\| \[\]\)\.some\(ip =>/)
  assert.match(page, /candidate\.macs \|\| \[\]\)\.some\(mac =>/)
  assert.match(page, /const links = base\.links\.filter\(link => !removedSummaryIds\.has\(link\.from\) && !removedSummaryIds\.has\(link\.to\)\)\.map\(link => \(\{ \.\.\.link \}\)\)/)
  assert.match(page, /else links\.push\(merged\)/)
  assert.match(page, /const nextLayout = layoutGraph\(mergedGraph\.nodes, mergedGraph\.links\)/)
})

test('refresh merge preserves confirmed links when MAC/ARP repeats the same pair', () => {
  assert.match(page, /const candidateIsMacEvidence = candidate\.source === 'MAC\/ARP'/)
  assert.match(page, /const existingIsConfirmed = existing\.confidence === 'CONFIRMED'/)
  assert.match(page, /existingIsConfirmed && candidateIsMacEvidence/)
  assert.match(page, /localPort: candidate\.localPort \|\| existing\.localPort/)
  assert.match(page, /macCount: candidate\.macCount \|\| existing\.macCount/)
})

test('incremental refresh preserves baseline on empty or stale collector data', () => {
  assert.match(page, /const mergedGraph = forceRefresh\s+\? mergeTopologyGraph\(topologyGraphRef\.current, result\)/)
  assert.match(page, /if \(!forceRefresh && responseTimestamp && topologyTimestampRef\.current && responseTimestamp < topologyTimestampRef\.current\)/)
  assert.match(page, /persistSNMPTopologySnapshot\(Number\(root\.id\), \{[\s\S]*devices: mergedGraph\.nodes,[\s\S]*links: mergedGraph\.links/)
})

test('topology render shows nodes connected by active graph links', () => {
  assert.match(page, /const CLOSED_PORT_STATES = \['down', 'closed', 'disabled', 'inactive', 'err-disabled', 'failed', 'offline'\]/)
  assert.match(page, /link\.status,[\s\S]*\(link as any\)\.oper_status/)
  assert.match(page, /return !status \|\| !CLOSED_PORT_STATES\.some\(state => status === state \|\| status\.includes\(state\)\)/)
  assert.match(page, /const openLinks = layout\.links\.filter\(isRenderableConnectedLink\)/)
  assert.match(page, /const connectedIds = new Set\(\[\.\.\.\(core \? \[core\.id\] : \[\]\), \.\.\.openLinks\.flatMap\(link => \[link\.from, link\.to\]\)\]\.map\(String\)\)/)
  assert.match(page, /\.filter\(node => connectedIds\.has\(String\(node\.id\)\)\)/)
  assert.match(page, /openLinks\.filter\(link => ids\.has\(String\(link\.from\)\) && ids\.has\(String\(link\.to\)\)\)/)
})

test('network topology graph renders the complete discovered topology', () => {
  assert.match(page, /function findCoreNode\(nodes: GraphNode\[\], links: GraphLink\[\]\): GraphNode \| undefined/)
  assert.match(page, /const switches = candidates\.length \? candidates : nodes\.filter\(node => node\.type === 'switch'\)/)
  assert.match(page, /degree\(right\) - degree\(left\) \|\| Number\(Boolean\(right\.ip\)\) - Number\(Boolean\(left\.ip\)\)/)
  assert.match(page, /const core = findCoreNode\(layout\.nodes, layout\.links\)/)
  assert.match(page, /The graph view must show the complete discovered topology/)
  assert.match(page, /const isRenderableConnectedLink = \(link: GraphLink\)/)
  assert.match(page, /link\.source === 'MAC\/ARP' \? !link\.gatewayPath : isOpenPortLink\(link\)/)
  assert.match(page, /link\.source !== 'MAC\/ARP' \|\| link\.gatewayPath \|\| !isRenderableConnectedLink\(link\)/)
  assert.match(page, /const openLinks = layout\.links\.filter\(isRenderableConnectedLink\)/)
  assert.match(page, /const connectedIds = new Set\(\[\.\.\.\(core \? \[core\.id\] : \[\]\), \.\.\.openLinks\.flatMap\(link => \[link\.from, link\.to\]\)\]\.map\(String\)\)/)
})

test('topology keeps endpoint groups and gives aggregate groups an IP/MAC identity', () => {
  assert.match(page, /const classification = lower\(group\.classification, group\.class, group\.port_type\)/)
  assert.match(page, /classification\.includes\('uplink'\) \|\| classification\.includes\('trunk'\)/)
  assert.doesNotMatch(page, /lldpPortByDevice\.get\(parent\.id\)/)
  assert.match(page, /item\.portGroups,[\s\S]*groupMacEntries\(item\.macEntries\.filter\(/)
  assert.match(page, /const groupsByPort = new Map<string, any>\(\)/)
  assert.match(page, /existing\.macs = unique\(/)
  assert.match(page, /\.sort\(\(left, right\) =>[\s\S]*ipSortKey\(left\)/)
})

test('topology represents dynamic multi-MAC ports and hides the local self MAC', () => {
  assert.doesNotMatch(page, /hostname: `\$\{parent\.hostname\} · Port \$\{port\} · \$\{groupMacs\.length\} MACs`/)
  assert.match(page, /const isSelfMac = Boolean\(parentMac\) && groupMacs\.some\(mac => cleanMac\(mac\) === parentMac\)/)
  assert.match(page, /The switch's own FDB entry is not a connected endpoint/)
  assert.match(page, /if \(isSelfMac\) return/)
  assert.match(page, /const endpoint = correlatedEndpoint \|\| addNode\(endpointCandidate\)/)
  assert.match(page, /hostname: resolvedIp \|\| groupMacs\[0\]/)
  assert.match(page, /const canonicalNodes: GraphNode\[\] = \[\]/)
  assert.match(page, /const uniqueLinks = new Map<string, GraphLink>\(\)/)
})

test('topology rejects self-reported LLDP neighbors and preserves managed MAC identity', () => {
  assert.match(page, /The DB inventory is authoritative for a managed device identity/)
  assert.match(page, /const sameIp = Boolean\(lldp\.remoteIp && local\.ip && lldp\.remoteIp === local\.ip\)/)
  assert.match(page, /const sameMac = Boolean\(lldp\.remoteMac && local\.mac && cleanMac\(lldp\.remoteMac\) === cleanMac\(local\.mac\)\)/)
  assert.match(page, /const sameHostname = Boolean\(lldp\.remoteHostname && local\.hostname && lower\(lldp\.remoteHostname\) === lower\(local\.hostname\)\)/)
  assert.match(page, /if \(sameIp \|\| sameMac \|\| sameHostname\) return/)
})

test('cached topology is enriched from current database-backed collections', () => {
  assert.match(page, /const allCollections = forceRefresh && liveTopologyEvidence \? liveCollections : currentStoredCollections/)
  assert.match(page, /const currentMac = await collectModule\(Number\(root\.id\), 'mac', true\)/)
  assert.match(page, /const corePortGroups = unwrapRows\(currentMac, \['port_groups'\]\)/)
  assert.match(page, /Keep the topology snapshot as the infrastructure baseline/)
  assert.doesNotMatch(page, /topologyResult\?\.cached === true && \(topologyLinks\.length > 0 \|\| topologyNodes\.length > 0\)\n          \? \[\]\n          : storedCollections/)
})

test('topology normalizes persisted numeric and string endpoint IDs', () => {
  assert.match(page, /flatMap\(link => \[link\.from, link\.to\]\)/)
  assert.match(page, /connectedIds\.has\(String\(node\.id\)\)/)
  assert.match(page, /const graphNodes = openLinks\.length\s+\? layout\.nodes\.filter\(node => connectedIds\.has\(String\(node\.id\)\)\)\s+: layout\.nodes/)
  assert.match(page, /ids\.has\(String\(link\.from\)\) && ids\.has\(String\(link\.to\)\)/)
})

test('topology normalizes backend source_node and target_node link fields', () => {
  assert.match(page, /function normalizePersistedLink\(raw: any, index: number\): GraphLink \| null/)
  assert.match(page, /raw\?\.from, raw\?\.source_node, raw\?\.source, raw\?\.source_id/)
  assert.match(page, /raw\?\.to, raw\?\.target_node, raw\?\.target, raw\?\.target_id/)
  assert.match(page, /value\.links\.map\(normalizePersistedLink\)\.filter\(Boolean\)/)
})

test('topology renders one edge per device pair and prefers confirmed evidence', () => {
  assert.match(page, /LLDP\/CDP and MAC\/ARP can describe the same device pair/)
  assert.match(page, /const key = \[String\(link\.from\), String\(link\.to\)\]\.sort\(\)\.join\('\|'\)/)
  assert.match(page, /existing\.confidence !== 'CONFIRMED' && link\.confidence === 'CONFIRMED'/)
})

test('MAC/ARP edge labels use the switch-side port', () => {
  assert.match(page, /link\.source === 'MAC\/ARP'[\s\S]*link\.localPort \|\| link\.remotePort/)
})

test('port summary wins over neighbor-side LLDP port metadata', () => {
  assert.match(page, /Port Summary is authoritative for the monitored switch-side port/)
  assert.match(page, /localPort: link\.localPort/)
  assert.match(page, /localPort: existing\.localPort \|\| link\.localPort/)
})

test('core switch connections show only active connected device ports', () => {
  assert.match(page, /link\.source !== 'MAC\/ARP' \|\| link\.gatewayPath \|\| !isRenderableConnectedLink\(link\)/)
  assert.match(page, /const connectedPorts = new Map<string, GraphLink>\(\)/)
  assert.match(page, /const localPort = from === coreId \? link\.localPort : link\.remotePort/)
  assert.match(page, /const key = portKey\(localPort\)/)
  assert.match(page, /connectedPorts\.has\(key\)/)
  assert.match(page, /links: \[\.\.\.connectedPorts\.values\(\)\]/)
})

test('persisted links without collector status remain renderable', () => {
  assert.match(page, /Persisted snapshots may omit the collector-only status field/)
  assert.match(page, /const status = lower\(/)
  assert.match(page, /return !status \|\| !CLOSED_PORT_STATES\.some\(/)
})

test('topology interaction controls preserve the viewport while supporting zoom and fullscreen', () => {
  assert.match(page, /const MIN_ZOOM = 0\.55/)
  assert.match(page, /const DEFAULT_FIT_MAX_ZOOM = 2\.5/)
  assert.match(page, /const MAX_ZOOM = 4/)
  assert.match(page, /const resetView = useCallback\(\(\) => \{[\s\S]*setZoom\(1\)[\s\S]*setPanX\(0\)[\s\S]*setPanY\(0\)/)
  assert.match(page, /const fitView = useCallback\(\(\) => \{[\s\S]*setZoom\(\+fitZoom\.toFixed\(2\)\)/)
  assert.match(page, /event\.preventDefault\(\)[\s\S]*zoomAt\(zoom \* \(event\.deltaY < 0 \? 1\.1 : 0\.9\), event\.clientX, event\.clientY\)/)
  assert.match(page, /requestFullscreen\(\)/)
  assert.match(page, /document\.addEventListener\('fullscreenchange'/)
  assert.match(page, /onDoubleClick=\{\(\) => focusNode\(node\)\}/)
  assert.match(page, /data-topology-node="true"/)
  assert.match(page, /transition: dragging \? 'none' : 'transform 160ms ease-out'/)
})

test('topology drag interactions distinguish canvas pan from node movement', () => {
  assert.match(page, /const deltaX = clientX - panStateRef\.current\.startX/)
  assert.match(page, /const deltaY = clientY - panStateRef\.current\.startY/)
  assert.match(page, /setPanX\(panStateRef\.current\.originX \+ deltaX \/ zoom\)/)
  assert.match(page, /setPanY\(panStateRef\.current\.originY \+ deltaY \/ zoom\)/)
  assert.match(page, /mode: 'node'/)
  assert.match(page, /nodeOrigin\.x \+ deltaX \/ zoom/)
  assert.match(page, /nodeOrigin\.y \+ deltaY \/ zoom/)
  assert.match(page, /Math\.hypot\(deltaX, deltaY\) < 4/)
  assert.match(page, /data-topology-node="true"[\s\S]*onPointerDown=/)
  assert.match(page, /topologyGraphRef\.current = next/)
})

test('interaction layer changes visual positions only', () => {
  assert.match(page, /const positions = new Map\(current\.positions\)/)
  assert.match(page, /positions\.set\(panStateRef\.current\.nodeId!, nextPosition\)/)
  assert.match(page, /devices: mergedGraph\.nodes,\s+links: mergedGraph\.links/)
  assert.match(page, /document\.fullscreenElement === graphFullscreenRef\.current/)
})

test('topology wheel zoom uses a non-passive native listener', () => {
  assert.match(page, /viewport\.addEventListener\('wheel', handleWheel, \{ passive: false \}\)/)
  assert.match(page, /viewport\.removeEventListener\('wheel', handleWheel\)/)
  assert.doesNotMatch(page, /onWheel=\{/)
})

test('topology auto-refreshes in the background and keeps manual refresh', () => {
  assert.match(page, /const TOPOLOGY_AUTO_REFRESH_MS = 30_000/)
  assert.match(page, /const refreshTimer = window\.setInterval\(\(\) => \{[\s\S]*void loadTopology\(true\)/)
  assert.match(page, /return \(\) => window\.clearInterval\(refreshTimer\)/)
  assert.match(page, /const refreshTopology = useCallback\(\(\) => \{[\s\S]*return loadTopology\(true\)/)
  assert.match(page, /onClick=\{\(\) => void refreshTopology\(\)\}/)
  assert.match(page, /AUTO 30S/)
})

test('topology restores visual view state without changing topology data', () => {
  assert.match(page, /const VIEW_STATE_KEY = 'topology-view-state-v1'/)
  assert.match(page, /const savedViewRef = useRef\(readSavedView\(\)\)/)
  assert.match(page, /useState\(savedViewRef\.current\.zoom\)/)
  assert.match(page, /useState\(savedViewRef\.current\.panX\)/)
  assert.match(page, /useState\(savedViewRef\.current\.panY\)/)
  assert.match(page, /window\.sessionStorage\.setItem\(VIEW_STATE_KEY, JSON\.stringify\(/)
  assert.match(page, /positions: \[\.\.\.manualPositionsRef\.current\.entries\(\)\]/)
  assert.match(page, /manualPositionsRef\.current\.clear\(\)/)
  assert.match(page, /onClick=\{resetView\}/)
})

test('topology link render keys remain unique when persisted link IDs collide', () => {
  assert.match(page, /const linkRenderKey = \(link: GraphLink, index: number, scope: string\)/)
  assert.match(page, /key=\{linkRenderKey\(link, index, 'graph-link'\)\}/)
  assert.match(page, /key=\{linkRenderKey\(link, index, 'core-connection'\)\}/)
  assert.match(page, /key=\{linkRenderKey\(link, index, 'node-link'\)\}/)
  assert.doesNotMatch(page, /key=\{link\.id\}/)
})
