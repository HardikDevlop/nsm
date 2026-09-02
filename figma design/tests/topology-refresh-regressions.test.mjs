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
  assert.match(page, /if \(forceRefresh && liveCollections\.length > 0\)/)
  assert.match(page, /persistSNMPTopologySnapshot\(Number\(root\.id\)/)
  assert.match(page, /const collectedAt = new Date\(\)\.toISOString\(\)/)
  assert.match(page, /source: 'live_refresh'/)
  assert.match(page, /refresh=true&requested_at=\$\{Date\.now\(\)\}/)
  assert.match(page, /queryClient\.setQueryData\(topologyQueryKey, latestSnapshot\)/)
  assert.match(page, /queryClient\.invalidateQueries\(\{ queryKey: topologyQueryKey, refetchType: 'none' \}\)/)
})

test('topology still uses persisted device inventory and real ICMP reachability', () => {
  assert.match(page, /const storedInventory = Array\.isArray\(inventoryResult\) \? inventoryResult : \[\]/)
  assert.match(page, /const health = await pingIps\(/)
  assert.match(page, /health\.results\.filter\(\(result\) => result\.reachable\)/)
  assert.match(page, /topologyResult\?\.cached === true && \(topologyLinks\.length > 0 \|\| topologyNodes\.length > 0\)/)
  assert.match(page, /responseTimestamp < topologyTimestampRef\.current/)
  assert.doesNotMatch(page, /sessionStorage\.setItem\(CACHE_KEY/)
})

test('persisted topology hydrates the complete snapshot before inventory correlation', () => {
  assert.match(page, /function normalizeGraphNode\(raw: any, fallbackId: string\): GraphNode/)
  assert.match(page, /type: node\.type \|\| 'unknown'/)
  assert.match(page, /const persistedNodes = Array\.isArray\(topologyResult\?\.devices\)/)
  assert.match(page, /topologyResult\.devices\.map\(\(node: any, index: number\) => normalizeGraphNode\(node, `persisted-\$\{index\}`\)\)/)

  const persistedHydration = page.slice(page.indexOf('const persistedNodes'), page.indexOf('const storedInventory'))
  assert.match(persistedHydration, /topologyResult\?\.cached === true && persistedNodes\.length > 0 && persistedLinks\.length > 0/)
  assert.match(persistedHydration, /layoutGraph\(persistedNodes, persistedLinks as GraphLink\[\]\)/)
  assert.match(persistedHydration, /applyTopologyLayout\(persistedLayout, 'persisted topology hydration'/)
  assert.match(persistedHydration, /return/)
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
  assert.match(page, /if \(existingIndex >= 0\) links\[existingIndex\] = merged\n    else links\.push\(merged\)/)
  assert.match(page, /candidate\.ips \|\| \[\]\)\.some\(ip =>/)
  assert.match(page, /candidate\.macs \|\| \[\]\)\.some\(mac =>/)
  assert.match(page, /const links = base\.links\.map\(link => \(\{ \.\.\.link \}\)\)/)
  assert.match(page, /else links\.push\(merged\)/)
  assert.match(page, /const nextLayout = layoutGraph\(mergedGraph\.nodes, mergedGraph\.links\)/)
})

test('incremental refresh preserves baseline on empty or stale collector data', () => {
  assert.match(page, /const mergedGraph = forceRefresh\s+\? mergeTopologyGraph\(topologyGraphRef\.current, result\)/)
  assert.match(page, /if \(!forceRefresh && responseTimestamp && topologyTimestampRef\.current && responseTimestamp < topologyTimestampRef\.current\)/)
  assert.match(page, /persistSNMPTopologySnapshot\(Number\(root\.id\), \{[\s\S]*devices: mergedGraph\.nodes,[\s\S]*links: mergedGraph\.links/)
})

test('topology render shows only nodes connected by persisted links', () => {
  assert.match(page, /const CLOSED_PORT_STATES = \['down', 'closed', 'disabled', 'inactive', 'err-disabled', 'failed', 'offline'\]/)
  assert.match(page, /link\.status,[\s\S]*\(link as any\)\.oper_status/)
  assert.match(page, /return !status \|\| !CLOSED_PORT_STATES\.some\(state => status === state \|\| status\.includes\(state\)\)/)
  assert.match(page, /const openLinks = layout\.links\.filter\(isOpenPortLink\)/)
  assert.match(page, /const connectedIds = new Set\(openLinks\.flatMap\(link => \[link\.from, link\.to\]\)\)/)
  assert.match(page, /\.filter\(node => connectedIds\.has\(node\.id\)\)/)
  assert.match(page, /openLinks\.filter\(link => ids\.has\(link\.from\) && ids\.has\(link\.to\)\)/)
})

test('persisted links without collector status remain renderable', () => {
  assert.match(page, /Persisted snapshots may omit the collector-only status field/)
  assert.match(page, /const status = lower\(/)
  assert.match(page, /return !status \|\| !CLOSED_PORT_STATES\.some\(/)
})

test('topology interaction controls preserve the viewport while supporting zoom and fullscreen', () => {
  assert.match(page, /const MIN_ZOOM = 0\.55/)
  assert.match(page, /const MAX_ZOOM = 2\.5/)
  assert.match(page, /const resetView = useCallback\(\(\) => \{[\s\S]*setZoom\(1\)[\s\S]*setPanX\(0\)[\s\S]*setPanY\(0\)/)
  assert.match(page, /const fitView = useCallback\(\(\) => \{[\s\S]*setZoom\(\+fitZoom\.toFixed\(2\)\)/)
  assert.match(page, /event\.preventDefault\(\)[\s\S]*zoomAt\(zoom \* \(event\.deltaY < 0 \? 1\.1 : 0\.9\), event\.clientX, event\.clientY\)/)
  assert.match(page, /requestFullscreen\(\)/)
  assert.match(page, /document\.addEventListener\('fullscreenchange'/)
  assert.match(page, /onDoubleClick=\{\(\) => focusNode\(node\)\}/)
  assert.match(page, /data-topology-node="true"/)
  assert.match(page, /transition: 'transform 160ms ease-out'/)
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

test('topology has no background polling and keeps manual refresh', () => {
  assert.doesNotMatch(page, /setInterval\(/)
  assert.match(page, /const refreshTopology = useCallback\(\(\) => \{[\s\S]*return loadTopology\(true\)/)
  assert.match(page, /onClick=\{\(\) => void refreshTopology\(\)\}/)
  assert.match(page, /Auto refresh OFF/)
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
