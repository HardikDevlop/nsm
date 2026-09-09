import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { persistSNMPTopologySnapshot, requestJson, updateDevice, type DeviceRecord } from '../lib/api'
import { agnigateLabel, isAgnigateMac } from '../lib/deviceIdentity'
import { useNavigate } from 'react-router'
import { useQueryClient } from '../lib/queryProvider'
import { useI18n } from '../i18n/I18nContext'

type DeviceType = 'gateway' | 'router' | 'firewall' | 'switch' | 'access-point' | 'server' | 'endpoint' | 'cpu' | 'port-summary' | 'unknown'
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
  topology_metadata?: { port?: string; vlans?: Array<string | number>; ips?: string[] }
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

const linkRenderKey = (link: GraphLink, index: number, scope: string) =>
  `${scope}:${link.id}:${link.from}:${link.to}:${link.localPort || ''}:${link.remotePort || ''}:${index}`

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
  rootId?: string
}

type TopologyNodeDetails = {
  device?: {
    id: number
    name?: string
    hostname?: string
    ip_address?: string
    vendor?: string | null
    device_type?: string | null
    model?: string | null
    serial_number?: string | null
    firmware?: string | null
    mac_address?: string | null
    topology_metadata?: { port?: string; vlans?: Array<string | number>; ips?: string[] }
    status?: string
    monitoring_status?: boolean
    last_seen?: string | null
    created_at?: string | null
    uptime_seconds?: number
  }
  snmp?: {
    version?: string | null
    status?: string | null
  }
  capabilities?: Record<string, boolean>
  monitoring?: Array<{
    module_name: string
    enabled: boolean
    status: string
    last_poll_at?: string | null
  }>
}

type HoverPreview = {
  title: string
  lines: string[]
  x: number
  y: number
  above: boolean
}

type PanState = {
  active: boolean
  mode: 'canvas' | 'node'
  startX: number
  startY: number
  originX: number
  originY: number
  nodeId?: string
  nodeOrigin?: { x: number; y: number }
  moved: boolean
}

const MIN_ZOOM = 0.55
const DEFAULT_FIT_MAX_ZOOM = 2.5
const MAX_ZOOM = 4
const VIEW_STATE_KEY = 'topology-view-state-v1'

type SavedViewState = {
  zoom: number
  panX: number
  panY: number
  positions: Array<[string, { x: number; y: number }]>
}

function readSavedView(): SavedViewState {
  const fallback: SavedViewState = { zoom: 1, panX: 0, panY: 0, positions: [] }
  if (typeof window === 'undefined') return fallback
  try {
    const value = JSON.parse(window.sessionStorage.getItem(VIEW_STATE_KEY) || 'null')
    return value && typeof value === 'object' ? { ...fallback, ...value } : fallback
  } catch {
    return fallback
  }
}

const str = (...values: any[]) => {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim()
  }
  return ''
}

const lower = (...values: any[]) => str(...values).toLowerCase()
const destinationPortLabel = (value: any) => {
  const port = str(value)
  return !port || lower(port).includes('unknown') ? '1' : port
}
const cleanMac = (...values: any[]) => lower(values.find(value => value !== undefined && value !== null)).replace(/[^a-f0-9]/g, '')
const isMac = (value: any) => cleanMac(value).length === 12
const displayMac = (value: any) => {
  const clean = cleanMac(value)
  return clean.length === 12 ? clean.match(/.{2}/g)!.join(':').toUpperCase() : str(value)
}
const unique = <T,>(values: T[]) => [...new Set(values)]
const portKey = (value: any) => lower(value).replace(/^(gigabitethernet|fastethernet|tengigabitethernet|ethernet|gi|ge|fa|te)/, '')
function ipSortKey(value: unknown): [number, ...Array<number | string>] {
  const text = String(value)
  const parts = text.split('.')
  if (parts.length === 4 && parts.every(part => /^\d+$/.test(part))) {
    return [0, ...parts.map(Number)]
  }
  return [1, text]
}
const isDefaultRoute = (value: any) => ['0.0.0.0/0', '0/0', '::/0', 'default', '0.0.0.0'].includes(lower(value))
const CLOSED_PORT_STATES = ['down', 'closed', 'disabled', 'inactive', 'err-disabled', 'failed', 'offline']

// Persisted snapshots may omit the collector-only status field. Keep those
// valid topology links visible; hide only links with explicit down evidence.
const isOpenPortLink = (link: GraphLink) => {
  const status = lower(
    link.status,
    (link as any).oper_status,
    (link as any).port_status,
    (link as any).state,
    (link as any).interface?.status,
    (link as any).interface?.oper_status,
  )
  return !status || !CLOSED_PORT_STATES.some(state => status === state || status.includes(state))
}

// A learned MAC on a port is a connected-port signal even when the separate
// interface snapshot is stale or reports that port down. PORT SUMMARY follows
// the learned MAC table, so topology must use the same rule for MAC/ARP links.
const isRenderableConnectedLink = (link: GraphLink) =>
  link.source === 'MAC/ARP' ? !link.gatewayPath : isOpenPortLink(link)

function findCoreNode(nodes: GraphNode[], links: GraphLink[]): GraphNode | undefined {
  const candidates = nodes.filter(node => node.type === 'switch' && lower(node.hostname).includes('core'))
  const switches = candidates.length ? candidates : nodes.filter(node => node.type === 'switch')
  if (!switches.length) return undefined
  const degree = (node: GraphNode) => links.reduce((count, link) =>
    count + (String(link.from) === String(node.id) || String(link.to) === String(node.id) ? 1 : 0), 0)
  // Prefer the canonical managed/inventory node over an IP-less persisted
  // alias. If the persisted node type is misleading, the highest-degree
  // switch is the actual core/root rather than an endpoint MAC node.
  return [...switches].sort((left, right) =>
    degree(right) - degree(left) || Number(Boolean(right.ip)) - Number(Boolean(left.ip))
  )[0]
}

function classifyDevice(raw: any, fallback: DeviceType = 'unknown'): DeviceType {
  const explicit = lower(raw?.device_type || raw?.type || raw?.category)
  const value = `${explicit} ${lower(raw?.vendor || raw?.manufacturer)} ${lower(raw?.hostname || raw?.name)}`
  if (explicit.includes('firewall') || value.includes('firewall') || value.includes('fortigate')) return 'firewall'
  if (explicit.includes('gateway') || value.includes('gateway') || value.includes('agnigate')) return 'gateway'
  if (explicit.includes('router') || value.includes('router')) return 'router'
  if (explicit.includes('access') || explicit.includes('wireless') || value.includes('access point') || value.includes('wireless')) return 'access-point'
  if (explicit.includes('switch') || value.includes('switch') || value.includes('cisco catalyst')) return 'switch'
  if (value.includes('nvr') || value.includes('camera') || value.includes('cctv')) return 'endpoint'
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
  const metadata = raw?.topology_metadata || {}
  const ip = str(raw?.ip_address, raw?.ip, raw?.management_ip, raw?.managementIp)
  const mac = displayMac(str(raw?.mac_address, raw?.mac, raw?.chassis_mac, raw?.chassisMac))
  const hostname = isAgnigateMac(mac)
    ? agnigateLabel(str(raw?.hostname, raw?.sys_name, raw?.sysName, raw?.name, raw?.device_name, raw?.display_name, ip, mac, 'UNKNOWN'))
    : str(raw?.hostname, raw?.sys_name, raw?.sysName, raw?.name, raw?.device_name, raw?.display_name, ip, mac, 'UNKNOWN')
  return {
    id: str(raw?.id, raw?.device_id, raw?.node_id, fallbackId),
    hostname,
    ip,
    mac,
    type: forcedType || classifyDevice(raw),
    status: statusOf(raw),
    vendor: str(raw?.vendor, raw?.manufacturer),
    model: str(raw?.model, raw?.device_model),
    port: str(raw?.port, raw?.interface_name, raw?.if_name, metadata.port),
    macCount: raw?.macCount,
    macs: raw?.macs,
    ips: raw?.ips || metadata.ips,
    vlans: raw?.vlans || metadata.vlans,
    topology_metadata: metadata,
  }
}

function normalizeGraphNode(raw: any, fallbackId: string): GraphNode {
  const explicitType = str(raw?.device_type, raw?.type, raw?.category)
  const node = makeNode(raw || {}, fallbackId, explicitType ? undefined : 'unknown')
  return {
    ...node,
    type: node.type || 'unknown',
    hostname: node.hostname || 'UNKNOWN',
    ip: node.ip || '',
    mac: node.mac || '',
    vendor: node.vendor || '',
    model: node.model || '',
    port: node.port || '',
  }
}

