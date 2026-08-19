import { useCallback, useEffect, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { listDevices, requestJson, type DeviceRecord } from '../lib/api'

type DeviceType = 'gateway' | 'router' | 'firewall' | 'switch' | 'access-point' | 'server' | 'endpoint' | 'unknown'
type DeviceStatus = 'online' | 'warning' | 'offline' | 'unknown'

type GraphNode = {
  id: string
  hostname: string
  ip: string
  mac: string
  type: DeviceType
  status: DeviceStatus
  vendor?: string
  model?: string
  port?: string
  macCount?: number
  macs?: string[]
  ips?: string[]
  vlans?: Array<string | number>
}

type GraphLink = {
  id: string
  from: string
  to: string
  localPort?: string
  remotePort?: string
  vlan?: string | number
  speed?: string | number
  status?: string
  source: 'LLDP/CDP' | 'MAC/ARP' | 'ROUTING'
  confidence: 'CONFIRMED' | 'INFERRED'
  macCount?: number
  wireless?: boolean
  gatewayPath?: boolean
}

type DeviceCollection = {
  device: GraphNode
  macEntries: any[]
  portGroups: any[]
  arpEntries: any[]
  lldpNeighbors: any[]
  routes: any[]
  interfaces: any[]
}

type Layout = {
  nodes: GraphNode[]
  links: GraphLink[]
  positions: Map<string, { x: number; y: number }>
  width: number
  height: number
}

const CACHE_KEY = 'nms.topology.snapshot.v4'
const REFRESH_INTERVAL = 30_000

const str = (...values: any[]) => {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim()
  }
  return ''
}

const lower = (...values: any[]) => str(...values).toLowerCase()
const cleanMac = (...values: any[]) => lower(values.find(value => value !== undefined && value !== null)).replace(/[^a-f0-9]/g, '')
const isMac = (value: any) => cleanMac(value).length === 12
const displayMac = (value: any) => {
  const clean = cleanMac(value)
  return clean.length === 12 ? clean.match(/.{2}/g)!.join(':').toUpperCase() : str(value)
}
const unique = <T,>(values: T[]) => [...new Set(values)]
const portKey = (value: any) => lower(value).replace(/^(gigabitethernet|fastethernet|tengigabitethernet|ethernet|gi|ge|fa|te)/, '')
const isDefaultRoute = (value: any) => ['0.0.0.0/0', '0/0', '::/0', 'default', '0.0.0.0'].includes(lower(value))

function classifyDevice(raw: any, fallback: DeviceType = 'unknown'): DeviceType {
  const explicit = lower(raw?.device_type || raw?.type || raw?.category)
  const value = `${explicit} ${lower(raw?.vendor || raw?.manufacturer)} ${lower(raw?.hostname || raw?.name)}`
  if (explicit.includes('firewall') || value.includes('firewall') || value.includes('fortigate')) return 'firewall'
  if (explicit.includes('router') || explicit.includes('gateway') || value.includes('gateway') || value.includes('router')) return 'router'
  if (explicit.includes('access') || explicit.includes('wireless') || value.includes('access point') || value.includes('wireless')) return 'access-point'
  if (explicit.includes('switch') || value.includes('switch') || value.includes('cisco catalyst')) return 'switch'
  if (explicit.includes('server') || value.includes('server') || value.includes('linux')) return 'server'
  if (explicit.includes('endpoint') || explicit.includes('host')) return 'endpoint'
  return fallback
}

function statusOf(raw: any): DeviceStatus {
  const value = lower(raw?.status || raw?.oper_status || raw?.admin_status)
  if (value.includes('offline') || value.includes('down') || value.includes('fail')) return 'offline'
  if (value.includes('warn') || value.includes('degrad')) return 'warning'
  if (value.includes('unknown')) return 'unknown'
  return 'online'
}

function makeNode(raw: any, fallbackId: string, forcedType?: DeviceType): GraphNode {
  const ip = str(raw?.ip_address, raw?.ip, raw?.management_ip, raw?.managementIp)
  const mac = displayMac(str(raw?.mac_address, raw?.mac, raw?.chassis_mac, raw?.chassisMac))
  const hostname = str(raw?.hostname, raw?.sys_name, raw?.sysName, raw?.name, raw?.device_name, ip, mac, 'UNKNOWN')
  return {
    id: str(raw?.id, raw?.device_id, raw?.node_id, fallbackId),
    hostname,
    ip,
    mac,
    type: forcedType || classifyDevice(raw),
    status: statusOf(raw),
    vendor: str(raw?.vendor, raw?.manufacturer),
    model: str(raw?.model, raw?.device_model),
  }
}

function unwrapRows(payload: any, keys: string[]): any[] {
  if (Array.isArray(payload)) return payload
  for (const key of keys) {
    if (Array.isArray(payload?.data?.[key])) return payload.data[key]
    if (Array.isArray(payload?.[key])) return payload[key]
  }
  return []
}

