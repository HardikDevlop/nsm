import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import GlassCard from '../components/GlassCard'
import SNMPDiscoveryPanel from '../features/snmp/components/SNMPDiscoveryPanel'
import SNMPSubnetDiscovery from '../features/snmp/components/SNMPSubnetDiscovery'
import { PermissionGuard } from '../components/PermissionGuard'
import { addDiscoveredDevices, checkStoredDevices, createDevice, createOrganization, createSite, deleteAllDevices, deleteDevice, detectLocalSubnet, getOverview, listDevices, listOrganizations, listSites, pingIps, startChunkedDiscovery, streamChunkedDiscovery, updateDevice, type ChunkedDiscoveryProgress, type DeviceRecord, type OrganizationRecord, type SiteRecord } from '../lib/api'
import { confirmDanger, toast } from '../lib/swal'
import { useI18n } from '../i18n/I18nContext'

const moduleCatalog = [
  { key: 'icmp_discovery', label: 'ICMP', description: 'Ping reachability and host alive checks' },
  // { key: 'tcp_discovery', label: 'TCP', description: 'Open ports and service reachability' },
  // { key: 'arp_discovery', label: 'ARP', description: 'MAC address / ARP cache enrichment' },
  // { key: 'dns_discovery', label: 'DNS', description: 'Hostname and DNS lookups' },
  { key: 'snmp_discovery', label: 'SNMP', description: 'Node description and SNMP metadata' },
  // { key: 'wmi_discovery', label: 'WMI', description: 'Windows system metadata' },
]

function isIPv4(value: string): boolean {
  const parts = value.trim().split('.')
  return parts.length === 4 && parts.every(part => /^\d{1,3}$/.test(part) && Number(part) <= 255)
}

function discoveryTargetIsValid(value: string): boolean {
  const spec = value.trim()
  if (!spec) return false
  if (spec.includes(',')) {
    const values = spec.split(',').map(item => item.trim()).filter(Boolean)
    return values.length <= 255 && values.every(isIPv4)
  }
  if (spec.includes('/')) {
    const [ip, prefix] = spec.split('/')
    const bits = Number(prefix)
    return isIPv4(ip) && /^\d{1,2}$/.test(prefix || '') && bits >= 24 && bits <= 32
  }
  if (spec.includes('-')) {
    const [start, end] = spec.split('-').map(item => item.trim())
    if (!isIPv4(start)) return false
    if (/^\d{1,3}$/.test(end)) return Number(end) <= 255 && Number(end) >= Number(start.split('.')[3]) && Number(end) - Number(start.split('.')[3]) + 1 <= 255
    if (!isIPv4(end)) return false
    const toNumber = (ip: string) => ip.split('.').reduce((total, part) => total * 256 + Number(part), 0)
    return toNumber(end) >= toNumber(start) && toNumber(end) - toNumber(start) + 1 <= 255
  }
  return isIPv4(spec)
}