function normalizePersistedLink(raw: any, index: number): GraphLink | null {
  const from = str(raw?.from, raw?.source_node, raw?.source, raw?.source_id)
  const to = str(raw?.to, raw?.target_node, raw?.target, raw?.target_id)
  if (!from || !to) return null
  const sourceValue = lower(raw?.source, raw?.protocol)
  const source: GraphLink['source'] = sourceValue.includes('arp') || sourceValue.includes('mac')
    ? 'MAC/ARP'
    : sourceValue.includes('routing') || sourceValue.includes('route')
      ? 'ROUTING'
      : 'LLDP/CDP'
  return {
    ...raw,
    id: str(raw?.id, `persisted-link-${index}`),
    from,
    to,
    localPort: str(raw?.localPort, raw?.local_port, raw?.source_port),
    remotePort: str(raw?.remotePort, raw?.remote_port, raw?.target_port),
    status: raw?.status,
    source,
    confidence: raw?.confidence === 'INFERRED' || raw?.verified === false ? 'INFERRED' : 'CONFIRMED',
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

async function collectModule(deviceId: number, module: string, fresh = false): Promise<any> {
  const endpoint = module === 'mac' ? 'mac-table' : module
  return requestJson<any>(`/snmp/devices/${deviceId}/${endpoint}`, fresh ? { cache: 'no-store' } : undefined)
}

async function collectDevice(device: GraphNode, fresh = false): Promise<DeviceCollection> {
  const deviceId = Number(device.id)
  const results = await Promise.allSettled([
    collectModule(deviceId, 'mac', fresh),
    collectModule(deviceId, 'arp', fresh),
    collectModule(deviceId, 'lldp', fresh),
    collectModule(deviceId, 'routing', fresh),
    collectModule(deviceId, 'interfaces', fresh),
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

async function collectStoredDevice(device: GraphNode): Promise<DeviceCollection> {
  const payload = await requestJson<any>('/monitoring/data', {
    method: 'POST',
    body: JSON.stringify({
      device_id: Number(device.id),
      modules: ['interfaces', 'lldp', 'cdp', 'arp', 'mac_table', 'routing'],
      include_history: false,
    }),
  })
  const moduleData = (name: string) => payload?.modules?.[name]?.data
  const mac = moduleData('mac_table')
  const lldp = moduleData('lldp') || moduleData('cdp')
  return {
    device,
    macEntries: unwrapRows(mac, ['entries', 'mac_entries']),
    portGroups: unwrapRows(mac, ['port_groups']),
    arpEntries: unwrapRows(moduleData('arp'), ['entries', 'arp_entries']),
    lldpNeighbors: unwrapRows(lldp, ['neighbors', 'lldp_entries', 'cdp']),
    routes: unwrapRows(moduleData('routing'), ['routes', 'routing']),
    interfaces: unwrapRows(moduleData('interfaces'), ['interfaces']),
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
      // Persisted snapshots can contain the same port aggregate with an old
      // first-MAC label. The current MAC/ARP collection is authoritative for
      // aggregate identity and must refresh its label and member lists.
      if (String(node.id).startsWith('port-') && existing.id === node.id) {
        existing.hostname = node.hostname
        existing.ip = node.ip
        existing.mac = node.mac
        existing.port = node.port
        existing.macCount = node.macCount
        existing.macs = node.macs
        existing.ips = node.ips
        existing.vlans = node.vlans
      }
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
  const addSyntheticNode = (node: GraphNode) => {
    const existing = nodes.find(candidate =>
      candidate.id === node.id ||
      (node.type === 'cpu' && candidate.type === 'cpu' && cleanMac(candidate.mac) === cleanMac(node.mac))
    )
    if (existing) {
      existing.ip ||= node.ip
      existing.mac ||= node.mac
      existing.macCount = Math.max(existing.macCount || 0, node.macCount || 0)
      existing.macs = unique([...(existing.macs || []), ...(node.macs || [])])
      existing.ips = unique([...(existing.ips || []), ...(node.ips || [])])
      existing.vlans = unique([...(existing.vlans || []), ...(node.vlans || [])])
      return existing
    }
    nodes.push(node)
    byId.set(node.id, node)
    return node
  }

  collections.forEach(item => addNode(item.device))
  // Keep every managed DB device visible even when the cached SNMP snapshot
  // contains only the device that was used as the collection root. Servers
  // and unknown device types are still useful topology endpoints, so do not
  // discard them before the graph is built.
  inventory
    .map((device, index) => makeNode(device, `inventory-${index}`))
    .forEach(addNode)
  topologyNodes
    // Port aggregates are rebuilt from the current MAC/ARP collections below.
    // Never seed them from an older persisted snapshot, otherwise the first
    // MAC label can survive even after the primary managed device changes.
    .filter((raw: any) => !String(raw?.id || '').startsWith('port-'))
    .map((raw: any, index: number) => {
      const inventoryDevice = inventoryMatch(raw, inventory)
      return inventoryDevice
        // The DB inventory is authoritative for a managed device identity.
        // A persisted topology node may carry a learned port MAC instead of
        // the device chassis MAC and must not overwrite the DB MAC by IP.
        ? makeNode(inventoryDevice, `managed-${index}`)
        : makeNode(raw, `topology-${index}`)
    })
    .forEach(addNode)

  const links: GraphLink[] = []
  const linkPairs = new Map<string, number>()
  const addLink = (link: GraphLink) => {
    if (!link.from || !link.to || link.from === link.to) return
    // LLDP/CDP and MAC/ARP can describe the same device pair. They must not
    // become two visual lines just because their source/port metadata differs.
    const key = [String(link.from), String(link.to)].sort().join('|')
    const existingIndex = linkPairs.get(key)
    if (existingIndex !== undefined) {
      const existing = links[existingIndex]
      if (link.source === 'MAC/ARP' && link.localPort) {
        // Port Summary is authoritative for the monitored switch-side port.
        // Keep that port even when LLDP supplied a neighbor-side eth0 link
        // for the same device pair.
        links[existingIndex] = {
          ...existing,
          localPort: link.localPort,
          macCount: link.macCount || existing.macCount,
        }
        return
      }
      if (existing.confidence !== 'CONFIRMED' && link.confidence === 'CONFIRMED') {
        links[existingIndex] = {
          ...link,
          localPort: existing.localPort || link.localPort,
          macCount: existing.macCount || link.macCount,
        }
      }
      return
    }
    linkPairs.set(key, links.length)
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
    if (topologyRaw) return addNode(makeNode(topologyRaw, `neighbor-${fallbackIndex}`, classifyDevice(topologyRaw, 'unknown')))
    if (!lldp.remoteHostname && !lldp.remoteIp && !lldp.remoteMac) return undefined
    return addNode(makeNode({
      id: `neighbor-${cleanMac(lldp.remoteMac) || lldp.remoteIp || lower(lldp.remoteHostname)}`,
      hostname: isAgnigateMac(lldp.remoteMac)
        ? agnigateLabel(lldp.remoteHostname || lldp.remoteIp || displayMac(lldp.remoteMac))
        : lldp.remoteHostname || lldp.remoteIp || displayMac(lldp.remoteMac),
      ip: lldp.remoteIp,
      mac: lldp.remoteMac,
      device_type: classifyDevice({ hostname: lldp.remoteHostname }, 'unknown'),
    }, `neighbor-${fallbackIndex}`, 'switch'))
  }

  // LLDP/CDP is the only source used for confirmed infrastructure links.
  collections.forEach((item, itemIndex) => {
    const local = managedFor(item)
    item.lldpNeighbors.map(normalizeLldp).forEach((lldp, index) => {
      const sameIp = Boolean(lldp.remoteIp && local.ip && lldp.remoteIp === local.ip)
      const sameMac = Boolean(lldp.remoteMac && local.mac && cleanMac(lldp.remoteMac) === cleanMac(local.mac))
      const sameHostname = Boolean(lldp.remoteHostname && local.hostname && lower(lldp.remoteHostname) === lower(local.hostname))
      // Some NVR/endpoint LLDP agents report their own eth0 as the remote
      // neighbor. Never turn that self-advertisement into a switch link.
      if (sameIp || sameMac || sameHostname) return
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
  topologyLinks.filter((link: any) => link?.verified === true && !lower(link?.protocol, link?.source).includes('routing')).forEach((link: any, index: number) => {
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

  // One node per physical port. A port with many MACs remains expandable via
  // the details panel instead of creating dozens of fake physical links.
  collections.forEach(item => {
    const parent = managedFor(item)
    // Some persisted collectors update entries and port_groups separately.
    // Merge both DB-backed shapes so a newly learned port cannot disappear
    // just because the grouped projection is one poll behind.
    const groupsByPort = new Map<string, any>()
    const selfMacs = new Set(
      item.macEntries
        .filter((entry: any) => lower(entry?.status) === 'self')
        .map((entry: any) => cleanMac(entry?.mac, entry?.mac_address))
        .filter(Boolean),
    )
    ;[
      ...item.portGroups,
      ...groupMacEntries(item.macEntries.filter((entry: any) => lower(entry?.status) !== 'self')),
    ].forEach((candidate: any) => {
      const learnedMacs = (candidate.macs || []).filter((mac: any) => !selfMacs.has(cleanMac(mac)))
      if (!learnedMacs.length) return
      const candidatePort = str(candidate.port, candidate.if_index, candidate.ifIndex, candidate.interface)
      const key = portKey(candidatePort)
      if (!key) return
      const existing = groupsByPort.get(key)
      if (!existing) {
        groupsByPort.set(key, { ...candidate, macs: [...learnedMacs], ip_addresses: [...(candidate.ip_addresses || candidate.ips || [])], vlans: [...(candidate.vlans || [])] })
        return
      }
      existing.macs = unique([...(existing.macs || []), ...learnedMacs])
      existing.ip_addresses = unique([...(existing.ip_addresses || []), ...(candidate.ip_addresses || candidate.ips || [])])
      existing.vlans = unique([...(existing.vlans || []), ...(candidate.vlans || [])])
      existing.classification ||= candidate.classification
    })
    const groups = [...groupsByPort.values()]
    groups.forEach((group: any) => {
      const port = str(group.port, group.if_index, group.ifIndex, group.interface)
      const classification = lower(group.classification, group.class, group.port_type)
      // Use the collector's PORT SUMMARY classification. LLDP alone is not
      // enough to hide a port because an endpoint may also advertise LLDP.
      if (!port || classification.includes('uplink') || classification.includes('trunk')) return
      const groupMacs = unique([
        ...(Array.isArray(group.macs) ? group.macs : []),
        ...item.macEntries.filter(entry => portKey(str(entry.port, entry.if_index)) === portKey(port)).map(entry => str(entry.mac, entry.mac_address)),
      ].filter(isMac).map(displayMac).sort())
      if (!groupMacs.length) return
      const entries = item.macEntries.filter(entry => groupMacs.some(mac => cleanMac(mac) === cleanMac(entry.mac)))
      const ips = unique([
        ...(Array.isArray(group.ip_addresses) ? group.ip_addresses : []),
        ...entries.flatMap(entry => entry.ip_addresses || entry.ip_address || entry.ip || []),
        ...groupMacs.flatMap(mac => {
          const arp = arpByMac.get(cleanMac(mac))
          return arp ? [str(arp.ip_address, arp.ip)] : []
        }),
      ].flat().filter(Boolean).map(String)).sort((left, right) =>
        JSON.stringify(ipSortKey(left)).localeCompare(JSON.stringify(ipSortKey(right)), undefined, { numeric: true }),
      )
      const vlans = unique([
        ...(Array.isArray(group.vlans) ? group.vlans : []),
        ...entries.map(entry => entry.vlan_id ?? entry.vlan).filter((value: any) => value !== undefined && value !== null),
      ])
      // Use a stable machine identity for aggregate groups. ARP hostnames and
      // raw walk order can change between polls, while sorted IP/MAC values do
      // not cause the same topology card to rename itself.
      const resolvedIp = ips[0] || ''
      // A managed row can describe the same host without a MAC address. In
      // that case identity matching cannot join it to the port group, so
      // correlate the endpoint using the IPs learned from ARP as well.
      // Prefer an exact learned MAC/IP from the managed inventory as the
      // primary endpoint for a multi-MAC port. MAC/IP evidence is stronger
      // than the inventory type because APs are often stored as unknown or
      // generic network devices. The remaining learned hosts stay in the
      // port details.
      const correlatedEndpoint = nodes
        .filter(node => node.id !== parent.id)
        .map(node => {
          const exactMac = groupMacs.some(mac => cleanMac(mac) === cleanMac(node.mac))
          const exactIp = ips.some(ip => ip === node.ip || (node.ips || []).includes(ip))
          return { node, score: exactMac ? 100 : exactIp ? 80 : 0, exactMac, exactIp }
        })
        .filter(candidate => candidate.score > 0)
        .sort((left, right) => right.score - left.score || Number(left.node.id) - Number(right.node.id))[0]
      const parentMac = cleanMac(parent.mac)
      const isSelfMac = Boolean(parentMac) && groupMacs.some(mac => cleanMac(mac) === parentMac)
      // The switch's own FDB entry is not a connected endpoint. Do not render
      // it as a fake CPU/device node or create a self-link.
      if (isSelfMac) return
      const endpointCandidate: GraphNode = {
              id: `port-${parent.id}-${portKey(port)}`,
        hostname: groupMacs.length > 1 ? `Port ${port} (${groupMacs.length} MACs)` : (groupMacs[0] || resolvedIp || 'MAC UNKNOWN'),
        ip: groupMacs.length === 1 ? resolvedIp : '',
        mac: groupMacs.length === 1 ? groupMacs[0] : '',
              type: 'endpoint',
              status: statusOf(group),
              port,
              macCount: groupMacs.length,
              macs: groupMacs,
              ips,
              vlans,
            }
      const endpoint = correlatedEndpoint ? correlatedEndpoint.node : addNode(endpointCandidate)
      if (correlatedEndpoint) {
        const primaryMac = correlatedEndpoint.exactMac
          ? groupMacs.find(mac => cleanMac(mac) === cleanMac(correlatedEndpoint.node.mac))
          : correlatedEndpoint.node.mac || groupMacs[0]
        const primaryIp = correlatedEndpoint.exactIp
          ? ips.find(ip => ip === correlatedEndpoint.node.ip || (correlatedEndpoint.node.ips || []).includes(ip))
          : correlatedEndpoint.node.ip || resolvedIp
        correlatedEndpoint.node.type = correlatedEndpoint.node.type === 'unknown' ? 'endpoint' : correlatedEndpoint.node.type
        correlatedEndpoint.node.hostname = primaryMac || primaryIp || correlatedEndpoint.node.hostname
        correlatedEndpoint.node.ip = primaryIp || ''
        correlatedEndpoint.node.mac = primaryMac || ''
        correlatedEndpoint.node.port = port
        correlatedEndpoint.node.macCount = groupMacs.length
        correlatedEndpoint.node.macs = groupMacs
        correlatedEndpoint.node.ips = ips
        correlatedEndpoint.node.vlans = vlans
      }
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
  const nodeById = new Map(nodes.map(node => [node.id, node]))
  const incident = new Map<string, GraphLink[]>()
  links.forEach(link => {
    incident.set(link.from, [...(incident.get(link.from) || []), link])
    incident.set(link.to, [...(incident.get(link.to) || []), link])
  })
  const degree = (node: GraphNode) => (incident.get(node.id) || []).length
  const root = nodes
    .filter(node => node.type === 'switch')
    .sort((a, b) => degree(b) - degree(a))[0]
    || nodes
      .filter(node => ['router', 'gateway', 'firewall'].includes(node.type))
      .sort((a, b) => degree(b) - degree(a))[0]
    || nodes.slice().sort((a, b) => degree(b) - degree(a))[0]

  const positions = new Map<string, { x: number; y: number }>()
  if (!root) return { nodes, links, positions, width: 1200, height: 650 }

  const rootLinks = incident.get(root.id) || []
  const isUplink = (node: GraphNode) => ['gateway', 'router', 'firewall'].includes(node.type)
  const otherEnd = (link: GraphLink) => link.from === root.id ? link.to : link.from
  const uplinks = unique(rootLinks.map(otherEnd).filter(id => {
    const node = nodeById.get(id)
    return Boolean(node && isUplink(node))
  }))
  const groups = new Map<string, string[]>()
  rootLinks.forEach(link => {
    const childId = otherEnd(link)
    const child = nodeById.get(childId)
    if (!child || uplinks.includes(childId)) return
    const port = link.from === root.id ? link.localPort : link.remotePort
    const group = str(port, `PORT-${groups.size + 1}`, 'UNKNOWN PORT')
    groups.set(group, [...(groups.get(group) || []), childId])
  })

  const width = Math.max(1200, groups.size * 240 + 120)
  const rootX = width / 2
  positions.set(root.id, { x: rootX, y: 300 })
  uplinks.forEach((id, index) => positions.set(id, {
    x: rootX + (index - (uplinks.length - 1) / 2) * 240,
    y: 90,
  }))

  const placed = new Set([root.id, ...uplinks])
  const groupEntries = [...groups.entries()]
  groupEntries.forEach(([group, childIds], groupIndex) => {
    const groupX = (groupIndex + 1) * (width / (groupEntries.length + 1))
    childIds.forEach((id, childIndex) => {
      const x = groupX + (childIndex - (childIds.length - 1) / 2) * 210
      positions.set(id, { x, y: 525 })
      placed.add(id)
    })
    // Keep downstream nodes under the same physical port group.
    const queue = childIds.map(id => ({ id, level: 1 }))
    while (queue.length) {
      const current = queue.shift()!
      ;(incident.get(current.id) || []).forEach(link => {
        const nextId = link.from === current.id ? link.to : link.from
        if (placed.has(nextId) || nextId === root.id) return
        placed.add(nextId)
        const siblings = groupEntries[groupIndex][1]
        const slot = siblings.indexOf(current.id)
        const x = groupX + (slot - (siblings.length - 1) / 2) * 210
        positions.set(nextId, { x, y: 525 + current.level * 175 })
        queue.push({ id: nextId, level: current.level + 1 })
      })
    }
  })

  const unplaced = nodes.filter(node => !placed.has(node.id))
  unplaced.forEach((node, index) => positions.set(node.id, {
    x: 100 + (index % 5) * 230,
    y: 525 + Math.floor(index / 5) * 175,
  }))
  const maxY = Math.max(650, ...[...positions.values()].map(point => point.y + 100))
  return { nodes, links, positions, width, height: maxY, rootId: root.id }
}

const TOPOLOGY_LAST_SNAPSHOT_KEY = 'topology-last-snapshot-v1'
const TOPOLOGY_LAYOUT_CACHE_KEY = 'topology-layout-cache-v1'
const TOPOLOGY_LAYOUT_QUERY_KEY = ['snmp-topology-layout'] as const
const TOPOLOGY_AUTO_REFRESH_MS = 30_000
const isCompleteTopologyLayout = (layout: Layout | null | undefined) => Boolean(layout && layout.nodes.length >= 2 && layout.links.length > 0)

function readTopologySnapshot(): any {
  if (typeof window === 'undefined') return null
  try {
    const value = JSON.parse(window.localStorage.getItem(TOPOLOGY_LAST_SNAPSHOT_KEY) || 'null')
    return Array.isArray(value?.devices) && Array.isArray(value?.links) && value.devices.length >= 2 && value.links.length > 0 ? value : null
  } catch {
    return null
  }
}

function readTopologyLayoutCache(): Layout | null {
  if (typeof window === 'undefined') return null
  try {
    const serialized = window.localStorage.getItem(TOPOLOGY_LAYOUT_CACHE_KEY) || window.sessionStorage.getItem(TOPOLOGY_LAYOUT_CACHE_KEY)
    const value = JSON.parse(serialized || 'null')
    if (!Array.isArray(value?.nodes) || !Array.isArray(value?.links) || value.nodes.length < 2 || value.links.length < 1) return null
    const nodes = value.nodes.map((node: any, index: number) => normalizeGraphNode(node, `cached-layout-${index}`))
    const links = value.links.map(normalizePersistedLink).filter(Boolean) as GraphLink[]
    const positions = new Map<string, { x: number; y: number }>(
      Array.isArray(value.positions) ? value.positions.filter((entry: any) => Array.isArray(entry) && entry.length === 2) : [],
    )
    return { nodes, links, positions, width: Number(value.width) || 1200, height: Number(value.height) || 650, rootId: value.rootId ? String(value.rootId) : undefined }
  } catch {
    return null
  }
}

function writeTopologyLayoutCache(layout: Layout): void {
  if (typeof window === 'undefined') return
  try {
    const serialized = JSON.stringify({
      ...layout,
      positions: [...layout.positions.entries()],
    })
    window.localStorage.setItem(TOPOLOGY_LAYOUT_CACHE_KEY, serialized)
    window.sessionStorage.setItem(TOPOLOGY_LAYOUT_CACHE_KEY, serialized)
  } catch {
    // Optional cache only; the current React state remains authoritative.
  }
}

// Keep the last complete snapshot across route remounts and browser reloads.
let topologyResponseCache: any = readTopologySnapshot()
// Only hydrate a layout that was produced by the final DB-backed graph build.
// The raw topology endpoint can legitimately be one snapshot behind and must
// not be shown as a misleading one-node graph during normal navigation.
let topologyLayoutCache: Layout | null = readTopologyLayoutCache()

function mergeTopologyGraph(base: Layout | null, delta: { nodes: GraphNode[]; links: GraphLink[] }): { nodes: GraphNode[]; links: GraphLink[] } {
  if (!base) return { nodes: [...delta.nodes], links: [...delta.links] }
  const removedSyntheticIds = new Set(base.nodes
    .filter(node => node.type === 'port-summary' || String(node.id).startsWith('port-'))
    .map(node => node.id))
  const nodes = base.nodes
    .filter(node => !removedSyntheticIds.has(node.id))
    .map(node => ({ ...node }))
  const findNode = (candidate: GraphNode) => {
    // Exact identity must win. A multi-MAC port aggregate contains many
    // member IPs/MACs, so using those lists to match first can incorrectly
    // merge the aggregate into the first stale endpoint node.
    const exactId = nodes.find(node => node.id === candidate.id)
    if (exactId) return exactId
    const exactIdentity = nodes.find(node =>
      (candidate.ip && node.ip === candidate.ip) ||
      (candidate.mac && cleanMac(node.mac) === cleanMac(candidate.mac))
    )
    if (exactIdentity) return exactIdentity
    if (candidate.macCount && candidate.macCount > 1) return undefined
    return nodes.find(node =>
      (candidate.ips || []).some(ip => Boolean(ip) && ((node.ips || []).includes(ip) || node.ip === ip)) ||
      (candidate.macs || []).some(mac => Boolean(mac) && ((node.macs || []).some(value => cleanMac(value) === cleanMac(mac)) || cleanMac(node.mac) === cleanMac(mac))) ||
      (candidate.hostname && lower(node.hostname) === lower(candidate.hostname))
    )
  }
  const ids = new Map<string, string>()
  delta.nodes.forEach(candidate => {
    const existing = findNode(candidate)
    if (existing) {
      ids.set(candidate.id, existing.id)
      Object.assign(existing, {
        ...candidate,
        id: existing.id,
        hostname: candidate.hostname || existing.hostname,
        ip: candidate.ip || existing.ip,
        mac: candidate.mac || existing.mac,
        vendor: candidate.vendor || existing.vendor,
        model: candidate.model || existing.model,
        port: candidate.port || existing.port,
      })
    } else {
      nodes.push({ ...candidate })
      ids.set(candidate.id, candidate.id)
    }
  })

  // Cached layouts can already contain duplicate synthetic CPU cards from a
  // previous refresh. Canonicalize them before returning the merged graph.
  const aliases = new Map<string, string>()
  const canonicalNodes: GraphNode[] = []
  const cpuByMac = new Map<string, GraphNode>()
  nodes.forEach(node => {
    const cpuMac = node.type === 'cpu' ? cleanMac(node.mac, ...(node.macs || [])) : ''
    const existing = cpuMac ? cpuByMac.get(cpuMac) : undefined
    if (!existing) {
      canonicalNodes.push(node)
      if (cpuMac) cpuByMac.set(cpuMac, node)
      aliases.set(node.id, node.id)
      return
    }
    existing.ip ||= node.ip
    existing.mac ||= node.mac
    existing.macCount = Math.max(existing.macCount || 0, node.macCount || 0)
    existing.macs = unique([...(existing.macs || []), ...(node.macs || [])])
    existing.ips = unique([...(existing.ips || []), ...(node.ips || [])])
    existing.vlans = unique([...(existing.vlans || []), ...(node.vlans || [])])
    aliases.set(node.id, existing.id)
  })

  const remap = (id: string) => aliases.get(ids.get(id) || id) || ids.get(id) || id
  const links = base.links
    .filter(link => !removedSyntheticIds.has(link.from) && !removedSyntheticIds.has(link.to))
    .map(link => ({ ...link }))
  delta.links.forEach(candidate => {
    const from = remap(candidate.from)
    const to = remap(candidate.to)
    const existingIndex = links.findIndex(link =>
      ((link.from === from && link.to === to) || (link.from === to && link.to === from)) &&
      (link.source === candidate.source || link.localPort || candidate.localPort)
    )
    const merged = { ...candidate, from, to }
    if (existingIndex >= 0) {
      const existing = links[existingIndex]
      const candidateIsMacEvidence = candidate.source === 'MAC/ARP'
      const existingIsConfirmed = existing.confidence === 'CONFIRMED'
      // A refresh can return the same pair from MAC/ARP after LLDP/CDP.
      // Keep the confirmed infrastructure edge and only enrich it with the
      // switch-side port summary instead of changing its visual/source type.
      links[existingIndex] = existingIsConfirmed && candidateIsMacEvidence
        ? {
            ...existing,
            localPort: candidate.localPort || existing.localPort,
            macCount: candidate.macCount || existing.macCount,
          }
        : merged
    } else links.push(merged)
  })
  const uniqueLinks = new Map<string, GraphLink>()
  links.forEach(link => {
    const from = remap(link.from)
    const to = remap(link.to)
    if (!from || !to || from === to) return
    const key = [from, to].sort().join('|')
    const existing = uniqueLinks.get(key)
    if (existing) {
      if (link.source === 'MAC/ARP' && link.localPort) {
        uniqueLinks.set(key, {
          ...existing,
          localPort: link.localPort,
          macCount: link.macCount || existing.macCount,
        })
        return
      }
      if (existing.confidence !== 'CONFIRMED' && link.confidence === 'CONFIRMED') {
        uniqueLinks.set(key, {
          ...link,
          from,
          to,
          localPort: existing.localPort || link.localPort,
          macCount: existing.macCount || link.macCount,
        })
      }
      return
    }
    uniqueLinks.set(key, { ...link, from, to })
  })
  return { nodes: canonicalNodes, links: [...uniqueLinks.values()] }
}

export default function Topology() {
  const { t } = useI18n()
  const tr = t.topology
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const savedViewRef = useRef(readSavedView())
  // A cached layout can contain deleted or offline devices. Rebuild from the
  // current reachable inventory before rendering topology nodes.
  const [layout, setLayout] = useState<Layout | null>(topologyLayoutCache)
  const hasLayoutRef = useRef(topologyLayoutCache !== null)
  const liveLayoutRef = useRef<Layout | null>(null)
  const liveInventoryKeyRef = useRef('')
  const topologyRequestRef = useRef(false)
  const topologyTimestampRef = useRef<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedLink, setSelectedLink] = useState<GraphLink | null>(null)
  const [selectedNodeDetails, setSelectedNodeDetails] = useState<TopologyNodeDetails | null>(null)
  const [connectedNodeDetails, setConnectedNodeDetails] = useState<Record<string, TopologyNodeDetails>>({})
  const [selectedNodeLoading, setSelectedNodeLoading] = useState(false)
  const [selectedNodeError, setSelectedNodeError] = useState<string | null>(null)
  const [editingNode, setEditingNode] = useState<TopologyNodeDetails['device'] | null>(null)
  const [connectionsSearch, setConnectionsSearch] = useState('')
  const [hoverPreview, setHoverPreview] = useState<HoverPreview | null>(null)
  const deferredConnectionsSearch = useDeferredValue(connectionsSearch)
  const [zoom, setZoom] = useState(savedViewRef.current.zoom)
  const [panX, setPanX] = useState(savedViewRef.current.panX)
  const [panY, setPanY] = useState(savedViewRef.current.panY)
  const [viewRevision, setViewRevision] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const graphViewportRef = useRef<HTMLDivElement | null>(null)
  const graphFullscreenRef = useRef<HTMLDivElement | null>(null)
  const fitPendingRef = useRef(true)
  const draggingRef = useRef(false)
  const viewportSizeRef = useRef({ width: 0, height: 0 })
  const panStateRef = useRef<PanState>({ active: false, mode: 'canvas', startX: 0, startY: 0, originX: 0, originY: 0, moved: false })
  const suppressClickRef = useRef(false)
  const manualPositionsRef = useRef(new Map(savedViewRef.current.positions))
  const deferredSearch = useDeferredValue(search)
  const topologyQueryKey = ['snmp-topology'] as const
  const layoutTimestampRef = useRef<string | null>(null)
  const topologyGraphRef = useRef<Layout | null>(null)

  const applyTopologyLayout = useCallback((next: Layout, source: string, requestUrl: string, responseTimestamp: string | null, accepted: boolean, allowEmpty = false) => {
    console.debug('[TOPOLOGY-FE] setLayout', {
      source,
      requestUrl,
      responseTimestamp,
      previousLayoutTimestamp: layoutTimestampRef.current,
      nodes: next.nodes.length,
      links: next.links.length,
      accepted,
    })
    if (!accepted) return
    // A transient empty/partial response must never replace a complete graph
    // that is already available for route remounts and browser reloads.
    if (!allowEmpty && !isCompleteTopologyLayout(next) && isCompleteTopologyLayout(topologyLayoutCache)) {
      console.debug('[TOPOLOGY-FE] incomplete layout ignored', {
        source,
        nodes: next.nodes.length,
        links: next.links.length,
      })
      setLoading(false)
      setRefreshing(false)
      return
    }
    layoutTimestampRef.current = responseTimestamp || layoutTimestampRef.current
    const positions = new Map(next.positions)
    manualPositionsRef.current.forEach((position, nodeId) => {
      if (positions.has(nodeId)) positions.set(nodeId, position)
    })
    const preservedLayout = { ...next, positions }
    topologyGraphRef.current = preservedLayout
    topologyLayoutCache = preservedLayout
    queryClient.setQueryData(TOPOLOGY_LAYOUT_QUERY_KEY, preservedLayout)
    writeTopologyLayoutCache(preservedLayout)
    fitPendingRef.current = true
    setLayout(preservedLayout)
  }, [])

  const handleBack = useCallback(() => {
    if (window.history.length > 1) {
      window.history.back()
    } else {
      window.location.href = '/'
    }
  }, [])

  const loadTopology = useCallback(async (forceRefresh = false) => {
    const requestUrl = forceRefresh
      ? `/snmp/topology?refresh=true&requested_at=${Date.now()}`
      : '/snmp/topology'
    console.debug('[TOPOLOGY-FE] loadTopology', { forceRefresh, requestUrl })
    if (topologyRequestRef.current) {
      console.debug('[TOPOLOGY-FE] loadTopology ignored', { requestUrl, reason: 'request-in-flight' })
      return
    }
    // Hydrate a complete cached graph synchronously on route remount. This
    // avoids a loading flash and avoids re-running the normal GET after a
    // refresh has already populated React Query's cache.
    if (!forceRefresh) {
      const cachedLayout = topologyLayoutCache || queryClient.getQueryData<Layout>(TOPOLOGY_LAYOUT_QUERY_KEY)
      if (isCompleteTopologyLayout(cachedLayout)) {
        applyTopologyLayout(cachedLayout, 'route-remount layout hydration', '/snmp/topology', topologyTimestampRef.current, true)
        hasLayoutRef.current = true
        setLoading(false)
      }
      // Do not hydrate the raw topology response here. It can be one snapshot
      // behind and is only used as the API baseline for the DB-backed rebuild.
    }
    topologyRequestRef.current = true
    setError(null)
    if (hasLayoutRef.current) setRefreshing(true); else setLoading(true)
    try {
      const topologyResult = await queryClient.fetchQuery({
        queryKey: topologyQueryKey,
        // Revalidate the persisted backend snapshot on every mount. The
        // completed layout stays visible while this request is in flight.
        queryFn: () => requestJson<any>(requestUrl, { cache: 'no-store' }),
        staleTime: 0,
      })
      if (Array.isArray(topologyResult?.devices) && Array.isArray(topologyResult?.links)) {
        topologyResponseCache = topologyResult
        try {
          window.localStorage.setItem(TOPOLOGY_LAST_SNAPSHOT_KEY, JSON.stringify(topologyResult))
        } catch {
          // Storage can be disabled or full; React Query remains the fallback.
        }
      }
      const responseTimestamp = topologyResult?.timestamp || topologyResult?.collected_at || null
      console.debug('[TOPOLOGY-FE] topology response', {
        source: forceRefresh ? 'refresh GET' : 'normal GET',
        requestUrl,
        responseTimestamp,
        nodes: Array.isArray(topologyResult?.devices) ? topologyResult.devices.length : 0,
        links: Array.isArray(topologyResult?.links) ? topologyResult.links.length : 0,
        reactQueryCache: queryClient.getQueryData(topologyQueryKey),
      })
      if (!forceRefresh && responseTimestamp && topologyTimestampRef.current && responseTimestamp < topologyTimestampRef.current) {
        console.debug('[TOPOLOGY-FE] topology response ignored', {
          source: 'loadTopology',
          requestUrl,
          responseTimestamp,
          previousLayoutTimestamp: topologyTimestampRef.current,
          nodes: Array.isArray(topologyResult?.devices) ? topologyResult.devices.length : 0,
          links: Array.isArray(topologyResult?.links) ? topologyResult.links.length : 0,
          accepted: false,
        })
        // Do not abort here. The persisted topology timestamp can lag behind
        // the module snapshots; current DB-backed MAC/ARP collections below
        // still need to rebuild the connected-port graph.
      }
      // Device inventory is also persisted state. Avoid the generic GET
      // cache here so a status/identity change is visible after navigation.
      const inventoryResult = await requestJson<DeviceRecord[]>('/devices', { cache: 'no-store' })
      const storedInventoryResult = Array.isArray(inventoryResult) ? inventoryResult : []
      let storedInventory = storedInventoryResult
      // The SNMP Devices page reads the optimized paginated inventory route.
      // Some deployments expose different data through the legacy /devices
      // route, so do not discard a live topology just because that route is
      // empty. Use the same DB-backed inventory source as the device page.
      if (!storedInventory.length) {
        try {
          const snmpInventory = await requestJson<{ items?: DeviceRecord[] }>(
            '/snmp/devices?page=1&page_size=200&sort_by=id&sort_order=asc',
            { cache: 'no-store' },
          )
          if (Array.isArray(snmpInventory?.items)) storedInventory = snmpInventory.items
        } catch (snmpInventoryError) {
          if (import.meta.env.DEV) console.debug('[Topology] SNMP inventory fallback unavailable', snmpInventoryError)
        }
      }
      const inventoryKey = storedInventory
        .map((device) => String(device.id))
        .sort()
        .join(',')
      // The API intentionally serves cached topology on normal loads. Keep a
      // successful explicit live refresh authoritative until the inventory
      // itself changes; otherwise an older stored snapshot can overwrite the
      // graph a moment after it was refreshed.
      if (
        !forceRefresh &&
        topologyResult?.cached === true &&
        liveLayoutRef.current &&
        liveInventoryKeyRef.current === inventoryKey
      ) {
        applyTopologyLayout(liveLayoutRef.current, 'cached live layout', requestUrl, responseTimestamp, true)
        hasLayoutRef.current = true
        setLastUpdated(new Date())
        return
      }
      if (storedInventory.length === 0) {
        // The device inventory is authoritative. An empty inventory means
        // every cached topology node has been deleted and must be cleared.
        liveLayoutRef.current = null
        liveInventoryKeyRef.current = ''
        const emptyLayout = { nodes: [], links: [], positions: new Map<string, { x: number; y: number }>(), width: 1200, height: 650 }
        topologyLayoutCache = null
        topologyResponseCache = null
        topologyGraphRef.current = emptyLayout
        queryClient.removeQueries({ queryKey: topologyQueryKey })
        queryClient.removeQueries({ queryKey: TOPOLOGY_LAYOUT_QUERY_KEY })
        try {
          window.localStorage.removeItem(TOPOLOGY_LAST_SNAPSHOT_KEY)
          window.localStorage.removeItem(TOPOLOGY_LAYOUT_CACHE_KEY)
          window.sessionStorage.removeItem(TOPOLOGY_LAYOUT_CACHE_KEY)
        } catch {
          // Storage can be disabled; React state and query caches are cleared above.
        }
        applyTopologyLayout(emptyLayout, 'empty inventory', requestUrl, responseTimestamp, true, true)
        setSelectedNode(null)
        setSelectedLink(null)
        setSelectedNodeDetails(null)
        setConnectedNodeDetails({})
        setSelectedNodeLoading(false)
        setSelectedNodeError(null)
        hasLayoutRef.current = true
        setLastUpdated(new Date())
        return
      }
      // The device table is the authoritative source for topology visibility.
      // Do not gate a normal route load on a second ICMP request: a transient
      // ping timeout can hide every valid DB-backed device and leave only a
      // stale cached node on screen.
      const inventory = storedInventory.filter(device => device.status !== 'offline')
      const topologyNodes = (Array.isArray(topologyResult?.devices) ? topologyResult.devices : [])
        .filter((node: any) => Boolean(node?.ip_address) && inventory.some(device => device.ip_address === node.ip_address))
      const topologyLinks = Array.isArray(topologyResult?.links) ? topologyResult.links : []
      const infrastructureSources = [
        ...inventory.map((device, index) => makeNode(device, `inventory-${index}`)),
        ...topologyNodes.map((node: any, index: number) => {
          const match = inventoryMatch(node, inventory)
          return match ? makeNode({ ...match, ...node, id: match.id }, `managed-${match.id}`) : makeNode(node, `topology-${index}`)
        }),
      ]
      const root = infrastructureSources.find(node => node.type === 'switch')
        || infrastructureSources.find(node => node.type === 'router')
        || infrastructureSources.find(node => node.type === 'gateway')
        || infrastructureSources[0]

      // Normal loads use stored monitoring snapshots. Live SNMP collection is
      // reserved for the explicit REFRESH action.
      const storedCollections = (await Promise.allSettled(
        infrastructureSources
          .filter(source => Number.isFinite(Number(source.id)))
          .map(source => collectStoredDevice(source))
      ))
        .filter((result): result is PromiseFulfilledResult<DeviceCollection> => result.status === 'fulfilled')
        .map(result => result.value)
      // PORT SUMMARY reads the persisted MAC-table snapshot directly. Refresh
      // that same DB-backed snapshot for the core only so topology cannot lag
      // behind on newly learned ports while still avoiding a live SNMP walk.
      let currentStoredCollections = storedCollections
      if (root && Number.isFinite(Number(root.id))) {
        try {
          const currentMac = await collectModule(Number(root.id), 'mac', true)
          const coreMacEntries = unwrapRows(currentMac, ['entries', 'mac_entries'])
          const corePortGroups = unwrapRows(currentMac, ['port_groups'])
          currentStoredCollections = storedCollections.map(collection => collection.device.id === root.id
            ? { ...collection, macEntries: coreMacEntries, portGroups: corePortGroups }
            : collection)
        } catch (coreMacError) {
          if (import.meta.env.DEV) console.debug('[Topology] core MAC snapshot unavailable, using stored monitoring data', coreMacError)
        }
      }
      const liveCollections: DeviceCollection[] = []
      if (forceRefresh && root && Number.isFinite(Number(root.id))) {
        try {
          const firstCollection = await collectDevice(root, true)
          liveCollections.push(firstCollection)
          const remoteDevices = firstCollection.lldpNeighbors
            .map(normalizeLldp)
            .map(remote => inventory.find(device =>
              (remote.remoteIp && device.ip_address === remote.remoteIp) ||
              (remote.remoteMac && cleanMac(device.mac_address) === cleanMac(remote.remoteMac)) ||
              (remote.remoteHostname && lower(device.hostname) === lower(remote.remoteHostname))
            ))
            .filter(Boolean) as DeviceRecord[]
          const extraSources = unique(remoteDevices.map(device => device.id))
            .map(id => infrastructureSources.find(node => Number(node.id) === id) || makeNode(inventory.find(device => device.id === id), `managed-${id}`))
          const extraCollections = await Promise.all(
            extraSources
              .filter(source => source.id !== root.id)
              .filter(source => Number.isFinite(Number(source.id)))
              .map(source => collectDevice(source))
          )
          liveCollections.push(...extraCollections)
        } catch (collectionError) {
          if (import.meta.env.DEV) {
            console.debug('[Topology] live collection failed, falling back to cached topology', collectionError)
          }
        }
      }
      const liveTopologyEvidence = liveCollections.some(collection =>
        collection.macEntries.length > 0 ||
        collection.arpEntries.length > 0 ||
        collection.lldpNeighbors.length > 0 ||
        collection.routes.length > 0 ||
        collection.portGroups.length > 0,
      )
      // The backend clears its persisted topology snapshot for a forced
      // refresh. Use the fresh collection as the source of truth instead of
      // allowing older stored module snapshots to repopulate stale links.
      const allCollections = forceRefresh && liveTopologyEvidence ? liveCollections : currentStoredCollections
      const result = buildGraph(allCollections, inventory, topologyNodes, topologyLinks)
      const mergedGraph = result
      const nextLayout = layoutGraph(mergedGraph.nodes, mergedGraph.links)
      if (forceRefresh && liveTopologyEvidence && root && Number.isFinite(Number(root.id))) {
        try {
          const collectedAt = new Date().toISOString()
          await persistSNMPTopologySnapshot(Number(root.id), {
            devices: mergedGraph.nodes,
            links: mergedGraph.links,
            collected_at: collectedAt,
            source: 'live_refresh',
          })
          const latestSnapshot = {
            devices: mergedGraph.nodes,
            links: mergedGraph.links,
            timestamp: collectedAt,
            collected_at: collectedAt,
            cached: true,
          }
          console.debug('[TOPOLOGY-FE] React Query cache update', {
            source: 'persist_snmp_topology_snapshot',
            requestUrl: '/snmp/topology/snapshot',
            responseTimestamp: collectedAt,
            nodes: latestSnapshot.devices.length,
            links: latestSnapshot.links.length,
            previousLayoutTimestamp: layoutTimestampRef.current,
            accepted: true,
          })
          queryClient.setQueryData(topologyQueryKey, latestSnapshot)
          topologyResponseCache = latestSnapshot
          try {
            window.localStorage.setItem(TOPOLOGY_LAST_SNAPSHOT_KEY, JSON.stringify(latestSnapshot))
          } catch {
            // Keep the in-memory/query caches when browser storage is unavailable.
          }
          topologyTimestampRef.current = collectedAt
          const persistedSnapshot = await queryClient.fetchQuery({
            queryKey: topologyQueryKey,
            queryFn: () => requestJson<any>('/snmp/topology', { cache: 'no-store' }),
            staleTime: 0,
          })
          const persistedTimestamp = persistedSnapshot?.timestamp || persistedSnapshot?.collected_at
          console.debug('[TOPOLOGY-FE] persisted topology refetch', {
            source: 'post-refresh GET',
            requestUrl: '/snmp/topology',
            responseTimestamp: persistedTimestamp || null,
            nodes: Array.isArray(persistedSnapshot?.devices) ? persistedSnapshot.devices.length : 0,
            links: Array.isArray(persistedSnapshot?.links) ? persistedSnapshot.links.length : 0,
            previousLayoutTimestamp: layoutTimestampRef.current,
            accepted: Boolean(persistedTimestamp && persistedTimestamp >= collectedAt),
          })
          if (persistedTimestamp && persistedTimestamp >= collectedAt) {
            topologyTimestampRef.current = persistedTimestamp
            queryClient.setQueryData(topologyQueryKey, persistedSnapshot)
            topologyResponseCache = persistedSnapshot
            try {
              window.localStorage.setItem(TOPOLOGY_LAST_SNAPSHOT_KEY, JSON.stringify(persistedSnapshot))
            } catch {
              // Keep the in-memory/query caches when browser storage is unavailable.
            }
          }
        } catch (snapshotError) {
          if (import.meta.env.DEV) {
            console.debug('[Topology] live snapshot persistence failed', snapshotError)
          }
        }
      }
      applyTopologyLayout(nextLayout, forceRefresh ? 'live refresh graph' : 'persisted topology graph', requestUrl, responseTimestamp, true)
      if (forceRefresh && liveTopologyEvidence) {
        liveLayoutRef.current = nextLayout
        liveInventoryKeyRef.current = inventoryKey
      }
      hasLayoutRef.current = true
      setLastUpdated(new Date())
      if (import.meta.env.DEV) {
        console.debug('[Topology] correlated live sources', {
          devices: mergedGraph.nodes.length,
          mac: allCollections.reduce((count, item) => count + item.macEntries.length, 0),
          arp: allCollections.reduce((count, item) => count + item.arpEntries.length, 0),
          lldp: allCollections.reduce((count, item) => count + item.lldpNeighbors.length, 0),
          routes: allCollections.reduce((count, item) => count + item.routes.length, 0),
          links: mergedGraph.links.length,
        })
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Topology data unavailable')
    } finally {
      setLoading(false)
      setRefreshing(false)
      topologyRequestRef.current = false
    }
  }, [])

  const refreshTopology = useCallback(() => {
    console.debug('[TOPOLOGY-FE] refreshTopology', { source: 'REFRESH button' })
    // Start a true rebuild: clear browser snapshots before the backend clears
    // its persisted topology JSON, so stale links cannot flash back on screen.
    topologyResponseCache = null
    topologyLayoutCache = null
    topologyGraphRef.current = null
    liveLayoutRef.current = null
    liveInventoryKeyRef.current = ''
    queryClient.removeQueries({ queryKey: topologyQueryKey })
    queryClient.removeQueries({ queryKey: TOPOLOGY_LAYOUT_QUERY_KEY })
    try {
      window.localStorage.removeItem(TOPOLOGY_LAST_SNAPSHOT_KEY)
      window.localStorage.removeItem(TOPOLOGY_LAYOUT_CACHE_KEY)
      window.sessionStorage.removeItem(TOPOLOGY_LAYOUT_CACHE_KEY)
    } catch {
      // Browser storage is optional; the in-memory/query caches are cleared above.
    }
    return loadTopology(true)
  }, [loadTopology])

  const saveNode = useCallback(async (values: Record<string, string>) => {
    if (!editingNode) return
    const saved = await updateDevice(editingNode.id, {
      hostname: values.hostname,
      ip_address: values.ip_address,
      mac_address: values.mac_address,
      model: values.model,
      serial_number: values.serial_number,
      firmware_version: values.firmware,
      status: values.status,
      vendor_name: values.vendor,
      topology_metadata: {
        port: values.port,
        vlans: values.vlans.split(',').map(value => value.trim()).filter(Boolean),
        ips: values.ips.split(',').map(value => value.trim()).filter(Boolean),
      },
    })
    setSelectedNodeDetails(current => current ? {
      ...current,
      device: { ...current.device, ...saved, firmware: saved.firmware_version },
    } : current)
    setEditingNode(null)
    // The edited device is already persisted in the database; do not wait for
    // a full live SNMP topology walk just to render the saved fields.
    await loadTopology()
  }, [editingNode, loadTopology])

  useEffect(() => {
    console.debug('[TOPOLOGY-FE] component mount/remount', {
      reactQueryCache: queryClient.getQueryData(topologyQueryKey),
      previousLayoutTimestamp: layoutTimestampRef.current,
    })
    // Cache clearing removes only browser snapshots. Rehydrate from the
    // server snapshot/stored monitoring data first; a live SNMP walk is
    // reserved for the explicit UPDATE TOPOLOGY action.
    void loadTopology(false)
  }, [loadTopology])

  useEffect(() => {
    // Keep the graph current while the topology route remains open. The
    // request-in-flight guard in loadTopology prevents overlapping SNMP walks.
    const refreshTimer = window.setInterval(() => {
      void loadTopology(true)
    }, TOPOLOGY_AUTO_REFRESH_MS)
    return () => window.clearInterval(refreshTimer)
  }, [loadTopology])

  useEffect(() => {
    const nodeId = Number(selectedNode?.id)
    if (!selectedNode || !Number.isFinite(nodeId)) {
      setSelectedNodeDetails(null)
      setSelectedNodeLoading(false)
      setSelectedNodeError(null)
      return
    }

    let cancelled = false
    setSelectedNodeLoading(true)
    setSelectedNodeError(null)

    void requestJson<TopologyNodeDetails>(`/snmp/devices/${nodeId}`)
      .then(result => {
        if (cancelled) return
        setSelectedNodeDetails(result)
      })
      .catch(error => {
        if (cancelled) return
        setSelectedNodeDetails(null)
        setSelectedNodeError(error instanceof Error ? error.message : 'Device details unavailable')
      })
      .finally(() => {
        if (!cancelled) setSelectedNodeLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedNode])

  useEffect(() => {
    if (!selectedNode || !layout) {
      setConnectedNodeDetails({})
      return
    }

    const neighborIds = unique(
      layout.links
        .filter(link => link.from === selectedNode.id || link.to === selectedNode.id)
        .map(link => link.from === selectedNode.id ? link.to : link.from)
        .filter(id => Number.isFinite(Number(id)))
    )

    if (!neighborIds.length) {
      setConnectedNodeDetails({})
      return
    }

    let cancelled = false

    void Promise.all(
      neighborIds.map(async id => {
        try {
          const result = await requestJson<TopologyNodeDetails>(`/snmp/devices/${Number(id)}`)
          return [id, result] as const
        } catch {
          return [id, null] as const
        }
      })
    ).then(entries => {
      if (cancelled) return
      const next: Record<string, TopologyNodeDetails> = {}
      entries.forEach(([id, result]) => {
        if (result) next[id] = result
      })
      setConnectedNodeDetails(next)
    })

    return () => {
      cancelled = true
    }
  }, [layout, selectedNode])

  const visible = useMemo(() => {
    if (!layout) return { nodes: [], links: [] as GraphLink[] }
    const query = deferredSearch.trim().toLowerCase()
    const core = findCoreNode(layout.nodes, layout.links)

    // The graph view must show the complete discovered topology. PORT SUMMARY
    // intentionally reduces this to one MAC/ARP relationship per core port,
    // but filtering those links here hides valid LLDP/CDP and routing paths.
    const openLinks = layout.links.filter(isRenderableConnectedLink)
    // Persisted snapshots can contain numeric endpoint IDs while normalized
    // graph nodes use strings. Compare canonical strings or the graph appears
    // empty even though the layout contains valid nodes and links.
    const connectedIds = new Set([...(core ? [core.id] : []), ...openLinks.flatMap(link => [link.from, link.to])].map(String))
    // A valid inventory can exist before SNMP discovers any relationship. In
    // that state links are empty, so show the DB-backed devices instead of
    // hiding the whole page behind the connected-node filter.
    const graphNodes = openLinks.length
      ? layout.nodes.filter(node => connectedIds.has(String(node.id)))
      : layout.nodes
    const nodes = graphNodes
      .filter(node => !query || `${node.hostname} ${node.ip} ${node.mac} ${node.port || ''} ${(node.ips || []).join(' ')}`.toLowerCase().includes(query))
    const ids = new Set(nodes.map(node => node.id))
    return { nodes, links: openLinks.filter(link => ids.has(String(link.from)) && ids.has(String(link.to))) }
  }, [deferredSearch, layout])

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

  const coreConnections = useMemo(() => {
    if (!layout) return { node: null as GraphNode | null, links: [] as GraphLink[] }
    const node = findCoreNode(layout.nodes, layout.links)
    if (!node) return { node: null, links: [] }
    // PORT SUMMARY is based on MAC/ARP port groups. Routing links describe an
    // uplink path, not an attached device port, so they must not appear here.
    // Keep one card per physical core port even when several records share it.
    const coreId = String(node.id)
    const connectedPorts = new Map<string, GraphLink>()
    layout.links.forEach(link => {
      const from = String(link.from)
      const to = String(link.to)
      if (from !== coreId && to !== coreId) return
      if (link.source !== 'MAC/ARP' || link.gatewayPath || !isRenderableConnectedLink(link)) return
      const localPort = from === coreId ? link.localPort : link.remotePort
      const key = portKey(localPort)
      if (!key || !localPort || connectedPorts.has(key)) return
      connectedPorts.set(key, link)
    })
    return { node, links: [...connectedPorts.values()] }
  }, [layout])

  const highlightedLinkIds = useMemo(() => {
    if (!layout) return new Set<string>()
    if (selectedLink) return new Set([selectedLink.id])
    if (!selectedNode) return new Set<string>()
    return new Set(
      layout.links
        .filter(link => link.from === selectedNode.id || link.to === selectedNode.id)
        .map(link => link.id)
    )
  }, [layout, selectedLink, selectedNode])

  const startPan = useCallback((clientX: number, clientY: number) => {
    draggingRef.current = true
    panStateRef.current = {
      active: true,
      mode: 'canvas',
      startX: clientX,
      startY: clientY,
      originX: panX,
      originY: panY,
      moved: false,
    }
    setDragging(true)
  }, [panX, panY])

  const startNodeDrag = useCallback((node: GraphNode, clientX: number, clientY: number) => {
    const origin = layout?.positions.get(node.id)
    if (!origin) return
    draggingRef.current = true
    panStateRef.current = {
      active: true,
      mode: 'node',
      startX: clientX,
      startY: clientY,
      originX: panX,
      originY: panY,
      nodeId: node.id,
      nodeOrigin: origin,
      moved: false,
    }
    setDragging(true)
  }, [layout, panX, panY])

  const updatePan = useCallback((clientX: number, clientY: number) => {
    if (!panStateRef.current.active) return
    const deltaX = clientX - panStateRef.current.startX
    const deltaY = clientY - panStateRef.current.startY
    if (!panStateRef.current.moved && Math.hypot(deltaX, deltaY) < 4) return
    panStateRef.current.moved = true
    if (panStateRef.current.mode === 'node' && panStateRef.current.nodeId && panStateRef.current.nodeOrigin) {
      const nextPosition = {
        x: panStateRef.current.nodeOrigin.x + deltaX / zoom,
        y: panStateRef.current.nodeOrigin.y + deltaY / zoom,
      }
      manualPositionsRef.current.set(panStateRef.current.nodeId, nextPosition)
      setViewRevision(value => value + 1)
      setLayout(current => {
        if (!current) return current
        const positions = new Map(current.positions)
        positions.set(panStateRef.current.nodeId!, nextPosition)
        const next = { ...current, positions }
        topologyGraphRef.current = next
        return next
      })
      return
    }
    setPanX(panStateRef.current.originX + deltaX / zoom)
    setPanY(panStateRef.current.originY + deltaY / zoom)
  }, [zoom])

  const endPan = useCallback(() => {
    draggingRef.current = false
    if (panStateRef.current.mode === 'node' && panStateRef.current.moved) suppressClickRef.current = true
    panStateRef.current.active = false
    setDragging(false)
  }, [])

  const resetView = useCallback(() => {
    manualPositionsRef.current.clear()
    setZoom(1)
    setPanX(0)
    setPanY(0)
    setViewRevision(value => value + 1)
  }, [])

  const fitView = useCallback(() => {
    if (!layout || !graphViewportRef.current || !layout.positions.size) return
    const rect = graphViewportRef.current.getBoundingClientRect()
    const points = [...layout.positions.values()]
    const minX = Math.min(...points.map(point => point.x)) - 120
    const maxX = Math.max(...points.map(point => point.x)) + 120
    const minY = Math.min(...points.map(point => point.y)) - 60
    const maxY = Math.max(...points.map(point => point.y)) + 60
    const svgScale = Math.min(rect.width / layout.width, rect.height / layout.height)
    const fitZoom = Math.max(
      MIN_ZOOM,
      Math.min(
        DEFAULT_FIT_MAX_ZOOM,
        (rect.width - 32) / ((maxX - minX) * svgScale),
        (rect.height - 32) / ((maxY - minY) * svgScale),
      ),
    )
    setZoom(+fitZoom.toFixed(2))
    setPanX((layout.width / 2) - ((minX + maxX) / 2) * fitZoom)
    setPanY((layout.height / 2) - ((minY + maxY) / 2) * fitZoom)
  }, [layout])

  const focusNode = useCallback((node: GraphNode) => {
    if (!layout) return
    const nextZoom = Math.max(1, Math.min(MAX_ZOOM, 1.35))
    setZoom(nextZoom)
    setPanX(layout.width / 2 - (layout.positions.get(node.id)?.x || layout.width / 2) * nextZoom)
    setPanY(layout.height / 2 - (layout.positions.get(node.id)?.y || layout.height / 2) * nextZoom)
  }, [layout])

  const zoomAt = useCallback((nextZoom: number, clientX?: number, clientY?: number) => {
    const bounded = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, nextZoom))
    if (!graphViewportRef.current || !layout) {
      setZoom(bounded)
      return
    }
    const rect = graphViewportRef.current.getBoundingClientRect()
    const anchorX = clientX ?? rect.left + rect.width / 2
    const anchorY = clientY ?? rect.top + rect.height / 2
    const cursorX = ((anchorX - rect.left) / rect.width) * layout.width
    const cursorY = ((anchorY - rect.top) / rect.height) * layout.height
    setPanX(current => current + (cursorX - current) * (1 - bounded / zoom))
    setPanY(current => current + (cursorY - current) * (1 - bounded / zoom))
    setZoom(bounded)
  }, [layout, zoom])

  const toggleFullscreen = useCallback(async () => {
    if (!document.fullscreenElement) await graphFullscreenRef.current?.requestFullscreen()
    else await document.exitFullscreen()
  }, [])

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === graphFullscreenRef.current)
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  useEffect(() => {
    if (!isFullscreen) return
    const frame = window.requestAnimationFrame(() => fitView())
    return () => window.cancelAnimationFrame(frame)
  }, [fitView, isFullscreen])

  useEffect(() => {
    if (!layout || !fitPendingRef.current) return
    fitPendingRef.current = false
    const frame = window.requestAnimationFrame(() => fitView())
    return () => window.cancelAnimationFrame(frame)
  }, [fitView, layout])

  useEffect(() => {
    const viewport = graphViewportRef.current
    if (!viewport) return
    const observer = new ResizeObserver(() => {
      if (draggingRef.current) return
      const { width, height } = viewport.getBoundingClientRect()
      if (width === viewportSizeRef.current.width && height === viewportSizeRef.current.height) return
      viewportSizeRef.current = { width, height }
      window.requestAnimationFrame(() => fitView())
    })
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [fitView])

  useEffect(() => {
    const viewport = graphViewportRef.current
    if (!viewport) return
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault()
      zoomAt(zoom * (event.deltaY < 0 ? 1.1 : 0.9), event.clientX, event.clientY)
    }
    viewport.addEventListener('wheel', handleWheel, { passive: false })
    return () => viewport.removeEventListener('wheel', handleWheel)
  }, [zoom, zoomAt])

  useEffect(() => {
    try {
      window.sessionStorage.setItem(VIEW_STATE_KEY, JSON.stringify({
        zoom,
        panX,
        panY,
        positions: [...manualPositionsRef.current.entries()],
      }))
    } catch {
      // View persistence is best-effort and must never affect topology rendering.
    }
  }, [panX, panY, viewRevision, zoom])

  const colorFor = (type: DeviceType) => {
    if (type === 'gateway' || type === 'router') return '#a78bfa'
    if (type === 'firewall') return '#fb7185'
    if (type === 'switch') return '#22d3ee'
    if (type === 'access-point') return '#c084fc'
    if (type === 'cpu') return '#f97316'
    if (type === 'port-summary') return '#fbbf24'
    return '#34d399'
  }

  const card = (node: GraphNode, point: { x: number; y: number }) => {
    const safeType = String(node.type || 'unknown')
    const safeIp = String(node.ip || '')
    const safePort = String(node.port || '')
    const safeMac = String(node.mac || node.macs?.[0] || '')
    const identityLabel = safeMac || 'MAC UNKNOWN'
    const infra = ['gateway', 'router', 'firewall', 'switch', 'access-point', 'cpu', 'port-summary'].includes(safeType)
    const color = colorFor(safeType as DeviceType)
    const width = infra ? 210 : 188
    const height = infra ? 90 : 82
    const x = point.x - width / 2
    const y = point.y - height / 2
    const selected = selectedNode?.id === node.id
    const detail = node.macCount && node.macCount > 1 ? `${node.macCount} MACs · ${(node.ips || []).length} IPs` : safeMac || 'UNKNOWN'
    return (
      <g
        key={node.id}
        data-topology-node="true"
        onPointerDown={(event) => {
          event.stopPropagation()
          event.currentTarget.setPointerCapture(event.pointerId)
          startNodeDrag(node, event.clientX, event.clientY)
        }}
        onPointerUp={(event) => {
          event.stopPropagation()
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
          endPan()
        }}
        onClick={() => {
          if (suppressClickRef.current) {
            suppressClickRef.current = false
            return
          }
          setSelectedNode(prev => prev?.id === node.id ? null : node)
          setSelectedLink(null)
        }}
        onDoubleClick={() => focusNode(node)}
        style={{ cursor: 'pointer' }}
      >
        <rect x={x} y={y} width={width} height={height} rx="12" fill="#071321" stroke={color} strokeWidth={selected ? 3 : 1.5} />
        <circle cx={x + width - 13} cy={y + 13} r="4" fill={node.status === 'online' ? '#34d399' : node.status === 'warning' ? '#fbbf24' : '#fb7185'} />
        <text x={x + 14} y={y + 23} className="font-mono" style={{ fill: color, fontSize: 10, fontWeight: 700 }}>{safeType === 'port-summary' ? 'PORT SUMMARY' : safeType.toUpperCase()}</text>
        <text x={x + 14} y={y + 43} className="font-mono" style={{ fill: '#e2e8f0', fontSize: 11, fontWeight: 700 }}>{identityLabel}</text>
        <text x={x + 14} y={y + 59} className="font-mono" style={{ fill: '#8ca0bb', fontSize: 10 }}>{safeIp || (safePort ? `Port ${safePort}` : 'IP UNKNOWN')}</text>
        <text x={x + 14} y={y + 74} className="font-mono" style={{ fill: '#64748b', fontSize: 8 }}>{detail}</text>
      </g>
    )
  }

  if (layout && layout.nodes.length === 0) {
    return (
      <div className="p-3 md:p-5 space-y-3 h-full flex flex-col" style={{ background: 'radial-gradient(circle at 50% 0%, rgba(34,211,238,.06), transparent 48%)' }}>
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-base" style={{ color: '#8899bb' }}>
            No devices found. Add a device to start monitoring.
          </div>
        </GlassCard>
      </div>
    )
  }

  return (
    <div className="p-3 md:p-5 space-y-3 h-full flex flex-col" style={{ background: 'radial-gradient(circle at 50% 0%, rgba(34,211,238,.06), transparent 48%)' }}>
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl tracking-widest neon-cyan">{tr.title}</h1>
          <p className="font-mono text-[10px]" style={{ color: '#8ca0bb' }}>{tr.subtitle}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={handleBack}
            className="glass-bright rounded px-3 py-2 text-xs font-mono transition-opacity hover:opacity-80"
            style={{ color: '#c084fc', border: '1px solid rgba(192,132,252,.2)' }}
            aria-label={tr.back}
            title={tr.back}
          >
            ← {tr.back}
          </button>
          <span className="font-mono text-[10px]" style={{ color: '#64748b' }}>{lastUpdated ? `${tr.updated} ${lastUpdated.toLocaleString()}` : tr.notLoaded}</span>
          <input value={search} onChange={event => setSearch(event.target.value)} placeholder={tr.search} className="glass-bright rounded px-3 py-2 text-xs font-mono outline-none" style={{ color: 'var(--t-text, #c8d8ee)', border: '1px solid rgba(34,211,238,.2)' }} />
          <button type="button" onClick={() => void refreshTopology()} className="glass-bright rounded px-3 py-2 text-xs font-mono" style={{ color: '#22d3ee' }}>{refreshing ? tr.rebuilding : tr.rebuild}</button>
        </div>
      </div>

      {error && <div className="font-mono text-xs rounded p-3" style={{ color: '#fb7185', background: 'rgba(127,29,29,.2)', border: '1px solid rgba(251,113,133,.2)' }}>{error}</div>}

      <GlassCard className="p-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <Metric label={tr.nodes} value={counts.nodes} />
        <Metric label={tr.links} value={counts.links} />
        <Metric label={tr.confirmed} value={counts.confirmed} color="#22d3ee" />
        <Metric label={tr.inferred} value={counts.inferred} color="#fbbf24" />
        <Metric label={tr.macsOnPorts} value={counts.mac} color="#34d399" />
        <Metric label={tr.portGroups} value={counts.endpoints} color="#34d399" />
        <div className="ml-auto flex items-center gap-2 font-mono text-[10px]" style={{ color: '#64748b' }}>
          <span>{tr.autoRefreshOff}</span>
          <button type="button" onClick={resetView} className="rounded px-2 py-1" style={{ color: '#22d3ee', border: '1px solid rgba(34,211,238,.2)' }}>
            {tr.resetView}
          </button>
          <button type="button" onClick={() => { setSelectedNode(null); setSelectedLink(null) }} className="rounded px-2 py-1" style={{ color: '#c084fc', border: '1px solid rgba(192,132,252,.2)' }}>
            {tr.clearSelection}
          </button>
        </div>
      </GlassCard>

      {coreConnections.node && coreConnections.links.length > 0 && (
        <GlassCard className="p-3">
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="font-display text-xs tracking-wider" style={{ color: '#22d3ee' }}>{tr.coreConnections}</div>
            <div className="font-mono text-[10px]" style={{ color: '#64748b' }}>{coreConnections.node.hostname} · {coreConnections.node.ip || tr.ipUnknown}</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
            {coreConnections.links.map((link, index) => {
              const coreId = String(coreConnections.node!.id)
              const fromIsCore = String(link.from) === coreId
              const remoteId = fromIsCore ? link.to : link.from
              const remote = layout?.nodes.find(node => String(node.id) === String(remoteId))
              const localPort = fromIsCore ? link.localPort : link.remotePort
              const remotePort = fromIsCore ? link.remotePort : link.localPort
              const tone = link.confidence === 'CONFIRMED' ? '#22d3ee' : link.gatewayPath ? '#a78bfa' : '#fbbf24'
              return (
                <button key={linkRenderKey(link, index, 'core-connection')} type="button" onClick={() => { setSelectedNode(remote || coreConnections.node); setSelectedLink(null) }} className="rounded p-2 text-left" style={{ color: '#dbeafe', background: 'rgba(8,25,55,.55)', border: `1px solid ${tone}44` }}>
                  <div className="font-mono text-[10px]" style={{ color: tone }}>{remote?.hostname || remote?.ip || remoteId}</div>
                  <div className="font-mono text-[9px] mt-1" style={{ color: '#94a3b8' }}>{remote?.ip || tr.ipUnknown} · {localPort || tr.portUnknown} → {destinationPortLabel(remotePort)}</div>
                  <div className="font-mono text-[9px] mt-1" style={{ color: '#64748b' }}>{link.source} · {link.confidence}</div>
                </button>
              )
            })}
          </div>
        </GlassCard>
      )}

      <div ref={graphFullscreenRef} className="flex-1 min-h-[650px] overflow-hidden relative rounded-xl" style={isFullscreen ? { width: '100vw', height: '100vh', background: '#030a14' } : undefined}>
      <GlassCard className="h-full overflow-hidden relative p-0">
        <div className="absolute left-3 top-3 z-10 flex gap-1 rounded-lg p-1" style={{ background: 'rgba(3,10,20,.9)', border: '1px solid rgba(34,211,238,.18)' }}>
          <button type="button" onClick={() => zoomAt(zoom + .1)} className="px-3 py-1.5 font-mono text-sm" style={{ color: '#22d3ee' }} aria-label={tr.zoomIn}>+</button>
          <button type="button" onClick={() => zoomAt(zoom - .1)} className="px-3 py-1.5 font-mono text-sm" style={{ color: '#22d3ee' }} aria-label={tr.zoomOut}>−</button>
          <button type="button" onClick={fitView} className="px-2 py-1.5 font-mono text-[9px]" style={{ color: '#8ca0bb' }}>{tr.fit}</button>
          <button type="button" onClick={resetView} className="px-2 py-1.5 font-mono text-[9px]" style={{ color: '#8ca0bb' }}>{tr.reset}</button>
          <button type="button" onClick={() => void toggleFullscreen()} className="px-2 py-1.5 font-mono text-[9px]" style={{ color: '#c084fc' }}>{isFullscreen ? tr.exitFullscreen : tr.fullscreen}</button>
        </div>
        <div className="absolute right-3 top-3 z-10 font-mono text-[10px] px-2 py-1 rounded" style={{ color: '#8ca0bb', background: 'rgba(3,10,20,.9)', border: '1px solid rgba(34,211,238,.12)' }}>{visible.nodes.length} NODES · {visible.links.length} LINKS</div>
        {(selectedNode || selectedLink) && (
          <div
            className="absolute right-0 top-0 z-20 h-full w-full max-w-[420px] overflow-y-auto"
            style={{ background: 'linear-gradient(180deg, rgba(3,10,20,.98), rgba(5,18,32,.96))', borderLeft: '1px solid rgba(34,211,238,.12)' }}
          >
            <div className="sticky top-0 flex items-center justify-between px-4 py-3" style={{ background: 'rgba(3,10,20,.96)', borderBottom: '1px solid rgba(34,211,238,.1)' }}>
              <div>
                <div className="font-display font-bold text-sm tracking-wider" style={{ color: selectedNode ? '#22d3ee' : '#c084fc' }}>
                  {selectedNode ? tr.deviceDetails : tr.linkDetails}
                </div>
                <div className="font-mono text-[10px]" style={{ color: '#64748b' }}>
                  {selectedNode ? (selectedNode.hostname || selectedNode.ip || selectedNode.id) : (selectedLink?.source || tr.topologyLink)}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedNode(null)
                  setSelectedLink(null)
                }}
                className="rounded px-2 py-1 font-mono text-[10px]"
                style={{ color: '#c084fc', border: '1px solid rgba(192,132,252,.2)' }}
              >
                CLOSE
              </button>
            </div>
            <div className="p-4">
              {selectedNode && (
                <NodeDetails
                  node={selectedNode}
                  links={layout?.links || []}
                  nodes={layout?.nodes || []}
                  onLink={setSelectedLink}
                  onNodeSelect={(remoteNode) => {
                    setSelectedNode(remoteNode)
                    setSelectedLink(null)
                  }}
                  onOpenDeviceDetails={(deviceId) => navigate(`/snmp/devices/${deviceId}`)}
                  onEditDevice={deviceDetails => setEditingNode(deviceDetails)}
                  connectionsSearch={connectionsSearch}
                  onConnectionsSearch={setConnectionsSearch}
                  deferredConnectionsSearch={deferredConnectionsSearch}
                  details={selectedNodeDetails}
                  connectedDetails={connectedNodeDetails}
                  loading={selectedNodeLoading}
                  error={selectedNodeError}
                />
              )}
              {selectedLink && (
                <LinkDetails
                  link={selectedLink}
                  nodes={layout?.nodes || []}
                  onNodeSelect={(remoteNode) => {
                    setSelectedNode(remoteNode)
                    setSelectedLink(null)
                  }}
                  onOpenDeviceDetails={(deviceId) => navigate(`/snmp/devices/${deviceId}`)}
                />
              )}
            </div>
          </div>
        )}

        {!layout ? (
          <div className="h-full flex items-center justify-center font-mono text-sm" style={{ color: '#8899bb' }}>{tr.noSnapshot}</div>
        ) : layout ? (
          <div
            ref={graphViewportRef}
            className="h-full overflow-auto relative"
            style={{ background: 'radial-gradient(circle at 50% 20%, rgba(34,211,238,.035), transparent 55%)', cursor: dragging ? 'grabbing' : 'grab', overscrollBehavior: 'contain', touchAction: 'none', userSelect: 'none' }}
            onPointerDown={(event) => {
              if ((event.target as HTMLElement).closest('button, [data-topology-interactive]')) return
              event.currentTarget.setPointerCapture(event.pointerId)
              startPan(event.clientX, event.clientY)
            }}
            onPointerMove={(event) => updatePan(event.clientX, event.clientY)}
            onPointerUp={(event) => {
              if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
              endPan()
            }}
            onPointerCancel={endPan}
            onPointerLeave={endPan}
          >
            <svg width="100%" height="100%" viewBox={`0 0 ${layout.width} ${layout.height}`} preserveAspectRatio="xMidYMid meet" style={{ display: 'block' }}>
              <defs>
                <filter id="topologyGlow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              </defs>
              <g
                transform={`translate(${panX} ${panY}) scale(${zoom})`}
                style={{ transition: dragging ? 'none' : 'transform 160ms ease-out', willChange: 'transform' }}
              >
              {visible.links.map((link, index) => {
                const from = layout.positions.get(link.from)
                const to = layout.positions.get(link.to)
                if (!from || !to) return null
                const fromNode = layout.nodes.find(node => node.id === link.from)
                const toNode = layout.nodes.find(node => node.id === link.to)
                const rootPort = layout.rootId && link.from === layout.rootId ? link.localPort : layout.rootId && link.to === layout.rootId ? link.remotePort : link.localPort
                // MAC/ARP links are built from the source switch's port
                // summary, so localPort is the actual switch-side port. Do
                // not replace it with the neighbor's eth0/remote port just
                // because layoutGraph selected that neighbor as its root.
                const displayPort = link.source === 'MAC/ARP'
                  ? link.localPort || link.remotePort
                  : rootPort || link.localPort || link.remotePort
                const color = link.gatewayPath ? '#a78bfa' : link.wireless ? '#c084fc' : link.confidence === 'CONFIRMED' ? '#22d3ee' : '#fbbf24'
                const selected = selectedLink?.id === link.id
                const highlighted = highlightedLinkIds.has(link.id)
                const startY = from.y < to.y ? from.y + 45 : from.y - 45
                const endY = from.y < to.y ? to.y - 45 : to.y + 45
                const midY = (startY + endY) / 2
                const destinationLabelX = from.x + (to.x - from.x) * 0.82
                const destinationLabelY = startY + (endY - startY) * 0.82
                return (
                  <g
                    key={linkRenderKey(link, index, 'graph-link')}
                    data-topology-interactive="true"
                    onClick={() => {
                      setSelectedLink(prev => prev?.id === link.id ? null : link)
                      setSelectedNode(null)
                    }}
                    onMouseEnter={(event) => {
                      const viewport = graphViewportRef.current
                      if (!viewport) return
                      const bounds = viewport.getBoundingClientRect()
                      const x = event.clientX - bounds.left
                      const y = event.clientY - bounds.top
                      setHoverPreview({
                        title: `${fromNode?.hostname || link.from} -> ${toNode?.hostname || link.to}`,
                        lines: [
                          `${fromNode?.ip || 'IP UNKNOWN'} | ${fromNode?.mac || 'MAC UNKNOWN'}`,
                          `${toNode?.ip || 'IP UNKNOWN'} | ${toNode?.mac || 'MAC UNKNOWN'}`,
                          `${link.localPort || 'PORT UNKNOWN'} -> ${destinationPortLabel(link.remotePort)}`,
                          `${link.source} | ${link.confidence}`,
                        ],
                        x: Math.max(12, Math.min(x, bounds.width - 12)),
                        y: Math.max(12, Math.min(y, bounds.height - 12)),
                        above: y > bounds.height - 170,
                      })
                    }}
                    onMouseLeave={() => setHoverPreview(current => current?.title === `${fromNode?.hostname || link.from} -> ${toNode?.hostname || link.to}` ? null : current)}
                    style={{ cursor: 'pointer' }}
                  >
                    <path d={`M ${from.x} ${startY} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${endY}`} fill="none" stroke="transparent" strokeWidth="22" />
                    <path d={`M ${from.x} ${startY} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${endY}`} fill="none" stroke={color} strokeWidth={selected ? 4 : highlighted ? 3.2 : link.gatewayPath ? 3 : 2} strokeOpacity={highlighted || selected ? 1 : 0.4} strokeDasharray={link.confidence === 'INFERRED' ? '8 6' : undefined} filter={selected || highlighted ? 'url(#topologyGlow)' : undefined}>
                      <animate attributeName="stroke-opacity" values={highlighted || selected ? '.7;1;.7' : '.25;.75;.25'} dur={link.gatewayPath ? '1.5s' : '2.4s'} repeatCount="indefinite" />
                      {link.confidence === 'INFERRED' && <animate attributeName="stroke-dashoffset" values="0;-28" dur="1s" repeatCount="indefinite" />}
                    </path>
                    <text x={(from.x + to.x) / 2} y={midY - 10} textAnchor="middle" className="font-mono" style={{ fill: color, fontSize: 8, fontWeight: 700 }}>SRC: {link.localPort || 'PORT UNKNOWN'}</text>
                    <text x={(from.x + to.x) / 2} y={midY + 14} textAnchor="middle" className="font-mono" style={{ fill: '#64748b', fontSize: 8 }}>{link.macCount ? `${link.macCount} MACs` : link.confidence}</text>
                    <text x={destinationLabelX} y={destinationLabelY - 8} textAnchor="middle" className="font-mono" style={{ fill: '#cbd5e1', fontSize: 8, fontWeight: 700 }}>DST: {destinationPortLabel(link.remotePort)}</text>
                  </g>
                )
              })}
              {visible.nodes.map(node => {
                const point = layout.positions.get(node.id)
                return point ? card(node, point) : null
              })}
              </g>
            </svg>
            {!visible.nodes.length && !loading && !refreshing && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="rounded-lg px-5 py-4 font-mono text-sm tracking-wide" style={{ color: '#22d3ee', background: 'rgba(3,10,20,.92)', border: '1px solid rgba(34,211,238,.18)', boxShadow: '0 16px 40px rgba(2,8,23,.35)' }}>
                  No connected nodes match the current filter.
                </div>
              </div>
            )}
            {hoverPreview && (
              <div
                className="absolute z-20 pointer-events-none max-w-[320px] rounded-xl px-3 py-2"
                style={{
                  left: hoverPreview.x,
                  top: hoverPreview.y,
                  transform: `translate(-50%, ${hoverPreview.above ? 'calc(-100% - 14px)' : '14px'})`,
                  background: 'rgba(3,10,20,.96)',
                  border: '1px solid rgba(34,211,238,.18)',
                  boxShadow: '0 18px 40px rgba(2,8,23,.45)',
                }}
              >
                <div className="font-display text-xs tracking-wider" style={{ color: '#22d3ee' }}>{hoverPreview.title}</div>
                {hoverPreview.lines.map((line, index) => (
                  <div key={`${hoverPreview.title}-${index}`} className="font-mono text-[10px] mt-1" style={{ color: 'var(--t-text, #c8d8ee)' }}>
                    {line}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

      </GlassCard>
      </div>

      <div className="flex flex-wrap gap-4 font-mono text-[10px]" style={{ color: '#64748b' }}>
        <span><i className="inline-block w-7 border-t-2 mr-2" style={{ borderColor: '#22d3ee' }} />{tr.confirmedLegend}</span>
        <span><i className="inline-block w-7 border-t-2 border-dashed mr-2" style={{ borderColor: '#fbbf24' }} />{tr.inferredLegend}</span>
        <span><i className="inline-block w-7 border-t-2 mr-2" style={{ borderColor: '#a78bfa' }} />{tr.gatewayPath}</span>
        <span>{tr.clickDetails}</span>
      </div>

      {editingNode && (
        <EditTopologyDeviceDialog
          device={editingNode}
          onClose={() => setEditingNode(null)}
          onSave={saveNode}
        />
      )}
    </div>
  )
}

function Metric({ label, value, color = '#e2e8f0' }: { label: string; value: number; color?: string }) {
  return <div><div className="font-mono text-[9px]" style={{ color: '#64748b' }}>{label}</div><div className="font-display text-lg" style={{ color }}>{value}</div></div>
}

function EditTopologyDeviceDialog({
  device,
  onClose,
  onSave,
}: {
  device: NonNullable<TopologyNodeDetails['device']>
  onClose: () => void
  onSave: (values: Record<string, string>) => Promise<void>
}) {
  const [values, setValues] = useState({
    hostname: device.hostname || device.name || '',
    ip_address: device.ip_address || '',
    mac_address: device.mac_address || '',
    vendor: device.vendor || '',
    model: device.model || '',
    serial_number: device.serial_number || '',
    firmware: device.firmware || '',
    status: device.status || 'unknown',
    port: device.topology_metadata?.port || '',
    vlans: (device.topology_metadata?.vlans || []).join(', '),
    ips: (device.topology_metadata?.ips || []).join(', '),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const update = (key: string, value: string) => setValues(current => ({ ...current, [key]: value }))

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await onSave(values)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Failed to update device')
    } finally {
      setSaving(false)
    }
  }

  const fields: Array<[string, string, string]> = [
    ['hostname', 'HOSTNAME', ''],
    ['ip_address', 'IP ADDRESS', ''],
    ['mac_address', 'MAC ADDRESS', 'aa:bb:cc:dd:ee:ff'],
    ['vendor', 'VENDOR / MANUFACTURER', 'e.g. Cisco, AgniGATE'],
    ['model', 'MODEL', ''],
    ['serial_number', 'SERIAL NUMBER', ''],
    ['firmware', 'FIRMWARE VERSION', ''],
    ['port', 'PORT / INTERFACE', 'e.g. Gi0/1'],
    ['vlans', 'VLANs', 'comma separated: 10, 20'],
    ['ips', 'IPs ON PORT', 'comma separated IPs'],
  ]
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.72)', backdropFilter: 'blur(4px)' }} onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <form onSubmit={submit} className="w-full max-w-2xl rounded-xl p-5 space-y-4" style={{ background: '#061426', border: '1px solid rgba(34,211,238,.3)', boxShadow: '0 20px 80px rgba(0,0,0,.45)' }}>
        <div className="flex items-center justify-between">
          <div><div className="font-display font-bold tracking-widest" style={{ color: '#22d3ee' }}>EDIT DEVICE</div><div className="font-mono text-[10px] mt-1" style={{ color: '#64748b' }}>SNMP identity used by topology</div></div>
          <button type="button" onClick={onClose} className="font-mono text-xs" style={{ color: '#fb7185' }}>CLOSE</button>
        </div>
        {error && <div className="rounded p-2 font-mono text-[10px]" style={{ color: '#fb7185', background: 'rgba(127,29,29,.25)' }}>{error}</div>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {fields.map(([key, label, placeholder]) => (
            <label key={key} className="font-mono text-[10px]" style={{ color: '#8ca0bb' }}>{label}
              <input value={values[key as keyof typeof values]} placeholder={placeholder} onChange={event => update(key, event.target.value)} required={key === 'hostname' || key === 'ip_address'} className="mt-1 w-full rounded px-3 py-2 outline-none" style={{ color: '#dbeafe', background: 'rgba(8,25,55,.7)', border: '1px solid rgba(34,211,238,.18)' }} />
            </label>
          ))}
          <label className="font-mono text-[10px]" style={{ color: '#8ca0bb' }}>STATUS
            <select value={values.status} onChange={event => update('status', event.target.value)} className="mt-1 w-full rounded px-3 py-2" style={{ color: '#dbeafe', background: '#081937', border: '1px solid rgba(34,211,238,.18)' }}><option value="online">ONLINE</option><option value="warning">WARNING</option><option value="offline">OFFLINE</option><option value="unknown">UNKNOWN</option></select>
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2" style={{ borderTop: '1px solid rgba(34,211,238,.12)' }}><button type="button" onClick={onClose} className="rounded px-3 py-2 font-mono text-[10px]" style={{ color: '#fb7185', border: '1px solid rgba(251,113,133,.2)' }}>CANCEL</button><button type="submit" disabled={saving} className="rounded px-3 py-2 font-mono text-[10px]" style={{ color: '#34d399', border: '1px solid rgba(52,211,153,.25)', opacity: saving ? .6 : 1 }}>{saving ? 'SAVING…' : 'SAVE CHANGES'}</button></div>
      </form>
    </div>
  )
}

function NodeDetails({
  node,
  links,
  nodes,
  onLink,
  onNodeSelect,
  onOpenDeviceDetails,
  onEditDevice,
  connectionsSearch,
  onConnectionsSearch,
  deferredConnectionsSearch,
  details,
  connectedDetails,
  loading,
  error,
}: {
  node: GraphNode
  links: GraphLink[]
  nodes: GraphNode[]
  onLink: (link: GraphLink) => void
  onNodeSelect: (node: GraphNode) => void
  onOpenDeviceDetails: (deviceId: number) => void
  onEditDevice: (device: NonNullable<TopologyNodeDetails['device']>) => void
  connectionsSearch: string
  onConnectionsSearch: (value: string) => void
  deferredConnectionsSearch: string
  details: TopologyNodeDetails | null
  connectedDetails: Record<string, TopologyNodeDetails>
  loading: boolean
  error: string | null
}) {
  const { t } = useI18n()
  const tr = t.topology
  const connectionQuery = deferredConnectionsSearch.trim().toLowerCase()
  const nodeLinks = links.filter(link => {
    if (link.from !== node.id && link.to !== node.id) return false
    if (!connectionQuery) return true
    const remoteId = link.from === node.id ? link.to : link.from
    const remote = nodes.find(item => item.id === remoteId)
    const remoteDetails = remote ? connectedDetails[remote.id] : null
    const haystack = [
      remote?.hostname,
      remote?.ip,
      remote?.mac,
      remoteDetails?.device?.vendor,
      remoteDetails?.device?.model,
      remoteDetails?.device?.serial_number,
      link.localPort,
      link.remotePort,
    ].filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(connectionQuery)
  })
  const monitoring = details?.monitoring || []
  const safeType = String(node.type || 'unknown')
  const safeStatus = String(node.status || 'unknown')
  const safeHostname = String(node.hostname || 'UNKNOWN')
  const safeIp = String(node.ip || '')
  const safeMac = String(node.mac || '')
  const allMacs = unique([...(node.macs || []), safeMac].filter(Boolean).map(value => displayMac(value) || String(value)))
  const safePort = String(node.port || '')
  const safeVendor = String(node.vendor || '')
  const safeModel = String(node.model || '')
  const runningModules = monitoring.filter(item => item.enabled).map(item => item.module_name.toUpperCase())
  const capabilities = Object.entries(details?.capabilities || {})
    .filter(([, supported]) => supported)
    .map(([name]) => name.toUpperCase())
  return (
    <div className="space-y-5">
      <div>
        <div className="font-display font-bold text-sm" style={{ color: '#22d3ee' }}>{safeHostname}</div>
        <div className="font-mono text-[10px] mt-1" style={{ color: '#64748b' }}>{safeType.toUpperCase()} · {safeStatus.toUpperCase()}</div>
        {details?.device?.id && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={() => onEditDevice(details.device!)} className="rounded px-3 py-2 font-mono text-[10px]" style={{ color: '#34d399', border: '1px solid rgba(52,211,153,.25)', background: 'rgba(52,211,153,.06)' }}>{tr.editDevice}</button>
            <button type="button" onClick={() => onOpenDeviceDetails(details.device!.id)} className="rounded px-3 py-2 font-mono text-[10px]" style={{ color: '#22d3ee', border: '1px solid rgba(34,211,238,.2)', background: 'rgba(34,211,238,.06)' }}>{tr.openSnmpDetails}</button>
          </div>
        )}
        <div className="grid sm:grid-cols-2 gap-x-6 mt-3">
          <Detail label="IP" value={safeIp || 'UNKNOWN'} />
          <Detail label="MAC" value={safeMac || (node.macs?.length ? `${node.macs.length} MACs` : 'UNKNOWN')} />
          {allMacs.length > 1 && <Detail label="ALL LEARNED MACS" value={allMacs.join(', ')} />}
          <Detail label="PORT" value={safePort || 'UNKNOWN'} />
          <Detail label="VLANs" value={node.vlans?.length ? node.vlans.join(', ') : 'UNKNOWN'} />
          <Detail label="IPs ON PORT" value={node.ips?.length ? node.ips.join(', ') : 'UNKNOWN'} />
          <Detail label="VENDOR / MODEL" value={[safeVendor, safeModel].filter(Boolean).join(' · ') || 'UNKNOWN'} />
        </div>

        <div className="mt-4">
          <div className="font-display text-xs tracking-wider mb-2" style={{ color: '#8ca0bb' }}>{tr.databaseDetails}</div>
          {loading ? (
            <div className="font-mono text-[10px]" style={{ color: '#64748b' }}>Loading device details…</div>
          ) : error ? (
            <div className="font-mono text-[10px]" style={{ color: '#fb7185' }}>{error}</div>
          ) : details?.device ? (
            <div className="grid sm:grid-cols-2 gap-x-6">
              <Detail label="HOSTNAME" value={details.device.hostname || details.device.name || node.hostname} />
              <Detail label="DB DEVICE ID" value={String(details.device.id)} />
              <Detail label="DB IP" value={details.device.ip_address || node.ip || 'UNKNOWN'} />
              <Detail label="DB MAC" value={details.device.mac_address || node.mac || 'UNKNOWN'} />
              <Detail label="SERIAL / FIRMWARE" value={[details.device.serial_number, details.device.firmware].filter(Boolean).join(' · ') || 'UNKNOWN'} />
              <Detail label="SNMP / LAST SEEN" value={[details.snmp?.version || 'N/A', details.device.last_seen ? new Date(details.device.last_seen).toLocaleString() : 'N/A'].join(' · ')} />
              <Detail label="CAPABILITIES" value={capabilities.length ? capabilities.join(', ') : 'N/A'} />
              <Detail label="MONITORING MODULES" value={runningModules.length ? runningModules.join(', ') : 'N/A'} />
            </div>
          ) : (
            <div className="font-mono text-[10px]" style={{ color: '#64748b' }}>This node is inferred from topology data and has no direct DB record.</div>
          )}
        </div>
      </div>

      <div>
        <div className="font-display text-xs tracking-wider mb-2" style={{ color: '#8ca0bb' }}>{tr.connections}</div>
        <input
          value={connectionsSearch}
          onChange={event => onConnectionsSearch(event.target.value)}
          placeholder={tr.searchConnections}
          className="mb-3 w-full rounded px-3 py-2 text-[10px] font-mono outline-none"
          style={{ color: 'var(--t-text, #c8d8ee)', border: '1px solid rgba(34,211,238,.15)', background: 'rgba(8,25,55,.5)' }}
        />
        {nodeLinks.length ? nodeLinks.map((link, index) => {
          const remoteId = link.from === node.id ? link.to : link.from
          const remote = nodes.find(item => item.id === remoteId)
          const remoteDetails = remote ? connectedDetails[remote.id] : null
          const remoteCapabilities = Object.entries(remoteDetails?.capabilities || {})
            .filter(([, supported]) => supported)
            .map(([name]) => name.toUpperCase())
          const remoteModules = (remoteDetails?.monitoring || [])
            .filter(item => item.enabled)
            .map(item => item.module_name.toUpperCase())
          return (
            <button
              type="button"
              key={linkRenderKey(link, index, 'node-link')}
              onClick={() => remote ? onNodeSelect(remote) : onLink(link)}
              className="w-full text-left py-2 border-t border-cyan-400/10 font-mono text-[10px]"
              style={{ color: link.confidence === 'CONFIRMED' ? '#22d3ee' : '#fbbf24' }}
              title={`${remote?.hostname || remoteId} | ${remote?.ip || 'IP UNKNOWN'} | ${remote?.mac || 'MAC UNKNOWN'} | ${link.localPort || 'PORT UNKNOWN'} -> ${destinationPortLabel(link.remotePort)}`}
            >
              {remote?.hostname || remote?.ip || remoteId}
              <span className="block mt-1" style={{ color: '#dbeafe' }}>
                {(remote?.ip || 'IP UNKNOWN')} · {(remote?.mac || 'MAC UNKNOWN')}
              </span>
              <span className="block" style={{ color: '#64748b' }}>
                {link.localPort || 'PORT UNKNOWN'} → {destinationPortLabel(link.remotePort)} · {link.confidence} · {link.source}
              </span>
              <span className="block mt-2" style={{ color: '#94a3b8' }}>
                Vendor: {remoteDetails?.device?.vendor || remote?.vendor || 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                Model: {remoteDetails?.device?.model || remote?.model || 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                Serial: {remoteDetails?.device?.serial_number || 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                Firmware: {remoteDetails?.device?.firmware || 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                SNMP: {remoteDetails?.snmp?.version || 'N/A'} · {remoteDetails?.snmp?.status || 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                Last Seen: {remoteDetails?.device?.last_seen ? new Date(remoteDetails.device.last_seen).toLocaleString() : 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                Capabilities: {remoteCapabilities.length ? remoteCapabilities.join(', ') : 'N/A'}
              </span>
              <span className="block" style={{ color: '#94a3b8' }}>
                Monitoring: {remoteModules.length ? remoteModules.join(', ') : 'N/A'}
              </span>
              <span className="mt-2 flex flex-wrap gap-2">
                {remoteDetails?.device?.id && (
                  <span
                    onClick={(event) => {
                      event.stopPropagation()
                      onOpenDeviceDetails(remoteDetails.device!.id)
                    }}
                    className="inline-flex rounded px-2 py-1"
                    style={{ color: '#22d3ee', border: '1px solid rgba(34,211,238,.18)', background: 'rgba(34,211,238,.06)' }}
                  >
                    {tr.openSnmpDetails}
                  </span>
                )}
                <span className="inline-flex rounded px-2 py-1" style={{ color: '#a78bfa', border: '1px solid rgba(167,139,250,.18)', background: 'rgba(167,139,250,.06)' }}>
                  {tr.clickConnected}
                </span>
              </span>
            </button>
          )
        }) : <div className="font-mono text-[10px]" style={{ color: '#64748b' }}>{tr.noLinks}</div>}
      </div>
    </div>
  )
}

function LinkDetails({
  link,
  nodes,
  onNodeSelect,
  onOpenDeviceDetails,
}: {
  link: GraphLink
  nodes: GraphNode[]
  onNodeSelect: (node: GraphNode) => void
  onOpenDeviceDetails: (deviceId: number) => void
}) {
  const local = nodes.find(node => node.id === link.from)
  const remote = nodes.find(node => node.id === link.to)
  return <div className="space-y-4 font-mono text-[10px]">
    <div className="grid sm:grid-cols-2 gap-3">
      <Detail label="LOCAL DEVICE / PORT" value={`${local?.hostname || link.from} · ${link.localPort || 'UNKNOWN'}`} />
      <Detail label="REMOTE DEVICE / PORT" value={`${remote?.hostname || link.to} · ${destinationPortLabel(link.remotePort)}`} />
      <Detail label="LOCAL IP / MAC" value={`${local?.ip || 'UNKNOWN'} · ${local?.mac || 'UNKNOWN'}`} />
      <Detail label="REMOTE IP / MAC" value={`${remote?.ip || 'UNKNOWN'} · ${remote?.mac || 'UNKNOWN'}`} />
      <Detail label="SOURCE / CONFIDENCE" value={`${link.source} · ${link.confidence}`} />
      <Detail label="VLAN / SPEED / STATUS" value={`${link.vlan ?? 'UNKNOWN'} · ${link.speed ?? 'UNKNOWN'} · ${link.status || 'UNKNOWN'}`} />
    </div>
    <div className="grid sm:grid-cols-2 gap-2">
      {local && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onNodeSelect(local)}
            className="rounded px-3 py-2 text-left"
            style={{ color: '#22d3ee', border: '1px solid rgba(34,211,238,.18)', background: 'rgba(34,211,238,.06)' }}
            title={`${local.hostname} | ${local.ip || 'IP UNKNOWN'} | ${local.mac || 'MAC UNKNOWN'}`}
          >
            Open local device
          </button>
          {Number.isFinite(Number(local.id)) && (
            <button
              type="button"
              onClick={() => onOpenDeviceDetails(Number(local.id))}
              className="rounded px-3 py-2 text-left"
              style={{ color: '#67e8f9', border: '1px solid rgba(103,232,249,.18)', background: 'rgba(103,232,249,.06)' }}
            >
              Local SNMP Details
            </button>
          )}
        </div>
      )}
      {remote && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onNodeSelect(remote)}
            className="rounded px-3 py-2 text-left"
            style={{ color: '#c084fc', border: '1px solid rgba(192,132,252,.18)', background: 'rgba(192,132,252,.06)' }}
            title={`${remote.hostname} | ${remote.ip || 'IP UNKNOWN'} | ${remote.mac || 'MAC UNKNOWN'}`}
          >
            Open remote device
          </button>
          {Number.isFinite(Number(remote.id)) && (
            <button
              type="button"
              onClick={() => onOpenDeviceDetails(Number(remote.id))}
              className="rounded px-3 py-2 text-left"
              style={{ color: '#e879f9', border: '1px solid rgba(232,121,249,.18)', background: 'rgba(232,121,249,.06)' }}
            >
              Remote SNMP Details
            </button>
          )}
        </div>
      )}
    </div>
  </div>
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="py-1.5 border-t border-cyan-400/10"><div style={{ color: '#64748b' }}>{label}</div><div className="mt-1 break-all" style={{ color: '#dbeafe' }}>{value}</div></div>
}