function readCache(): { layout?: Layout; updated?: string } {
  try {
    const value = JSON.parse(sessionStorage.getItem(CACHE_KEY) || '{}')
    if (!value || typeof value !== 'object' || !Array.isArray(value.layout?.nodes) || !Array.isArray(value.layout?.links)) return {}
    // Positions are rebuilt from the cached nodes/links because JSON does not
    // preserve the Map used by the live SVG layout.
    return { layout: layoutGraph(value.layout.nodes, value.layout.links), updated: value.updated }
  } catch {
    return {}
  }
}

function inventoryMatch(raw: any, inventory: DeviceRecord[]): DeviceRecord | undefined {
  const id = str(raw?.id, raw?.device_id, raw?.node_id)
  const ip = str(raw?.ip, raw?.ip_address, raw?.management_ip)
  const mac = cleanMac(raw?.mac, raw?.mac_address, raw?.chassis_mac)
  const hostname = lower(raw?.hostname, raw?.sys_name, raw?.name)
  return inventory.find(device =>
    (id && String(device.id) === id) ||
    (ip && device.ip_address === ip) ||
    (mac && mac === cleanMac(device.mac_address)) ||
    (hostname && hostname === lower(device.hostname))
  )
}

async function collectModule(deviceId: number, module: string): Promise<any> {
  const endpoint = module === 'mac' ? 'mac-table' : module
  return requestJson<any>(`/snmp/devices/${deviceId}/${endpoint}`)
}

async function collectDevice(device: GraphNode): Promise<DeviceCollection> {
  const deviceId = Number(device.id)
  const results = await Promise.allSettled([
    collectModule(deviceId, 'mac'),
    collectModule(deviceId, 'arp'),
    collectModule(deviceId, 'lldp'),
    collectModule(deviceId, 'routing'),
    collectModule(deviceId, 'interfaces'),
  ])
  const value = (index: number) => results[index].status === 'fulfilled' ? results[index].value : null
  const mac = value(0)
  return {
    device,
    macEntries: unwrapRows(mac, ['entries', 'mac_entries']),
    portGroups: unwrapRows(mac, ['port_groups']),
    arpEntries: unwrapRows(value(1), ['entries', 'arp_entries']),
    lldpNeighbors: unwrapRows(value(2), ['neighbors', 'lldp_entries', 'cdp']),
    routes: unwrapRows(value(3), ['routes', 'routing']),
    interfaces: unwrapRows(value(4), ['interfaces']),
  }
}

function findByIdentity(nodes: GraphNode[], raw: any): GraphNode | undefined {
  const id = str(raw?.id, raw?.device_id, raw?.node_id, raw)
  const ip = str(raw?.ip, raw?.ip_address, raw?.management_ip)
  const mac = cleanMac(raw?.mac, raw?.mac_address, raw?.chassis_mac)
  const hostname = lower(raw?.hostname, raw?.remote_sys_name, raw?.sys_name, raw?.name, raw)
  return nodes.find(node =>
    (id && node.id === id) ||
    (ip && node.ip === ip) ||
    (mac && mac === cleanMac(node.mac)) ||
    (hostname && hostname === lower(node.hostname))
  )
}

function normalizeLldp(row: any) {
  return {
    localPort: str(row?.local_port, row?.local_port_desc, row?.local_port_num),
    remotePort: str(row?.remote_port, row?.remote_port_id, row?.remote_port_desc),
    remoteHostname: str(row?.remote_device, row?.remote_sys_name, row?.remote_hostname),
    remoteIp: str(row?.remote_mgmt_ip, row?.mgmt_address, row?.remote_ip),
    remoteMac: str(row?.remote_mac, row?.remote_chassis_id),
  }
}