export default function ISPMonitoring() {
  const { t } = useI18n()
  const tr = t.workflow
  const queryClient = useQueryClient()
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [interfaceCount, setInterfaceCount] = useState(0)
  const [openAlertCount, setOpenAlertCount] = useState(0)
  const [discoveryTarget, setDiscoveryTarget] = useState('192.168.1.0/24')
  const [selectedModules, setSelectedModules] = useState<string[]>(['ip_discovery', 'icmp_discovery'])
  const [discoveryProgress, setDiscoveryProgress] = useState<ChunkedDiscoveryProgress | null>(null)
  const [discoveryResults, setDiscoveryResults] = useState<Record<string, unknown>[]>([])
  const [eventRows, setEventRows] = useState<Array<{ id: string; title: string; detail: string }>>([])
  const [page, setPage] = useState(1)
  const [message, setMessage] = useState('')
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [storedIps, setStoredIps] = useState<Set<string>>(new Set())
  const [showAllStored, setShowAllStored] = useState(false)
  const [addingIps, setAddingIps] = useState<Set<string>>(new Set())
  const [topoHover, setTopoHover] = useState<string | null>(null)
  const [topoStatuses, setTopoStatuses] = useState<Record<string, boolean>>({})
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // SNMP Discovery Modal State
  const [showSNMPModal, setShowSNMPModal] = useState(false)

  // ── Device CRUD state ──
  const [showAddDevice, setShowAddDevice] = useState(false)
  const [organizations, setOrganizations] = useState<OrganizationRecord[]>([])
  const [sites, setSites] = useState<SiteRecord[]>([])
  const [newOrg, setNewOrg] = useState('')
  const [newSite, setNewSite] = useState('')
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null)
  const [selectedSiteId, setSelectedSiteId] = useState<number | null>(null)
  const [deviceForm, setDeviceForm] = useState({
    hostname: '',
    ip_address: '',
    mac_address: '',
    model: '',
    serial_number: '',
    firmware_version: '',
  })
  const [editingDeviceId, setEditingDeviceId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<DeviceRecord>>({})
  const [crudMessage, setCrudMessage] = useState('')
  const [crudError, setCrudError] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [selectedManagedDeviceIds, setSelectedManagedDeviceIds] = useState<Set<number>>(new Set())
  const [deletingSelectedManaged, setDeletingSelectedManaged] = useState(false)

  // ── Topology graph data ──
  interface TopoNode { id: string; ip: string; hostname: string; status: string; mac: string; x: number; y: number; type: 'gateway' | 'device' }
  interface TopoEdge { from: string; to: string }

  const { topoNodes, topoEdges } = useMemo(() => {
    const nodes: TopoNode[] = []
    const edges: TopoEdge[] = []
    // Gateway at center
    const gwIp = discoveryTarget.split('/')[0] || '192.168.100.1'
    nodes.push({ id: 'gw', ip: gwIp, hostname: 'Gateway', status: 'online', mac: '', x: 0.5, y: 0.5, type: 'gateway' })

    // Always use stored DB devices for topology — discoveryResults are temporary
    // and should never replace devices already stored in the database
    const source = devices.map(d => ({
      ip: d.ip_address,
      hostname: d.hostname,
      status: topoStatuses[d.ip_address] !== undefined
        ? (topoStatuses[d.ip_address] ? 'online' : 'offline')
        : (d.status === 'online' ? 'online' : 'offline'),
      mac: d.mac_address ?? '',
    }))

    const count = source.length
    if (count === 0) return { topoNodes: nodes, topoEdges: edges }

    source.forEach((dev, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2
      const radius = 0.36
      const nx = 0.5 + radius * Math.cos(angle)
      const ny = 0.5 + radius * Math.sin(angle)
      const id = `n-${i}`
      nodes.push({ id, ip: dev.ip, hostname: dev.hostname, status: dev.status, mac: dev.mac, x: nx, y: ny, type: 'device' })
      edges.push({ from: 'gw', to: id })
    })

    return { topoNodes: nodes, topoEdges: edges }
  }, [devices, discoveryResults, discoveryTarget, topoStatuses])

  // ── Canvas topology renderer ──
  const drawTopology = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    const W = rect.width
    const H = rect.height
    ctx.clearRect(0, 0, W, H)

    const pos = (n: TopoNode) => ({ px: n.x * W, py: n.y * H })

    // Draw edges
    topoEdges.forEach(edge => {
      const fromNode = topoNodes.find(n => n.id === edge.from)
      const toNode = topoNodes.find(n => n.id === edge.to)
      if (!fromNode || !toNode) return
      const a = pos(fromNode)
      const b = pos(toNode)
      const isHovered = topoHover === edge.to || topoHover === edge.from
      ctx.beginPath()
      ctx.moveTo(a.px, a.py)
      ctx.lineTo(b.px, b.py)
      ctx.strokeStyle = isHovered ? 'rgba(0,212,255,0.6)' : 'rgba(0,212,255,0.12)'
      ctx.lineWidth = isHovered ? 2 : 1
      ctx.stroke()
      // Animated pulse dot along edge
      const t = (Date.now() % 3000) / 3000
      const dx = b.px - a.px
      const dy = b.py - a.py
      const px = a.px + dx * t
      const py = a.py + dy * t
      ctx.beginPath()
      ctx.arc(px, py, 1.5, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(0,212,255,0.5)'
      ctx.fill()
    })

    // Draw nodes
    topoNodes.forEach(node => {
      const { px, py } = pos(node)
      const isHovered = topoHover === node.id
      const isGateway = node.type === 'gateway'
      const r = isGateway ? 14 : 7
      const color = node.status === 'online' ? '#00ff88' : '#ff3366'

      // Glow
      if (isHovered || isGateway) {
        const grad = ctx.createRadialGradient(px, py, 0, px, py, r * 3)
        grad.addColorStop(0, isGateway ? 'rgba(0,212,255,0.25)' : `${color}33`)
        grad.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.beginPath()
        ctx.arc(px, py, r * 3, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()
      }

      // Node circle
      ctx.beginPath()
      ctx.arc(px, py, r, 0, Math.PI * 2)
      ctx.fillStyle = isGateway ? 'rgba(0,212,255,0.2)' : `${color}22`
      ctx.fill()
      ctx.strokeStyle = isGateway ? '#00d4ff' : color
      ctx.lineWidth = isGateway ? 2 : 1.5
      ctx.stroke()

      // Gateway icon (router symbol)
      if (isGateway) {
        ctx.strokeStyle = '#00d4ff'
        ctx.lineWidth = 1.5
        // Arrows
        const s = 6
        ctx.beginPath(); ctx.moveTo(px - s, py); ctx.lineTo(px + s, py); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(px, py - s); ctx.lineTo(px, py + s); ctx.stroke()
        // Arrow heads
        ctx.beginPath(); ctx.moveTo(px + s - 2, py - 2); ctx.lineTo(px + s, py); ctx.lineTo(px + s - 2, py + 2); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(px - s + 2, py - 2); ctx.lineTo(px - s, py); ctx.lineTo(px - s + 2, py + 2); ctx.stroke()
      }

      // Label
      ctx.font = `${isGateway ? 10 : 8}px "JetBrains Mono", monospace`
      ctx.textAlign = 'center'
      const lightTheme = document.documentElement.getAttribute('data-theme') === 'light'
      ctx.fillStyle = isHovered ? (lightTheme ? '#111827' : '#ffffff') : (lightTheme ? '#475569' : '#8899bb')
      ctx.fillText(node.ip, px, py + r + 12)
      if (isGateway) {
        ctx.font = '9px "JetBrains Mono", monospace'
        ctx.fillStyle = '#00d4ff'
        ctx.fillText('GATEWAY', px, py + r + 23)
      }
    })
  }, [topoNodes, topoEdges, topoHover])

  // Animation loop for topology
  useEffect(() => {
    let frameId: number
    const loop = () => {
      drawTopology()
      frameId = requestAnimationFrame(loop)
    }
    frameId = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(frameId)
  }, [drawTopology])

  // Mouse interaction for topology
  const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const W = rect.width
    const H = rect.height
    let found: string | null = null
    for (const node of topoNodes) {
      const px = node.x * W
      const py = node.y * H
      const r = node.type === 'gateway' ? 18 : 12
      if (Math.hypot(mx - px, my - py) < r) {
        found = node.id
        break
      }
    }
    setTopoHover(found)
  }, [topoNodes])

  // ── Auto-ping topology nodes every 15 seconds ──
  const pingTopologyNodes = useCallback(async () => {
    const ips = topoNodes.filter(n => n.type === 'device').map(n => n.ip).filter(Boolean)
    if (ips.length === 0) return
    try {
      const result = await pingIps(ips, 1000)
      const statuses: Record<string, boolean> = {}
      for (const r of result.results) {
        statuses[r.ip] = r.reachable
      }
      setTopoStatuses(statuses)
    } catch {
      // silent — topology just keeps last known status
    }
  }, [topoNodes])

  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState !== 'visible') return
      void pingTopologyNodes()
    }, 15000)
    return () => clearInterval(interval)
  }, [pingTopologyNodes])

  const pageSize = 25

  const loadInitialData = async () => {
    try {
      const [deviceData, overview, subnetData] = await Promise.all([
        listDevices(),
        getOverview(24),
        detectLocalSubnet().catch(() => ({ subnet: '192.168.1.0/24', ip: null })),
      ])
      setDevices(deviceData)
      setInterfaceCount(overview.normalized.interface_summary.total)
      setOpenAlertCount(overview.alerts.filter(alert => alert.status === 'open').length)
      // Auto-detect local subnet for discovery target
      if (subnetData.subnet) {
        setDiscoveryTarget(subnetData.subnet)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load ISP data')
    }
  }

  useEffect(() => {
    let ignore = false
    void (async () => {
      await loadInitialData()
      if (ignore) return
    })()
    return () => { ignore = true }
  }, [])

  useEffect(() => {
    if (organizations.length > 0 || sites.length > 0) return
    let cancelled = false
    void (async () => {
      try {
        const [orgData, siteData] = await Promise.all([listOrganizations(), listSites()])
        if (cancelled) return
        setOrganizations(orgData)
        setSites(siteData)
      } catch {
        // keep form usable without blocking page render
      }
    })()
    return () => { cancelled = true }
  }, [organizations.length, sites.length])

  const discoverySummary = useMemo(() => {
    const online = devices.filter(device => device.status === 'online').length
    const offline = devices.filter(device => device.status !== 'online').length
    return [
      { name: 'Devices', value: devices.length, color: '#00d4ff' },
      { name: 'Online', value: online, color: '#00ff88' },
      { name: 'Offline', value: offline, color: '#ff3366' },
      { name: 'Interfaces', value: interfaceCount, color: '#ffaa00' },
      { name: 'Open Alerts', value: openAlertCount, color: '#9b8cff' },
    ]
  }, [devices, interfaceCount, openAlertCount])

  const totalPages = Math.max(1, Math.ceil(eventRows.length / pageSize))
  const pagedRows = useMemo(() => eventRows.slice((page - 1) * pageSize, page * pageSize), [eventRows, page])

  useEffect(() => {
    setPage(1)
  }, [eventRows.length])

  const toggleModule = (moduleKey: string) => {
    // Open SNMP modal when SNMP is clicked
    if (moduleKey === 'snmp_discovery') {
      setShowSNMPModal(true)
      return
    }
    
    setSelectedModules(prev => {
      if (prev.includes(moduleKey)) {
        return prev.filter(item => item !== moduleKey)
      }
      return [...prev, moduleKey]
    })
  }

  const buildRows = (results: Record<string, unknown>[]) => {
    const rows: Array<{ id: string; title: string; detail: string }> = []

    results.forEach((device, index) => {
      const item = device as Record<string, unknown>
      const ip = String(item.ip_address ?? item.ip ?? `device-${index + 1}`)
      const hostname = String(item.hostname ?? item.dns_hostname ?? 'unknown')
      const mac = String(item.mac_address ?? item.mac ?? '—')
      const vendor = String(item.vendor ?? '—')
      rows.push({ id: `${index}-device`, title: 'Discovered device', detail: `${hostname} · ${ip} · MAC: ${mac} · Vendor: ${vendor} · ${String(item.status ?? 'online')}` })

      if (item.open_ports) {
        const ports = typeof item.open_ports === 'object' ? Object.entries(item.open_ports as Record<string, unknown>).map(([port, service]) => `${port}:${service}`).join(', ') : String(item.open_ports)
        rows.push({ id: `${index}-tcp`, title: 'TCP discovery', detail: ports })
      }
      if (item.arp) {
        rows.push({ id: `${index}-arp`, title: 'ARP discovery', detail: JSON.stringify(item.arp) })
      }
      if (item.dns) {
        rows.push({ id: `${index}-dns`, title: 'DNS discovery', detail: JSON.stringify(item.dns) })
      }
      if (item.http) {
        rows.push({ id: `${index}-http`, title: 'HTTP discovery', detail: JSON.stringify(item.http) })
      }
      if (item.snmp) {
        rows.push({ id: `${index}-snmp`, title: 'SNMP discovery', detail: JSON.stringify(item.snmp) })
      }
      if (item.ssh) {
        rows.push({ id: `${index}-ssh`, title: 'SSH discovery', detail: JSON.stringify(item.ssh) })
      }
      if (item.wmi) {
        rows.push({ id: `${index}-wmi`, title: 'WMI discovery', detail: JSON.stringify(item.wmi) })
      }
      if (item.device_profile && !category && !os) {
        rows.push({ id: `${index}-profile-full`, title: 'Device profile', detail: JSON.stringify(item.device_profile) })
      }
      if (item.snmp_name) {
        rows.push({ id: `${index}-snmp-name`, title: 'SNMP name', detail: `${String(item.snmp_name)} · ${String(item.snmp_description ?? '')} · Vendor: ${String(item.snmp_vendor ?? '—')}` })
      }
      if (item.dns_hostname) {
        rows.push({ id: `${index}-dns-host`, title: 'DNS hostname', detail: String(item.dns_hostname) })
      }
      if (item.ssh_banner) {
        rows.push({ id: `${index}-ssh-banner`, title: 'SSH banner', detail: `${String(item.ssh_banner)} · Platform: ${String(item.ssh_platform ?? '—')}` })
      }
    })

    return rows
  }

  const buildSingleDeviceRows = (device: Record<string, unknown>, index: number) => {
    const item = device as Record<string, unknown>
    const rows: Array<{ id: string; title: string; detail: string }> = []
    const ip = String(item.ip_address ?? item.ip ?? `device-${index + 1}`)
    const hostname = String(item.hostname ?? item.dns_hostname ?? 'unknown')
    const mac = String(item.mac_address ?? item.mac ?? '—')
    const vendor = String(item.vendor ?? '—')
    rows.push({ id: `${index}-device`, title: 'Discovered device', detail: `${hostname} · ${ip} · MAC: ${mac} · Vendor: ${vendor} · ${String(item.status ?? 'online')}` })

    if (item.open_ports) {
      const ports = typeof item.open_ports === 'object' ? Object.entries(item.open_ports as Record<string, unknown>).map(([port, service]) => `${port}:${service}`).join(', ') : String(item.open_ports)
      rows.push({ id: `${index}-tcp`, title: 'TCP discovery', detail: ports })
    }
    if (item.arp) rows.push({ id: `${index}-arp`, title: 'ARP discovery', detail: JSON.stringify(item.arp) })
    if (item.dns) rows.push({ id: `${index}-dns`, title: 'DNS discovery', detail: JSON.stringify(item.dns) })
    if (item.http) rows.push({ id: `${index}-http`, title: 'HTTP discovery', detail: JSON.stringify(item.http) })
    if (item.snmp) rows.push({ id: `${index}-snmp`, title: 'SNMP discovery', detail: JSON.stringify(item.snmp) })
    if (item.ssh) rows.push({ id: `${index}-ssh`, title: 'SSH discovery', detail: JSON.stringify(item.ssh) })
    if (item.wmi) rows.push({ id: `${index}-wmi`, title: 'WMI discovery', detail: JSON.stringify(item.wmi) })
    if (item.snmp_name) rows.push({ id: `${index}-snmp-name`, title: 'SNMP name', detail: `${String(item.snmp_name)} · ${String(item.snmp_description ?? '')}` })
    if (item.dns_hostname) rows.push({ id: `${index}-dns-host`, title: 'DNS hostname', detail: String(item.dns_hostname) })
    if (item.ssh_banner) rows.push({ id: `${index}-ssh-banner`, title: 'SSH banner', detail: `${String(item.ssh_banner)} · Platform: ${String(item.ssh_platform ?? '—')}` })
    return rows
  }

  const discoveryResultsRef = useRef<Record<string, unknown>[]>([])

  const inventoryOnlyPayload = (device: Record<string, unknown>) => {
    // IP Scan stores inventory only. SNMP results must be created from the
    // dedicated SNMP discovery flow, not forwarded from this page.
    const {
      snmp,
      snmp_name,
      snmp_description,
      snmp_vendor,
      snmp_model,
      snmp_version,
      collectors,
      ...inventory
    } = device
    return inventory
  }

  const handleDiscover = async () => {
    const target = discoveryTarget.trim() || '192.168.1.0/24'
    if (!discoveryTargetIsValid(target)) {
      setError('Enter valid IPv4 addresses and keep the discovery range within 255 addresses.')
      toast.warning('Invalid discovery range. Maximum allowed is 255 addresses.')
      return
    }
    setError(null)
    setMessage('')
    setDiscoveryResults([])
    discoveryResultsRef.current = []
    setEventRows([])
    setDiscoveryProgress(null)
    setIsDiscovering(true)
    setStoredIps(new Set())
    setShowAllStored(false)

    try {
      const modules = Array.from(new Set(['ip_discovery', ...selectedModules]))
      const started = await startChunkedDiscovery({
        network_range: target,
        max_hosts: 254,
        ports: [22, 80, 443, 161, 162, 8080, 8443],
        timeout_ms: 700,
        scan_icmp: modules.includes('icmp_discovery'),
        scan_ports: modules.includes('tcp_discovery'),
        scan_snmp: modules.includes('snmp_discovery'),
        chunk_size: 25,
        modules,
      })

      setDiscoveryProgress({
        job_id: started.job_id,
        status: started.status,
        network_range: target,
        total_ips: started.total_ips,
        chunk_size: started.chunk_size,
        chunks_total: started.chunks_total,
        chunks_completed: 0,
        ips_scanned: 0,
        discovered_count: 0,
        progress_pct: 0,
        elapsed_seconds: 0,
        error: null,
      })
      setMessage(`Discovery started for job ${started.job_id}`)

      await streamChunkedDiscovery(started.job_id, (event) => {
        if (event.event === 'progress') {
          setDiscoveryProgress(event.data as ChunkedDiscoveryProgress)
          setMessage(`Scanning ${event.data.chunks_completed}/${event.data.chunks_total} chunks · ${event.data.discovered_count} devices found`)
        }
        if (event.event === 'discovered') {
          const discovered = event.data as Record<string, unknown>
          // Incrementally add to results ref and build rows immediately
          const ip = String(discovered.ip_address ?? discovered.ip ?? '')
          const exists = discoveryResultsRef.current.some(item => String(item.ip_address ?? item.ip ?? '') === ip)
          if (!exists) {
            discoveryResultsRef.current = [...discoveryResultsRef.current, discovered]
            setDiscoveryResults([...discoveryResultsRef.current])
            // Build rows for this device immediately — fast visual feedback
            const newRows = buildSingleDeviceRows(discovered, discoveryResultsRef.current.length - 1)
            setEventRows(prev => [...prev, ...newRows])
          }
        }
        if (event.event === 'complete') {
          const discovered = (event.data.discovered ?? []) as Record<string, unknown>[]
          discoveryResultsRef.current = discovered
          setDiscoveryResults(discovered)
          // Rebuild all rows from final data for consistency
          setEventRows(buildRows(discovered))
          setMessage(`Discovery completed — ${discovered.length} device(s) found`)
        }
        if (event.event === 'error') {
          setMessage(String(event.data.error ?? 'Discovery failed'))
        }
      })

      // Check which discovered devices are already stored
      const finalResults = discoveryResultsRef.current
      if (finalResults.length > 0) {
        const ips = finalResults.map(d => String((d as Record<string, unknown>).ip_address ?? (d as Record<string, unknown>).ip ?? '')).filter(Boolean)
        try {
          const check = await checkStoredDevices(ips)
          setStoredIps(new Set(check.stored_ips))
        } catch { /* ignore */ }
        setMessage(`Discovery completed — ${finalResults.length} device(s) found. Click Add to store individually.`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start discovery')
    } finally {
      setIsDiscovering(false)
    }
  }

  const handleStoreResults = async () => {
    if (discoveryResults.length === 0) {
      setMessage('Run discovery first so there is data to store')
      return
    }
    try {
      const stored = await addDiscoveredDevices({
        devices: discoveryResults.map(inventoryOnlyPayload),
        site_id: null,
        discovery_source: 'icmp',
      })
      setMessage(`Stored ${stored.added_count} device(s) into the database`)
      // Update storedIps
      const ips = discoveryResults.map(d => String((d as Record<string, unknown>).ip_address ?? (d as Record<string, unknown>).ip ?? '')).filter(Boolean)
      setStoredIps(prev => new Set([...prev, ...ips]))
      await loadInitialData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to store devices')
    }
  }

  const handleStoreSingle = async (device: Record<string, unknown>) => {
    const ip = String((device as Record<string, unknown>).ip_address ?? (device as Record<string, unknown>).ip ?? '')
    if (!ip) return
    setAddingIps(prev => new Set([...prev, ip]))
    try {
      const stored = await addDiscoveredDevices({
        devices: [inventoryOnlyPayload(device)],
        site_id: null,
        discovery_source: 'icmp',
      })
      if (stored.added_count > 0) {
        setStoredIps(prev => new Set([...prev, ip]))
        setMessage(`Stored ${ip} into the database`)
      } else {
        // Device already exists in DB, mark it as stored in UI
        setStoredIps(prev => new Set([...prev, ip]))
        setMessage(`${ip} already exists in the database`)
      }
      await loadInitialData()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to store ${ip}`)
    } finally {
      setAddingIps(prev => { const n = new Set(prev); n.delete(ip); return n })
    }
  }

  // Sort discovered devices: not-stored first, stored last
  const sortedDiscoveryResults = useMemo(() => {
    return [...discoveryResults].sort((a, b) => {
      const ipA = String((a as Record<string, unknown>).ip_address ?? (a as Record<string, unknown>).ip ?? '')
      const ipB = String((b as Record<string, unknown>).ip_address ?? (b as Record<string, unknown>).ip ?? '')
      const isStoredA = storedIps.has(ipA)
      const isStoredB = storedIps.has(ipB)
      // Not stored (false) comes before stored (true)
      if (isStoredA === isStoredB) return 0
      return isStoredA ? 1 : -1
    })
  }, [discoveryResults, storedIps])

  // ── Device CRUD handlers ──
  const handleCreateOrg = async () => {
    if (!newOrg.trim()) return
    setCrudError('')
    setCrudMessage('')
    try {
      const org = await createOrganization({ name: newOrg.trim() })
      setOrganizations(prev => [...prev, org])
      setSelectedOrgId(org.id)
      setNewOrg('')
      setCrudMessage(`Organization "${org.name}" created`)
    } catch (err) {
      setCrudError(err instanceof Error ? err.message : 'Failed to create organization')
    }
  }

  const handleCreateSite = async () => {
    if (!newSite.trim() || !selectedOrgId) {
      setCrudError('Please select an organization first')
      return
    }
    setCrudError('')
    setCrudMessage('')
    try {
      const site = await createSite({ name: newSite.trim(), organization_id: selectedOrgId })
      setSites(prev => [...prev, site])
      setSelectedSiteId(site.id)
      setNewSite('')
      setCrudMessage(`Site "${site.name}" created`)
    } catch (err) {
      setCrudError(err instanceof Error ? err.message : 'Failed to create site')
    }
  }

  const handleCreateDevice = async () => {
    if (!deviceForm.hostname.trim() || !deviceForm.ip_address.trim()) {
      setCrudError('Hostname and IP address are required')
      return
    }
    setCrudError('')
    setCrudMessage('')
    setIsCreating(true)
    try {
      const device = await createDevice({
        hostname: deviceForm.hostname.trim(),
        ip_address: deviceForm.ip_address.trim(),
        mac_address: deviceForm.mac_address.trim() || undefined,
        model: deviceForm.model.trim() || undefined,
        serial_number: deviceForm.serial_number.trim() || undefined,
        firmware_version: deviceForm.firmware_version.trim() || undefined,
        site_id: selectedSiteId ?? undefined,
      })
      setDevices(prev => [...prev, device])
      setDeviceForm({ hostname: '', ip_address: '', mac_address: '', model: '', serial_number: '', firmware_version: '' })
      setShowAddDevice(false)
      setCrudMessage(`Device "${device.hostname}" added successfully`)
    } catch (err) {
      setCrudError(err instanceof Error ? err.message : 'Failed to create device')
    } finally {
      setIsCreating(false)
    }
  }

  const handleUpdateDevice = async (id: number) => {
    setCrudError('')
    setCrudMessage('')
    try {
      // Convert null values to undefined for API
      const updateData = {
        hostname: editForm.hostname ?? undefined,
        ip_address: editForm.ip_address ?? undefined,
        mac_address: editForm.mac_address ?? undefined,
        model: editForm.model ?? undefined,
        serial_number: editForm.serial_number ?? undefined,
        firmware_version: editForm.firmware_version ?? undefined,
        site_id: editForm.site_id ?? undefined,
        status: editForm.status ?? undefined,
      }
      const updated = await updateDevice(id, updateData)
      setDevices(prev => prev.map(d => d.id === id ? updated : d))
      setEditingDeviceId(null)
      setEditForm({})
      setCrudMessage(`Device updated successfully`)
    } catch (err) {
      setCrudError(err instanceof Error ? err.message : 'Failed to update device')
    }
  }

  const handleDeleteDevice = async (id: number, hostname: string) => {
    const ok = await confirmDanger({
      title: `Delete device "${hostname}"?`,
      text: 'This action cannot be undone.',
      confirmText: 'Delete',
    })
    if (!ok) return
    setCrudError('')
    setCrudMessage('')
    try {
      await deleteDevice(id)
      queryClient.clear()
      setDevices(prev => prev.filter(d => d.id !== id))
      setSelectedManagedDeviceIds(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
      setCrudMessage(`Device "${hostname}" deleted`)
      toast.success(`Device "${hostname}" deleted`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete device'
      setCrudError(message)
      toast.error(message)
    }
  }

  const handleDeleteSelectedManaged = async () => {
    if (selectedManagedDeviceIds.size === 0) return
    const selected = devices.filter((device) => selectedManagedDeviceIds.has(device.id))
    const ok = await confirmDanger({
      title: `Delete ${selected.length} selected device${selected.length === 1 ? '' : 's'}?`,
      text: 'This will permanently remove the selected devices and their data from the database. This cannot be undone.',
      confirmText: 'Delete selected',
    })
    if (!ok) return
    setDeletingSelectedManaged(true)
    setCrudError('')
    setCrudMessage('')
    try {
      await Promise.all(selected.map((device) => deleteDevice(device.id)))
      queryClient.clear()
      setDevices((current) => current.filter((device) => !selectedManagedDeviceIds.has(device.id)))
      setSelectedManagedDeviceIds(new Set())
      setCrudMessage(`${selected.length} selected device${selected.length === 1 ? '' : 's'} deleted successfully`)
      toast.success(`${selected.length} selected device${selected.length === 1 ? '' : 's'} deleted`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete selected devices'
      setCrudError(message)
      toast.error(message)
    } finally {
      setDeletingSelectedManaged(false)
    }
  }

  const handleDeleteAll = async () => {
    if (devices.length === 0) return
    const ok = await confirmDanger({
      title: `Delete all ${devices.length} devices?`,
      text: 'This will permanently remove all devices and their data from the database. This cannot be undone.',
      confirmText: 'Delete All',
    })
    if (!ok) return
    setCrudError('')
    setCrudMessage('')
    try {
      const result = await deleteAllDevices()
      // Plain API cache invalidation cannot clear React Query snapshots held
      // by SNMP/detail pages, so remove every cached device response too.
      queryClient.clear()
      setDevices([])
      setSelectedManagedDeviceIds(new Set())
      setCrudMessage(`All ${result.deleted} devices deleted successfully`)
      toast.success(`All ${result.deleted} devices deleted`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete all devices'
      setCrudError(message)
      toast.error(message)
    }
  }

  const startEdit = (device: DeviceRecord) => {
    setEditingDeviceId(device.id)
    setEditForm({
      hostname: device.hostname,
      ip_address: device.ip_address,
      mac_address: device.mac_address ?? '',
      model: device.model ?? '',
      serial_number: device.serial_number ?? '',
      firmware_version: device.firmware_version ?? '',
      site_id: device.site_id ?? null,
    })
  }

  return (
    <div className="ip-scan-page p-4 md:p-6 space-y-4 md:space-y-5">
      <div>
        <h1 className="font-display font-bold text-2xl tracking-widest neon-cyan">{tr.scanTitle}</h1>
        <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>{tr.scanSubtitle}</p>
      </div>

      {error ? <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div> : null}


      {/* Dynamic SNMP subnet sweep — scans all .1–.254 IPs in the current discovery target */}

      <GlassCard className="p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">{tr.discover}</div>
            <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>Choose the modules you want, start chunked discovery, then add discovered devices to the database.</div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex flex-col">
              <input
                value={discoveryTarget}
                onChange={(event) => setDiscoveryTarget(event.target.value.replace(/[^\d./,-]/g, ''))}
                className="rounded border px-3 py-2 font-mono text-xs outline-none"
                style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)', minWidth: 180 }}
                placeholder="192.168.1.1-192.168.1.255 or /24"
              />
              <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>
                Single IP, start-end range, or CIDR. Maximum 255 IPs.
              </div>
            </div>
            <PermissionGuard permission="discovery:execute">
            <button
              onClick={handleDiscover}
              disabled={isDiscovering}
              className="rounded px-4 py-2 font-display text-xs tracking-wider uppercase transition disabled:opacity-60"
              style={{ background: isDiscovering ? 'rgba(255,170,0,0.2)' : 'rgba(0,212,255,0.16)', border: '1px solid rgba(0,212,255,0.3)', color: 'var(--t-text, #c8d8ee)' }}
            >
              {isDiscovering ? 'DISCOVERY RUNNING…' : tr.discover}
            </button>
            </PermissionGuard>
          </div>
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {moduleCatalog.map(module => (
            <label key={module.key} className="flex items-start gap-2 rounded-lg border px-3 py-2 text-xs" style={{ borderColor: 'rgba(0,212,255,0.16)', background: 'rgba(255,255,255,0.03)' }}>
              <input type="checkbox" checked={selectedModules.includes(module.key)} onChange={() => toggleModule(module.key)} />
              <span>
                <span className="font-display tracking-wider" style={{ color: 'var(--t-text, #c8d8ee)' }}>{module.label}</span>
                <span className="block font-mono mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>{module.description}</span>
              </span>
            </label>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-2 items-center">
          {discoveryResults.length > 0 && !isDiscovering && (
            <PermissionGuard permission="devices:create">
            <button
              onClick={handleStoreResults}
              className="rounded px-3 py-2 font-display text-xs tracking-wider uppercase transition hover:opacity-80"
              style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}
            >
              STORE ALL ({discoveryResults.length})
            </button>
            </PermissionGuard>
          )}
          <div className="font-mono text-xs self-center" style={{ color: 'var(--t-muted, #8899bb)' }}>{message || 'Discovery results will appear below as they stream in.'}</div>
        </div>

        {discoveryProgress ? (
          <div className="mt-4 rounded-lg p-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.12)' }}>
            <div className="flex items-center justify-between font-mono text-xs mb-2" style={{ color: 'var(--t-muted, #8899bb)' }}>
              <span>{discoveryProgress.network_range}</span>
              <span>{discoveryProgress.progress_pct}% · {discoveryProgress.discovered_count} discovered</span>
            </div>
            <div className="h-2 rounded-full" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.08))' }}>
              <div className="h-2 rounded-full" style={{ width: `${Math.max(discoveryProgress.progress_pct, 4)}%`, background: discoveryProgress.status === 'completed' ? '#00ff88' : '#00d4ff' }} />
            </div>
          </div>
        ) : null}
      </GlassCard>
 {!isDiscovering && discoveryResults.length > 0 && (
        <GlassCard className="p-4 md:p-5">
          {/* header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
            <div>
              <div className="font-display font-bold text-base tracking-wider neon-cyan">{tr.discovered}</div>
              {/* <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>
                {discoveryResults.length} device{discoveryResults.length !== 1 ? 's' : ''} found via ICMP/TCP scan
                {storedIps.size > 0 && <span style={{ color: '#00ff88' }}> · {storedIps.size} stored</span>}
              </div> */}
            </div>
            {discoveryResults.length > 0 && (
              <PermissionGuard permission="devices:create">
                <button onClick={handleStoreResults}
                  className="rounded-lg px-4 py-2 font-display text-xs tracking-wider font-semibold transition hover:opacity-80 shrink-0"
                  style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}>
                  STORE ALL ({discoveryResults.length - storedIps.size} new)
                </button>
              </PermissionGuard>
            )}
          </div>

          {/* device cards */}
          <div className="space-y-3">
            {sortedDiscoveryResults.map((device, idx) => {
              const item = device as Record<string, unknown>
              const ip       = String(item.ip_address ?? item.ip ?? '')
              const hostname = String(item.hostname ?? item.dns_hostname ?? item.snmp_name ?? ip)
              const mac      = String(item.mac_address ?? item.mac ?? '—')
              const status   = String(item.status ?? 'online')
              const deviceName = hostname !== ip ? hostname : `Device ${idx + 1}`
              const isStored = storedIps.has(ip)
              const isAdding = addingIps.has(ip)

              return (
                <div key={`${ip}-${idx}`} className="ip-discovery-card rounded-xl overflow-hidden transition-all"
                  style={{ border: isStored ? '1px solid rgba(0,255,136,0.25)' : '1px solid rgba(0,212,255,0.15)', background: isStored ? 'rgba(0,255,136,0.02)' : 'rgba(0,212,255,0.02)' }}>

                  <div className="ip-discovery-row grid grid-cols-[1.4fr_1fr_1.4fr_0.9fr_1.2fr_auto] items-center gap-3 px-4 py-3"
                    style={{ borderBottom: '1px solid rgba(0,212,255,0.08)', background: 'rgba(0,0,0,0.2)' }}>
                    <div className="min-w-0">
                      <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>Device Name</div>
                      <div className="font-display text-sm tracking-wider truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{deviceName}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>IP</div>
                      <div className="font-mono text-xs truncate" style={{ color: '#00d4ff' }}>{ip}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>Hostname</div>
                      <div className="font-mono text-xs truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{hostname}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>Status</div>
                      <div className="font-mono text-xs truncate" style={{ color: status === 'online' ? '#00ff88' : '#ff3366' }}>{status}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>MAC</div>
                      <div className="font-mono text-xs truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{mac}</div>
                    </div>
                    {!isStored && (
                      <PermissionGuard permission="devices:create">
                        <button onClick={() => handleStoreSingle(device)} disabled={isAdding}
                          className="font-mono text-xs px-3 py-1 rounded shrink-0 transition hover:opacity-80 disabled:opacity-50"
                          style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>
                          {isAdding ? 'Adding…' : '+ ADD'}
                        </button>
                      </PermissionGuard>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </GlassCard>
      )} 
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-2">NETWORK TOPOLOGY</div>
          <div className="font-mono text-xs mb-3" style={{ color: 'var(--t-muted, #8899bb)' }}>
            {topoNodes.length - 1} device(s) connected to gateway · {discoveryTarget}
          </div>
          <div className="relative" style={{ height: 320 }}>
            <canvas
              ref={canvasRef}
              className="w-full h-full"
              style={{ cursor: topoHover ? 'pointer' : 'default' }}
              onMouseMove={handleCanvasMouseMove}
              onMouseLeave={() => setTopoHover(null)}
            />
            {topoHover && topoHover !== 'gw' && (() => {
              const node = topoNodes.find(n => n.id === topoHover)
              if (!node) return null
              return (
                <div
                  className="absolute pointer-events-none rounded-lg px-3 py-2"
                  style={{
                    left: `${node.x * 100}%`,
                    top: `${node.y * 100}%`,
                    transform: 'translate(-50%, -140%)',
                    background: 'var(--t-card, rgba(4,14,33,0.95))',
                    border: '1px solid rgba(0,212,255,0.3)',
                    zIndex: 10,
                  }}
                >
                  <div className="font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{node.ip}</div>
                  <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{node.hostname}</div>
                  {node.mac ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>MAC: {node.mac}</div> : null}
                </div>
              )
            })()}
          </div>
          <div className="flex flex-wrap gap-4 mt-3 justify-center">
            {discoverySummary.map(entry => (
              <div key={entry.name} className="flex items-center gap-1.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>
                <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: entry.color }} />
                {entry.name}: <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{entry.value}</span>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-2">STORED DEVICES</div>
          <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Stored devices ready for monitoring ({devices.length})</div>
          <div className="space-y-3">
            {devices.length === 0 ? (
              <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No stored devices yet. Discover and add devices to see them here.</div>
            ) : (
              <>
                {(showAllStored ? devices : devices.slice(0, 5)).map(device => (
                  <div key={device.id} className="rounded-lg p-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="inline-block w-2 h-2 rounded-full" style={{ background: device.status === 'online' ? '#00ff88' : '#ff3366' }} />
                          <div className="font-display text-sm tracking-wider" style={{ color: 'var(--t-text, #c8d8ee)' }}>{device.hostname}</div>
                        </div>
                        <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>{device.ip_address} · {device.model ?? '—'} · {device.status}</div>
                        <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--t-muted, #667799)' }}>
                          {device.mac_address ? `MAC: ${device.mac_address} · ` : ''}{device.vendor_name ? `Vendor: ${device.vendor_name} · ` : ''}{device.device_type ? `Type: ${device.device_type}` : ''}
                        </div>
                      </div>
                      <div className="flex flex-col gap-2">
                        <Link to={`/device-monitoring/${device.id}`} className="font-mono text-xs text-center" style={{ color: '#00d4ff' }}>View Details</Link>
                      </div>
                    </div>
                  </div>
                ))}
                {devices.length > 5 && (
                  <button
                    onClick={() => setShowAllStored(!showAllStored)}
                    className="w-full rounded py-2 font-mono text-xs transition hover:opacity-80"
                    style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)', color: '#00d4ff' }}
                  >
                    {showAllStored ? `Show Less` : `Show All ${devices.length} Devices ▼`}
                  </button>
                )}
              </>
            )}
          </div>
        </GlassCard>
      </div>

      {/* ── DEVICE CRUD MODULE ── */}
      <GlassCard className="p-4 md:p-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <div>
            <div className="font-display font-bold text-base tracking-wider neon-cyan">DEVICE MANAGEMENT</div>
            <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>Add, edit, and delete devices · Assign to organizations and sites</div>
          </div>
          <div className="flex gap-2 shrink-0">
            <PermissionGuard permission="devices:delete">
            <button
              onClick={handleDeleteSelectedManaged}
              disabled={selectedManagedDeviceIds.size === 0 || deletingSelectedManaged}
              className="rounded px-4 py-2 font-display text-xs tracking-wider uppercase transition hover:opacity-80 disabled:opacity-40"
              style={{ background: 'rgba(255,51,102,0.12)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}
            >
              {deletingSelectedManaged ? 'DELETING…' : `DELETE SELECTED (${selectedManagedDeviceIds.size})`}
            </button>
            <button
              onClick={handleDeleteAll}
              disabled={devices.length === 0}
              className="rounded px-4 py-2 font-display text-xs tracking-wider uppercase transition hover:opacity-80 disabled:opacity-40"
              style={{ background: 'rgba(255,51,102,0.12)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}
            >
              🗑 DELETE ALL
            </button>
            </PermissionGuard>
            <PermissionGuard permission="devices:create">
            <button
              onClick={() => setShowAddDevice(!showAddDevice)}
              className="rounded px-4 py-2 font-display text-xs tracking-wider uppercase transition hover:opacity-80 shrink-0"
              style={{ background: showAddDevice ? 'rgba(255,51,102,0.12)' : 'rgba(0,255,136,0.12)', border: `1px solid ${showAddDevice ? 'rgba(255,51,102,0.3)' : 'rgba(0,255,136,0.3)'}`, color: showAddDevice ? '#ff3366' : '#00ff88' }}
            >
              {showAddDevice ? '✕ CANCEL' : '+ ADD DEVICE'}
            </button>
            </PermissionGuard>
          </div>
        </div>

        {crudError && <div className="font-mono text-xs mb-3" style={{ color: '#ff3366' }}>{crudError}</div>}
        {crudMessage && <div className="font-mono text-xs mb-3" style={{ color: '#00ff88' }}>{crudMessage}</div>}

        {/* Add Device Form */}
        {showAddDevice && (
          <div className="mb-6 rounded-lg p-4" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.15)' }}>
            <div className="font-display font-bold text-sm tracking-wider mb-3" style={{ color: '#00d4ff' }}>NEW DEVICE</div>
            
            {/* Organization & Site Selection */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Organization *</label>
                <div className="flex gap-2">
                  <select
                    value={selectedOrgId ?? ''}
                    onChange={(e) => setSelectedOrgId(e.target.value ? Number(e.target.value) : null)}
                    className="flex-1 rounded border px-3 py-2 font-mono text-xs outline-none"
                    style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  >
                    <option value="">Select organization</option>
                    {organizations.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}
                  </select>
                  <input
                    value={newOrg}
                    onChange={(e) => setNewOrg(e.target.value)}
                    className="flex-1 rounded border px-3 py-2 font-mono text-xs outline-none"
                    style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                    placeholder="Or create new"
                  />
                  <PermissionGuard permission="organizations:create">
                  <button
                    onClick={handleCreateOrg}
                    className="rounded px-3 py-2 font-mono text-xs transition hover:opacity-80"
                    style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
                  >
                    + Org
                  </button>
                  </PermissionGuard>
                </div>
              </div>
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Site *</label>
                <div className="flex gap-2">
                  <select
                    value={selectedSiteId ?? ''}
                    onChange={(e) => setSelectedSiteId(e.target.value ? Number(e.target.value) : null)}
                    className="flex-1 rounded border px-3 py-2 font-mono text-xs outline-none"
                    style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                    disabled={!selectedOrgId}
                  >
                    <option value="">Select site</option>
                    {sites.filter(s => s.organization_id === selectedOrgId).map(site => <option key={site.id} value={site.id}>{site.name}</option>)}
                  </select>
                  <input
                    value={newSite}
                    onChange={(e) => setNewSite(e.target.value)}
                    className="flex-1 rounded border px-3 py-2 font-mono text-xs outline-none"
                    style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                    placeholder="Or create new"
                    disabled={!selectedOrgId}
                  />
                  <PermissionGuard permission="sites:create">
                  <button
                    onClick={handleCreateSite}
                    disabled={!selectedOrgId}
                    className="rounded px-3 py-2 font-mono text-xs transition hover:opacity-80 disabled:opacity-40"
                    style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
                  >
                    + Site
                  </button>
                  </PermissionGuard>
                </div>
              </div>
            </div>

            {/* Device Fields */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: '#ff6644' }}>Hostname * (required)</label>
                <input
                  value={deviceForm.hostname}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, hostname: e.target.value }))}
                  className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                  style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  placeholder="e.g., router-01"
                />
              </div>
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: '#ff6644' }}>IP Address * (required)</label>
                <input
                  value={deviceForm.ip_address}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, ip_address: e.target.value }))}
                  className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                  style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  placeholder="e.g., 192.168.1.100"
                />
              </div>
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>MAC Address</label>
                <input
                  value={deviceForm.mac_address}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, mac_address: e.target.value }))}
                  className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                  style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  placeholder="e.g., 00:11:22:33:44:55"
                />
              </div>
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Model</label>
                <input
                  value={deviceForm.model}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, model: e.target.value }))}
                  className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                  style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  placeholder="e.g., Cisco ISR 4321"
                />
              </div>
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Serial Number</label>
                <input
                  value={deviceForm.serial_number}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, serial_number: e.target.value }))}
                  className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                  style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  placeholder="e.g., FTX12345678"
                />
              </div>
              <div>
                <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Firmware Version</label>
                <input
                  value={deviceForm.firmware_version}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, firmware_version: e.target.value }))}
                  className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                  style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                  placeholder="e.g., 16.9.4"
                />
              </div>
            </div>

            <PermissionGuard permission="devices:create">
            <button
              onClick={handleCreateDevice}
              disabled={isCreating}
              className="rounded px-6 py-2 font-display text-xs tracking-wider uppercase transition disabled:opacity-60"
              style={{ background: 'rgba(0,255,136,0.16)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}
            >
              {isCreating ? 'CREATING…' : 'CREATE DEVICE'}
            </button>
            </PermissionGuard>
          </div>
        )}

        {/* Device List with Edit/Delete */}
        <div className="space-y-3">
          {devices.length === 0 ? (
            <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No devices yet. Add a device or run discovery to populate.</div>
          ) : (
            devices.map(device => {
              const isEditing = editingDeviceId === device.id
              const site = device.site_id ? sites.find(s => s.id === device.site_id) : null
              const org = site ? organizations.find(o => o.id === site.organization_id) : null

              if (isEditing) {
                return (
                  <div key={device.id} className="rounded-lg p-4" style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.2)' }}>
                    <div className="font-display text-sm tracking-wider mb-3" style={{ color: '#00d4ff' }}>EDIT DEVICE</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Hostname</label>
                        <input
                          value={editForm.hostname ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, hostname: e.target.value }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        />
                      </div>
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>IP Address</label>
                        <input
                          value={editForm.ip_address ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, ip_address: e.target.value }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        />
                      </div>
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>MAC Address</label>
                        <input
                          value={editForm.mac_address ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, mac_address: e.target.value }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        />
                      </div>
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Model</label>
                        <input
                          value={editForm.model ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, model: e.target.value }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        />
                      </div>
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Serial Number</label>
                        <input
                          value={editForm.serial_number ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, serial_number: e.target.value }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        />
                      </div>
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Firmware Version</label>
                        <input
                          value={editForm.firmware_version ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, firmware_version: e.target.value }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        />
                      </div>
                      <div>
                        <label className="font-mono text-xs mb-1 block" style={{ color: 'var(--t-muted, #8899bb)' }}>Site</label>
                        <select
                          value={editForm.site_id ?? ''}
                          onChange={(e) => setEditForm(prev => ({ ...prev, site_id: e.target.value ? Number(e.target.value) : null }))}
                          className="w-full rounded border px-3 py-2 font-mono text-xs outline-none"
                          style={{ background: 'var(--t-card-alpha, rgba(4,14,33,0.85))', borderColor: 'rgba(0,212,255,0.24)', color: 'var(--t-text, #c8d8ee)' }}
                        >
                          <option value="">No site</option>
                          {sites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}
                        </select>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <PermissionGuard permission="devices:update">
                      <button
                        onClick={() => handleUpdateDevice(device.id)}
                        className="rounded px-4 py-2 font-mono text-xs transition hover:opacity-80"
                        style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}
                      >
                        ✓ SAVE
                      </button>
                      </PermissionGuard>
                      <button
                        onClick={() => { setEditingDeviceId(null); setEditForm({}) }}
                        className="rounded px-4 py-2 font-mono text-xs transition hover:opacity-80"
                        style={{ background: 'rgba(255,51,102,0.12)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}
                      >
                        ✕ CANCEL
                      </button>
                    </div>
                  </div>
                )
              }

              return (
                <div key={device.id} className="ip-managed-device rounded-lg p-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
                  <div className="flex flex-col sm:flex-row items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <input
                          type="checkbox"
                          checked={selectedManagedDeviceIds.has(device.id)}
                          onChange={() => setSelectedManagedDeviceIds((current) => {
                            const next = new Set(current)
                            if (next.has(device.id)) next.delete(device.id)
                            else next.add(device.id)
                            return next
                          })}
                          aria-label={`Select ${device.hostname}`}
                          className="h-4 w-4 accent-[#ff3366]"
                        />
                        <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: device.status === 'online' ? '#00ff88' : '#ff3366' }} />
                        <div className="font-display text-sm tracking-wider truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{device.hostname}</div>
                        <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{device.ip_address}</div>
                      </div>
                      <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>
                        {device.model && <span>Model: {device.model} · </span>}
                        {device.mac_address && <span>MAC: {device.mac_address} · </span>}
                        {device.vendor_name && <span>Vendor: {device.vendor_name} · </span>}
                        {device.device_type && <span>Type: {device.device_type} · </span>}
                        {device.snmp_version && <span>SNMP: {device.snmp_version} · </span>}
                        {org && <span>Org: {org.name} · </span>}
                        {site && <span>Site: {site.name}</span>}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Link to={`/device-monitoring/${device.id}`} className="font-mono text-xs px-3 py-1 rounded" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)' }}>Details</Link>
                      <PermissionGuard permission="devices:update">
                      <button
                        onClick={() => startEdit(device)}
                        className="font-mono text-xs px-3 py-1 rounded transition hover:opacity-80"
                        style={{ background: 'rgba(255,170,0,0.12)', border: '1px solid rgba(255,170,0,0.3)', color: '#ffaa00' }}
                      >
                        Edit
                      </button>
                      </PermissionGuard>
                      <PermissionGuard permission="devices:delete">
                      <button
                        onClick={() => handleDeleteDevice(device.id, device.hostname)}
                        className="font-mono text-xs px-3 py-1 rounded transition hover:opacity-80"
                        style={{ background: 'rgba(255,51,102,0.12)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}
                      >
                        Delete
                      </button>
                      </PermissionGuard>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </GlassCard>

     

      {/* <GlassCard className="p-5">
        <div className="font-display font-bold text-base tracking-wider neon-cyan mb-2">DISCOVERY DETAILS</div>
        <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Every module payload is rendered here with 25 rows per page so you can step through the full discovery output.</div>
        {eventRows.length === 0 ? (
          <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No discovery details yet. Start a discovery run to populate this view.</div>
        ) : (
          <>
            <div className="space-y-3">
              {pagedRows.map(row => (
                <div key={row.id} className="rounded-lg p-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
                  <div className="font-display text-sm tracking-wider" style={{ color: 'var(--t-text, #c8d8ee)' }}>{row.title}</div>
                  <div className="font-mono text-xs mt-1 break-all" style={{ color: 'var(--t-muted, #8899bb)' }}>{row.detail}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between">
              <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Page {page} of {totalPages} · {eventRows.length} rows</div>
              <div className="flex gap-2">
                <button onClick={() => setPage(prev => Math.max(1, prev - 1))} disabled={page === 1} className="rounded px-2 py-1 font-mono text-xs" style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', color: 'var(--t-text, #c8d8ee)' }}>← Prev</button>
                <button onClick={() => setPage(prev => Math.min(totalPages, prev + 1))} disabled={page >= totalPages} className="rounded px-2 py-1 font-mono text-xs" style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', color: 'var(--t-text, #c8d8ee)' }}>Next →</button>
              </div>
            </div>
          </>
        )}
      </GlassCard> */}

      {/* SNMP Discovery Modal */}
      {showSNMPModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }}
          onClick={e => { if (e.target === e.currentTarget) setShowSNMPModal(false) }}>
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl"
            style={{ background: 'rgba(8,25,55,0.98)', border: '2px solid rgba(0,212,255,0.3)' }}>
            <SNMPSubnetDiscovery
              subnet={discoveryTarget}
              onDevicesStored={async () => {
                await loadInitialData()
                setShowSNMPModal(false)
              }}
            />
            <div className="p-4 border-t" style={{ borderColor: 'rgba(0,212,255,0.1)' }}>
              <button
                onClick={() => setShowSNMPModal(false)}
                className="w-full py-2 rounded font-mono text-xs font-bold transition-all"
                style={{ background: 'rgba(136,153,187,0.12)', border: '1px solid rgba(136,153,187,0.3)', color: 'var(--t-muted, #8899bb)' }}>
                CLOSE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