function buildGraph(collections: DeviceCollection[], inventory: DeviceRecord[], topologyNodes: any[], topologyLinks: any[]): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodes: GraphNode[] = []
  const byId = new Map<string, GraphNode>()
  const byIdentity = (candidate: any) => findByIdentity(nodes, candidate)
  const addNode = (node: GraphNode) => {
    const existing = byIdentity(node)
    if (existing) {
      existing.ip ||= node.ip
      existing.mac ||= node.mac
      existing.vendor ||= node.vendor
      existing.model ||= node.model
      if (existing.type === 'unknown' && node.type !== 'unknown') existing.type = node.type
      byId.set(existing.id, existing)
      return existing
    }
    nodes.push(node)
    byId.set(node.id, node)
    return node
  }

  collections.forEach(item => addNode(item.device))
  topologyNodes
    .map((raw: any, index: number) => {
      const inventoryDevice = inventoryMatch(raw, inventory)
      return inventoryDevice
        ? makeNode({ ...inventoryDevice, ...raw, id: inventoryDevice.id }, `managed-${index}`)
        : makeNode(raw, `topology-${index}`)
    })
    .filter(node => ['gateway', 'router', 'firewall', 'switch', 'access-point'].includes(node.type))
    .forEach(addNode)

  const links: GraphLink[] = []
  const linkKeys = new Set<string>()
  const addLink = (link: GraphLink) => {
    if (!link.from || !link.to || link.from === link.to) return
    const key = [link.from, link.to, link.localPort || '', link.remotePort || '', link.source].join('|')
    const reverse = [link.to, link.from, link.remotePort || '', link.localPort || '', link.source].join('|')
    if (linkKeys.has(key) || linkKeys.has(reverse)) return
    linkKeys.add(key)
    links.push(link)
  }

  const managedFor = (item: DeviceCollection) => byId.get(item.device.id) || addNode(item.device)
  const remoteFor = (lldp: ReturnType<typeof normalizeLldp>, fallbackIndex: number): GraphNode | undefined => {
    const inventoryDevice = inventory.find(device =>
      (lldp.remoteIp && device.ip_address === lldp.remoteIp) ||
      (lldp.remoteMac && cleanMac(device.mac_address) === cleanMac(lldp.remoteMac)) ||
      (lldp.remoteHostname && lower(device.hostname) === lower(lldp.remoteHostname))
    )
    if (inventoryDevice) return addNode(makeNode(inventoryDevice, `managed-${inventoryDevice.id}`))
    const topologyRaw = topologyNodes.find((raw: any) =>
      (lldp.remoteIp && str(raw.ip, raw.ip_address) === lldp.remoteIp) ||
      (lldp.remoteMac && cleanMac(raw.mac, raw.mac_address) === cleanMac(lldp.remoteMac)) ||
      (lldp.remoteHostname && lower(str(raw.hostname, raw.sys_name)) === lower(lldp.remoteHostname))
    )
    if (topologyRaw) return addNode(makeNode(topologyRaw, `neighbor-${fallbackIndex}`, 'switch'))
    if (!lldp.remoteHostname && !lldp.remoteIp && !lldp.remoteMac) return undefined
    return addNode(makeNode({
      id: `neighbor-${cleanMac(lldp.remoteMac) || lldp.remoteIp || lower(lldp.remoteHostname)}`,
      hostname: lldp.remoteHostname || lldp.remoteIp || displayMac(lldp.remoteMac),
      ip: lldp.remoteIp,
      mac: lldp.remoteMac,
      device_type: 'switch',
    }, `neighbor-${fallbackIndex}`, 'switch'))
  }

  // LLDP/CDP is the only source used for confirmed infrastructure links.
  collections.forEach((item, itemIndex) => {
    const local = managedFor(item)
    item.lldpNeighbors.map(normalizeLldp).forEach((lldp, index) => {
      const remote = remoteFor(lldp, itemIndex * 100 + index)
      if (!remote) return
      const iface = item.interfaces.find((row: any) => {
        const candidate = str(row.ifIndex, row.if_index, row.name, row.if_name, row.interface_name)
        return portKey(candidate) === portKey(lldp.localPort)
      }) || {}
      addLink({
        id: `lldp-${local.id}-${remote.id}-${lldp.localPort}`,
        from: local.id,
        to: remote.id,
        localPort: lldp.localPort,
        remotePort: lldp.remotePort,
        speed: iface.speed_bps || iface.speed,
        status: iface.oper_status || iface.status || 'up',
        source: 'LLDP/CDP',
        confidence: 'CONFIRMED',
        wireless: local.type === 'access-point' || remote.type === 'access-point',
      })
    })
  })

  // Use verified links returned by the topology endpoint only as a fallback
  // when the direct LLDP response did not expose the same row.
  topologyLinks.filter((link: any) => link?.verified === true).forEach((link: any, index: number) => {
    const source = byIdentity({ id: str(link.source_node, link.source) })
    const target = byIdentity({ id: str(link.target_node, link.target), ip: link.target_ip })
    if (!source || !target) return
    addLink({
      id: `verified-${index}-${source.id}-${target.id}`,
      from: source.id,
      to: target.id,
      localPort: str(link.source_port, link.local_port),
      remotePort: str(link.target_port, link.remote_port),
      vlan: link.vlan_id,
      speed: link.interface?.speed_bps || link.speed,
      status: link.interface?.status || link.status || 'up',
      source: 'LLDP/CDP',
      confidence: 'CONFIRMED',
    })
  })

  const arpByMac = new Map<string, any>()
  collections.forEach(item => item.arpEntries.forEach(entry => {
    const mac = cleanMac(entry.mac, entry.mac_address)
    if (mac) arpByMac.set(mac, entry)
  }))

  const lldpPortByDevice = new Map<string, Set<string>>()
  links.filter(link => link.source === 'LLDP/CDP').forEach(link => {
    const values = lldpPortByDevice.get(link.from) || new Set<string>()
    if (link.localPort) values.add(portKey(link.localPort))
    lldpPortByDevice.set(link.from, values)
  })

  // One node per physical port. A port with many MACs remains expandable via
  // the details panel instead of creating dozens of fake physical links.
  collections.forEach(item => {
    const parent = managedFor(item)
    const groups = item.portGroups.length ? item.portGroups : groupMacEntries(item.macEntries)
    groups.forEach((group: any) => {
      const port = str(group.port, group.if_index, group.ifIndex, group.interface)
      if (!port || lldpPortByDevice.get(parent.id)?.has(portKey(port))) return
      const groupMacs = unique([
        ...(Array.isArray(group.macs) ? group.macs : []),
        ...item.macEntries.filter(entry => portKey(str(entry.port, entry.if_index)) === portKey(port)).map(entry => str(entry.mac, entry.mac_address)),
      ].filter(isMac).map(displayMac))
      if (!groupMacs.length) return
      const entries = item.macEntries.filter(entry => groupMacs.some(mac => cleanMac(mac) === cleanMac(entry.mac)))
      const ips = unique([
        ...(Array.isArray(group.ip_addresses) ? group.ip_addresses : []),
        ...entries.flatMap(entry => entry.ip_addresses || entry.ip_address || entry.ip || []),
        ...groupMacs.flatMap(mac => {
          const arp = arpByMac.get(cleanMac(mac))
          return arp ? [str(arp.ip_address, arp.ip)] : []
        }),
      ].flat().filter(Boolean).map(String))
      const vlans = unique([
        ...(Array.isArray(group.vlans) ? group.vlans : []),
        ...entries.map(entry => entry.vlan_id ?? entry.vlan).filter((value: any) => value !== undefined && value !== null),
      ])
      const firstArp = arpByMac.get(cleanMac(groupMacs[0]))
      const single = groupMacs.length === 1
      const endpointId = `port-${parent.id}-${portKey(port)}`
      const endpoint = addNode({
        id: endpointId,
        hostname: single ? str(firstArp?.hostname, firstArp?.host_name, ips[0], groupMacs[0]) : `Port ${port} · ${groupMacs.length} MACs`,
        ip: single ? str(ips[0]) : '',
        mac: single ? groupMacs[0] : '',
        type: 'endpoint',
        status: statusOf(group),
        port,
        macCount: groupMacs.length,
        macs: groupMacs,
        ips,
        vlans,
      })
      const iface = item.interfaces.find((row: any) => portKey(str(row.ifIndex, row.if_index, row.name, row.if_name, row.interface_name)) === portKey(port)) || {}
      addLink({
        id: `port-${parent.id}-${port}`,
        from: parent.id,
        to: endpoint.id,
        localPort: port,
        vlan: vlans.length === 1 ? vlans[0] : undefined,
        speed: iface.speed_bps || iface.speed,
        status: iface.oper_status || iface.status || group.status || 'up',
        source: 'MAC/ARP',
        confidence: 'INFERRED',
        macCount: groupMacs.length,
      })
    })
  })

  // A default route is a real upstream relationship; it is not an invented
  // device-to-device link. Use the next-hop IP and mark the path explicitly.
  collections.forEach(item => {
    const local = managedFor(item)
    item.routes.filter(route => isDefaultRoute(str(route.destination, route.prefix, route.network, route.route)) && str(route.next_hop, route.nextHop, route.gateway, route.gateway_ip)).forEach((route, index) => {
      const nextHop = str(route.next_hop, route.nextHop, route.gateway, route.gateway_ip)
      const existing = inventory.find(device => device.ip_address === nextHop)
      const gateway = existing
        ? addNode(makeNode(existing, `managed-${existing.id}`, 'gateway'))
        : addNode(makeNode({ id: `gateway-${nextHop}`, hostname: `Gateway ${nextHop}`, ip: nextHop, device_type: 'gateway' }, `gateway-${nextHop}`, 'gateway'))
      addLink({
        id: `route-${local.id}-${gateway.id}-${index}`,
        from: local.id,
        to: gateway.id,
        localPort: str(route.interface, route.interface_name),
        status: 'up',
        source: 'ROUTING',
        confidence: 'CONFIRMED',
        gatewayPath: true,
      })
    })
  })

  return { nodes, links }
}

function groupMacEntries(entries: any[]): any[] {
  const groups = new Map<string, any>()
  entries.forEach(entry => {
    const port = str(entry.port, entry.if_index, entry.ifIndex)
    if (!port) return
    const group = groups.get(port) || { port, macs: [], vlans: [], ip_addresses: [] }
    const mac = str(entry.mac, entry.mac_address)
    if (isMac(mac)) group.macs.push(displayMac(mac))
    if (entry.vlan_id !== undefined && entry.vlan_id !== null) group.vlans.push(entry.vlan_id)
    if (entry.ip_address || entry.ip) group.ip_addresses.push(entry.ip_address || entry.ip)
    groups.set(port, group)
  })
  return [...groups.values()].map(group => ({
    ...group,
    macs: unique(group.macs),
    vlans: unique(group.vlans),
    ip_addresses: unique(group.ip_addresses),
  }))
}

function layoutGraph(nodes: GraphNode[], links: GraphLink[]): Layout {
  const infra = new Set<DeviceType>(['gateway', 'router', 'firewall', 'switch', 'access-point'])
  const rank = new Map<string, number>()
  const adjacency = new Map<string, string[]>()
  links.forEach(link => {
    adjacency.set(link.from, [...(adjacency.get(link.from) || []), link.to])
    adjacency.set(link.to, [...(adjacency.get(link.to) || []), link.from])
  })
  const roots = nodes.filter(node => ['gateway', 'router', 'firewall'].includes(node.type))
  const firstRoots = roots.length ? roots : nodes.filter(node => node.type === 'switch').slice(0, 1)
  const queue = firstRoots.map(node => ({ id: node.id, level: 0 }))
  while (queue.length) {
    const current = queue.shift()!
    if (rank.has(current.id) && (rank.get(current.id) || 0) <= current.level) continue
    rank.set(current.id, current.level)
    ;(adjacency.get(current.id) || []).forEach(next => queue.push({ id: next, level: current.level + 1 }))
  }
  nodes.filter(node => !rank.has(node.id) && infra.has(node.type)).forEach((node, index) => rank.set(node.id, Math.max(0, ...rank.values(), 0) + index + 1))
  nodes.filter(node => !rank.has(node.id)).forEach(node => {
    const parent = links.find(link => link.to === node.id || link.from === node.id)
    rank.set(node.id, parent ? (rank.get(parent.from === node.id ? parent.to : parent.from) || 0) + 1 : 0)
  })

  const layers = new Map<number, GraphNode[]>()
  nodes.forEach(node => {
    const level = rank.get(node.id) || 0
    layers.set(level, [...(layers.get(level) || []), node])
  })
  const maxLayer = Math.max(0, ...layers.keys())
  const width = Math.max(1200, ...[...layers.values()].map(layer => layer.length * 230 + 120))
  const rowHeight = 190
  const height = Math.max(650, (maxLayer + 1) * rowHeight + 100)
  const positions = new Map<string, { x: number; y: number }>()
  for (const [level, layer] of layers) {
    const gap = width / (layer.length + 1)
    layer.forEach((node, index) => positions.set(node.id, { x: gap * (index + 1), y: 70 + level * rowHeight }))
  }
  return { nodes, links, positions, width, height }
}

export default function Topology() {
  const cached = readCache()
  const [layout, setLayout] = useState<Layout | null>(cached.layout || null)
  const [lastUpdated, setLastUpdated] = useState(cached.updated ? new Date(cached.updated) : null)
  const [loading, setLoading] = useState(!cached.layout)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedLink, setSelectedLink] = useState<GraphLink | null>(null)
  const [zoom, setZoom] = useState(1)

  const handleBack = useCallback(() => {
    if (window.history.length > 1) {
      window.history.back()
    } else {
      window.location.href = '/'
    }
  }, [])

  const loadTopology = useCallback(async (forceRefresh = false) => {
    setError(null)
    if (layout) setRefreshing(true); else setLoading(true)
    try {
      const [topologyResult, inventoryResult] = await Promise.all([
        requestJson<any>(`/snmp/topology${forceRefresh ? '?refresh=true' : ''}`),
        listDevices(),
      ])
      const inventory = Array.isArray(inventoryResult) ? inventoryResult : []
      const topologyNodes = Array.isArray(topologyResult?.devices) ? topologyResult.devices : []
      const topologyLinks = Array.isArray(topologyResult?.links) ? topologyResult.links : []
      const infrastructureSources = [
        ...inventory.map((device, index) => makeNode(device, `inventory-${index}`)),
        ...topologyNodes.map((node: any, index: number) => {
          const match = inventoryMatch(node, inventory)
          return match ? makeNode({ ...match, ...node, id: match.id }, `managed-${match.id}`) : makeNode(node, `topology-${index}`)
        }),
      ].filter(node => ['gateway', 'router', 'firewall', 'switch', 'access-point'].includes(node.type))
      const root = infrastructureSources.find(node => node.type === 'switch') || infrastructureSources[0]
      if (!root || !Number.isFinite(Number(root.id))) throw new Error('No SNMP infrastructure device is available for topology')

      const firstCollection = await collectDevice(root)
      const remoteDevices = firstCollection.lldpNeighbors.map(normalizeLldp).map(remote => inventory.find(device =>
        (remote.remoteIp && device.ip_address === remote.remoteIp) ||
        (remote.remoteMac && cleanMac(device.mac_address) === cleanMac(remote.remoteMac)) ||
        (remote.remoteHostname && lower(device.hostname) === lower(remote.remoteHostname))
      )).filter(Boolean) as DeviceRecord[]
      const extraSources = unique(remoteDevices.map(device => device.id)).map(id => infrastructureSources.find(node => Number(node.id) === id) || makeNode(inventory.find(device => device.id === id), `managed-${id}`))
      const allCollections = [firstCollection, ...(await Promise.all(extraSources.filter(source => source.id !== root.id).map(collectDevice)))]
      const result = buildGraph(allCollections, inventory, topologyNodes, topologyLinks)
      const nextLayout = layoutGraph(result.nodes, result.links)
      setLayout(nextLayout)
      setLastUpdated(new Date())
      try {
        sessionStorage.setItem(CACHE_KEY, JSON.stringify({ layout: nextLayout, updated: new Date().toISOString() }))
      } catch { /* cache is optional */ }
      if (import.meta.env.DEV) {
        console.debug('[Topology] correlated live sources', {
          devices: result.nodes.length,
          mac: allCollections.reduce((count, item) => count + item.macEntries.length, 0),
          arp: allCollections.reduce((count, item) => count + item.arpEntries.length, 0),
          lldp: allCollections.reduce((count, item) => count + item.lldpNeighbors.length, 0),
          routes: allCollections.reduce((count, item) => count + item.routes.length, 0),
          links: result.links.length,
        })
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Topology data unavailable')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [layout])

  useEffect(() => {
    void loadTopology()
    const timer = window.setInterval(() => void loadTopology(true), REFRESH_INTERVAL)
    return () => window.clearInterval(timer)
  }, [loadTopology])

  const visible = useMemo(() => {
    if (!layout) return { nodes: [], links: [] as GraphLink[] }
    const query = search.trim().toLowerCase()
    const nodes = query
      ? layout.nodes.filter(node => `${node.hostname} ${node.ip} ${node.mac} ${node.port || ''} ${(node.ips || []).join(' ')}`.toLowerCase().includes(query))
      : layout.nodes
    const ids = new Set(nodes.map(node => node.id))
    return { nodes, links: layout.links.filter(link => ids.has(link.from) && ids.has(link.to)) }
  }, [layout, search])

  const counts = useMemo(() => {
    const endpointNodes = layout?.nodes.filter(node => node.type === 'endpoint' || node.type === 'server') || []
    return {
      nodes: layout?.nodes.length || 0,
      links: layout?.links.length || 0,
      confirmed: layout?.links.filter(link => link.confidence === 'CONFIRMED').length || 0,
      inferred: layout?.links.filter(link => link.confidence === 'INFERRED').length || 0,
      mac: endpointNodes.reduce((sum, node) => sum + (node.macCount || 0), 0),
      endpoints: endpointNodes.length,
    }
  }, [layout])

  const colorFor = (type: DeviceType) => {
    if (type === 'gateway' || type === 'router') return '#a78bfa'
    if (type === 'firewall') return '#fb7185'
    if (type === 'switch') return '#22d3ee'
    if (type === 'access-point') return '#c084fc'
    return '#34d399'
  }

  const card = (node: GraphNode, point: { x: number; y: number }) => {
    const infra = ['gateway', 'router', 'firewall', 'switch', 'access-point'].includes(node.type)
    const color = colorFor(node.type)
    const width = infra ? 210 : 188
    const height = infra ? 90 : 82
    const x = point.x - width / 2
    const y = point.y - height / 2
    const selected = selectedNode?.id === node.id
    const detail = node.macCount && node.macCount > 1 ? `${node.macCount} MACs · ${(node.ips || []).length} IPs` : node.mac || 'UNKNOWN'
    return (
      <g key={node.id} onClick={() => { setSelectedNode(node); setSelectedLink(null) }} style={{ cursor: 'pointer' }}>
        <rect x={x} y={y} width={width} height={height} rx="12" fill="#071321" stroke={color} strokeWidth={selected ? 3 : 1.5} />
        <circle cx={x + width - 13} cy={y + 13} r="4" fill={node.status === 'online' ? '#34d399' : node.status === 'warning' ? '#fbbf24' : '#fb7185'} />
        <text x={x + 14} y={y + 23} className="font-mono" style={{ fill: color, fontSize: 10, fontWeight: 700 }}>{node.type.toUpperCase()}</text>
        <text x={x + 14} y={y + 43} className="font-mono" style={{ fill: '#e2e8f0', fontSize: 12, fontWeight: 700 }}>{node.hostname.length > 24 ? `${node.hostname.slice(0, 24)}…` : node.hostname}</text>
        <text x={x + 14} y={y + 59} className="font-mono" style={{ fill: '#8ca0bb', fontSize: 10 }}>{node.ip || (node.port ? `Port ${node.port}` : 'IP UNKNOWN')}</text>
        <text x={x + 14} y={y + 74} className="font-mono" style={{ fill: '#64748b', fontSize: 8 }}>{detail}</text>
      </g>
    )
  }

  return (
    <div className="p-3 md:p-5 space-y-3 h-full flex flex-col" style={{ background: 'radial-gradient(circle at 50% 0%, rgba(34,211,238,.06), transparent 48%)' }}>
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl tracking-widest neon-cyan">NETWORK TOPOLOGY</h1>
          <p className="font-mono text-[10px]" style={{ color: '#8ca0bb' }}>LIVE SNMP · LLDP/CDP CONFIRMED · MAC/ARP PORT INFERENCE</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={handleBack}
            className="glass-bright rounded px-3 py-2 text-xs font-mono transition-opacity hover:opacity-80"
            style={{ color: '#c084fc', border: '1px solid rgba(192,132,252,.2)' }}
            aria-label="Go back"
            title="Go back"
          >
            ← BACK
          </button>
          <span className="font-mono text-[10px]" style={{ color: '#64748b' }}>{lastUpdated ? `Updated ${lastUpdated.toLocaleString()}` : 'Not loaded'}</span>
          <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search hostname / IP / MAC" className="glass-bright rounded px-3 py-2 text-xs font-mono outline-none" style={{ color: '#c8d8ee', border: '1px solid rgba(34,211,238,.2)' }} />
          <button type="button" onClick={() => void loadTopology(true)} className="glass-bright rounded px-3 py-2 text-xs font-mono" style={{ color: '#22d3ee' }}>{refreshing ? 'UPDATING…' : 'REFRESH'}</button>
        </div>
      </div>

      {error && <div className="font-mono text-xs rounded p-3" style={{ color: '#fb7185', background: 'rgba(127,29,29,.2)', border: '1px solid rgba(251,113,133,.2)' }}>{error}</div>}

      <GlassCard className="p-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <Metric label="NODES" value={counts.nodes} />
        <Metric label="LINKS" value={counts.links} />
        <Metric label="CONFIRMED" value={counts.confirmed} color="#22d3ee" />
        <Metric label="INFERRED" value={counts.inferred} color="#fbbf24" />
        <Metric label="MACs ON PORTS" value={counts.mac} color="#34d399" />
        <Metric label="PORT GROUPS" value={counts.endpoints} color="#34d399" />
        <div className="ml-auto font-mono text-[10px]" style={{ color: '#64748b' }}>Auto refresh {REFRESH_INTERVAL / 1000}s</div>
      </GlassCard>

      <GlassCard className="flex-1 min-h-[650px] overflow-hidden relative p-0">
        <div className="absolute left-3 top-3 z-10 flex gap-1 rounded-lg p-1" style={{ background: 'rgba(3,10,20,.9)', border: '1px solid rgba(34,211,238,.18)' }}>
          <button type="button" onClick={() => setZoom(value => Math.min(1.8, +(value + .1).toFixed(2)))} className="px-3 py-1.5 font-mono text-sm" style={{ color: '#22d3ee' }}>+</button>
          <button type="button" onClick={() => setZoom(value => Math.max(.55, +(value - .1).toFixed(2)))} className="px-3 py-1.5 font-mono text-sm" style={{ color: '#22d3ee' }}>−</button>
          <button type="button" onClick={() => setZoom(1)} className="px-2 py-1.5 font-mono text-[9px]" style={{ color: '#8ca0bb' }}>FIT</button>
        </div>
        <div className="absolute right-3 top-3 z-10 font-mono text-[10px] px-2 py-1 rounded" style={{ color: '#8ca0bb', background: 'rgba(3,10,20,.9)', border: '1px solid rgba(34,211,238,.12)' }}>{visible.nodes.length} NODES · {visible.links.length} LINKS</div>

        {loading && !layout ? (
          <div className="h-full flex items-center justify-center font-mono text-sm" style={{ color: '#22d3ee' }}>Loading topology…</div>
        ) : layout ? (
          <div className="h-full overflow-auto" style={{ background: 'radial-gradient(circle at 50% 20%, rgba(34,211,238,.035), transparent 55%)' }}>
            <svg width="100%" height="100%" viewBox={`0 0 ${layout.width / zoom} ${layout.height / zoom}`} preserveAspectRatio="xMidYMin meet" style={{ minWidth: `${Math.min(layout.width, 1000)}px`, minHeight: '650px' }}>
              <defs>
                <filter id="topologyGlow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              </defs>
              {visible.links.map(link => {
                const from = layout.positions.get(link.from)
                const to = layout.positions.get(link.to)
                if (!from || !to) return null
                const color = link.gatewayPath ? '#a78bfa' : link.wireless ? '#c084fc' : link.confidence === 'CONFIRMED' ? '#22d3ee' : '#fbbf24'
                const selected = selectedLink?.id === link.id
                const startY = from.y < to.y ? from.y + 45 : from.y - 45
                const endY = from.y < to.y ? to.y - 45 : to.y + 45
                const midY = (startY + endY) / 2
                return (
                  <g key={link.id} onClick={() => { setSelectedLink(link); setSelectedNode(null) }} style={{ cursor: 'pointer' }}>
                    <path d={`M ${from.x} ${startY} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${endY}`} fill="none" stroke="transparent" strokeWidth="22" />
                    <path d={`M ${from.x} ${startY} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${endY}`} fill="none" stroke={color} strokeWidth={selected ? 4 : link.gatewayPath ? 3 : 2} strokeDasharray={link.confidence === 'INFERRED' ? '8 6' : undefined} filter={selected ? 'url(#topologyGlow)' : undefined}>
                      <animate attributeName="stroke-opacity" values=".35;1;.35" dur={link.gatewayPath ? '1.5s' : '2.4s'} repeatCount="indefinite" />
                      {link.confidence === 'INFERRED' && <animate attributeName="stroke-dashoffset" values="0;-28" dur="1s" repeatCount="indefinite" />}
                    </path>
                    <text x={(from.x + to.x) / 2} y={midY - 7} textAnchor="middle" className="font-mono" style={{ fill: color, fontSize: 9, fontWeight: 700 }}>{link.localPort || link.source}</text>
                    <text x={(from.x + to.x) / 2} y={midY + 8} textAnchor="middle" className="font-mono" style={{ fill: '#64748b', fontSize: 8 }}>{link.remotePort ? `↔ ${link.remotePort}` : link.macCount ? `${link.macCount} MACs` : link.confidence}</text>
                  </g>
                )
              })}
              {visible.nodes.map(node => {
                const point = layout.positions.get(node.id)
                return point ? card(node, point) : null
              })}
            </svg>
          </div>
        ) : null}
      </GlassCard>

      {(selectedNode || selectedLink) && (
        <GlassCard className="p-4">
          {selectedNode && <NodeDetails node={selectedNode} links={layout?.links || []} nodes={layout?.nodes || []} onLink={setSelectedLink} />}
          {selectedLink && <LinkDetails link={selectedLink} nodes={layout?.nodes || []} />}
        </GlassCard>
      )}

      <div className="flex flex-wrap gap-4 font-mono text-[10px]" style={{ color: '#64748b' }}>
        <span><i className="inline-block w-7 border-t-2 mr-2" style={{ borderColor: '#22d3ee' }} />LLDP/CDP CONFIRMED</span>
        <span><i className="inline-block w-7 border-t-2 border-dashed mr-2" style={{ borderColor: '#fbbf24' }} />MAC/ARP INFERRED</span>
        <span><i className="inline-block w-7 border-t-2 mr-2" style={{ borderColor: '#a78bfa' }} />GATEWAY PATH</span>
        <span>Click a node or link for details</span>
      </div>
    </div>
  )
}

function Metric({ label, value, color = '#e2e8f0' }: { label: string; value: number; color?: string }) {
  return <div><div className="font-mono text-[9px]" style={{ color: '#64748b' }}>{label}</div><div className="font-display text-lg" style={{ color }}>{value}</div></div>
}

function NodeDetails({ node, links, nodes, onLink }: { node: GraphNode; links: GraphLink[]; nodes: GraphNode[]; onLink: (link: GraphLink) => void }) {
  const nodeLinks = links.filter(link => link.from === node.id || link.to === node.id)
  return (
    <div className="grid lg:grid-cols-[1fr_1fr] gap-5">
      <div>
        <div className="font-display font-bold text-sm" style={{ color: '#22d3ee' }}>{node.hostname}</div>
        <div className="font-mono text-[10px] mt-1" style={{ color: '#64748b' }}>{node.type.toUpperCase()} · {node.status.toUpperCase()}</div>
        <div className="grid sm:grid-cols-2 gap-x-6 mt-3">
          <Detail label="IP" value={node.ip || 'UNKNOWN'} />
          <Detail label="MAC" value={node.mac || (node.macs?.length ? `${node.macs.length} MACs` : 'UNKNOWN')} />
          <Detail label="PORT" value={node.port || 'UNKNOWN'} />
          <Detail label="VLANs" value={node.vlans?.length ? node.vlans.join(', ') : 'UNKNOWN'} />
          <Detail label="IPs ON PORT" value={node.ips?.length ? node.ips.join(', ') : 'UNKNOWN'} />
          <Detail label="VENDOR / MODEL" value={[node.vendor, node.model].filter(Boolean).join(' · ') || 'UNKNOWN'} />
        </div>
      </div>
      <div>
        <div className="font-display text-xs tracking-wider mb-2" style={{ color: '#8ca0bb' }}>CONNECTIONS</div>
        {nodeLinks.length ? nodeLinks.map(link => {
          const remoteId = link.from === node.id ? link.to : link.from
          const remote = nodes.find(item => item.id === remoteId)
          return <button type="button" key={link.id} onClick={() => onLink(link)} className="w-full text-left py-2 border-t border-cyan-400/10 font-mono text-[10px]" style={{ color: link.confidence === 'CONFIRMED' ? '#22d3ee' : '#fbbf24' }}>{remote?.hostname || remote?.ip || remoteId}<span className="block" style={{ color: '#64748b' }}>{link.localPort || 'PORT UNKNOWN'} · {link.confidence}</span></button>
        }) : <div className="font-mono text-[10px]" style={{ color: '#64748b' }}>No verified or inferred links</div>}
      </div>
    </div>
  )
}

function LinkDetails({ link, nodes }: { link: GraphLink; nodes: GraphNode[] }) {
  const local = nodes.find(node => node.id === link.from)
  const remote = nodes.find(node => node.id === link.to)
  return <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-[10px]">
    <Detail label="LOCAL DEVICE / PORT" value={`${local?.hostname || link.from} · ${link.localPort || 'UNKNOWN'}`} />
    <Detail label="REMOTE DEVICE / PORT" value={`${remote?.hostname || link.to} · ${link.remotePort || 'UNKNOWN'}`} />
    <Detail label="SOURCE / CONFIDENCE" value={`${link.source} · ${link.confidence}`} />
    <Detail label="VLAN / SPEED / STATUS" value={`${link.vlan ?? 'UNKNOWN'} · ${link.speed ?? 'UNKNOWN'} · ${link.status || 'UNKNOWN'}`} />
  </div>
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="py-1.5 border-t border-cyan-400/10"><div style={{ color: '#64748b' }}>{label}</div><div className="mt-1 break-all" style={{ color: '#dbeafe' }}>{value}</div></div>
}
