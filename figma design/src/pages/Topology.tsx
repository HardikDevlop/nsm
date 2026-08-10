import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import GlassCard from '../components/GlassCard'
import { listDevices, listAlerts, detectLocalSubnet, pingIps, type AlertRecord, type DeviceRecord } from '../lib/api'

type NodeType = 'gateway' | 'server' | 'container' | 'switch' | 'firewall' | 'router' | 'nginx' | 'isp'

type Node = {
  id: string
  label: string
  ip: string
  mac: string
  type: NodeType
  x: number
  y: number
  status: 'online' | 'warning' | 'offline'
  latency: number
  bandwidth: number
  packetLoss: number
  health: number
}

type Edge = { from: string; to: string; latency: number; loss: number }

const nodeIcons: Record<NodeType, string> = {
  isp: 'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0',
  firewall: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
  router: 'M13 10V3L4 14h7v7l9-11h-7z',
  switch: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
  server: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
  container: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
  nginx: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2',
  gateway: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
}

const nodeColors: Record<NodeType, string> = {
  gateway: '#00d4ff',
  isp: '#7c3aed',
  firewall: '#ff3366',
  router: '#00d4ff',
  switch: '#00d4ff',
  server: '#00ff88',
  container: '#ffaa00',
  nginx: '#00d4ff',
}

const statusColor = { online: '#00ff88', warning: '#ffaa00', offline: '#ff3366' }

function getEdgeColor(loss: number, latency: number) {
  if (loss > 1 || latency > 200) return '#ff3366'
  if (loss > 0.1 || latency > 50) return '#ffaa00'
  return '#00d4ff'
}

function classifyDevice(hostname: string, ip: string): NodeType {
  const h = hostname.toLowerCase()
  if (h.includes('firewall') || h.includes('fw')) return 'firewall'
  if (h.includes('router') || h.includes('gw')) return 'router'
  if (h.includes('switch') || h.includes('sw-')) return 'switch'
  if (h.includes('nginx') || h.includes('lb')) return 'nginx'
  if (h.includes('container') || h.includes('docker') || h.includes('k8s')) return 'container'
  if (h.includes('srv') || h.includes('server') || h.includes('web') || h.includes('db') || h.includes('app')) return 'server'
  return 'server'
}

/** Arrange nodes in a radial layout around center */
function computeLayout(
  centerX: number,
  centerY: number,
  deviceCount: number,
  radiusX: number,
  radiusY: number,
): Array<{ x: number; y: number }> {
  if (deviceCount === 0) return []
  if (deviceCount === 1) return [{ x: centerX + radiusX, y: centerY }]
  const positions: Array<{ x: number; y: number }> = []
  const angleStep = (2 * Math.PI) / deviceCount
  for (let i = 0; i < deviceCount; i++) {
    const angle = angleStep * i - Math.PI / 2 // start from top
    positions.push({
      x: centerX + radiusX * Math.cos(angle),
      y: centerY + radiusY * Math.sin(angle),
    })
  }
  return positions
}

export default function Topology() {
  const [selected, setSelected] = useState<Node | null>(null)
  const [search, setSearch] = useState('')
  const [zoom, setZoom] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [gatewayIp, setGatewayIp] = useState<string>('')
  const [topoStatuses, setTopoStatuses] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const svgRef = useRef<SVGSVGElement>(null)

  // Load devices + gateway
  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [deviceData, alertData, subnet] = await Promise.all([listDevices(), listAlerts(), detectLocalSubnet()])
      setDevices(deviceData)
      setAlerts(alertData)
      if (subnet?.ip) setGatewayIp(subnet.ip)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load topology data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let ignore = false
    void (async () => {
      await loadData()
    })()
    return () => { ignore = true }
  }, [loadData])

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [loadData])

  // Build dynamic nodes + edges
  const { nodes, edges } = useMemo(() => {
    const CX = 500
    const CY = 260
    const RX = 340
    const RY = 200

    // Gateway node
    const gwNode: Node = {
      id: 'gateway',
      label: gatewayIp ? `Gateway · ${gatewayIp}` : 'Local Gateway',
      ip: gatewayIp,
      mac: '',
      type: 'gateway',
      x: CX,
      y: CY,
      status: 'online',
      latency: 1,
      bandwidth: 1000,
      packetLoss: 0,
      health: 100,
    }

    if (devices.length === 0) {
      return { nodes: [gwNode], edges: [] as Edge[] }
    }

    // Device nodes in radial layout
    const positions = computeLayout(CX, CY, devices.length, RX, RY)
    const deviceNodes: Node[] = devices.map((d, i) => {
      const alertCount = alerts.filter(a => a.device_id === d.id).length
      const liveStatus = topoStatuses[d.ip_address]
      let status: Node['status']
      if (liveStatus !== undefined) {
        status = liveStatus ? 'online' : 'offline'
      } else {
        status = d.status === 'offline' ? 'offline' : alertCount > 0 ? 'warning' : 'online'
      }
      const health = Math.max(20, 100 - alertCount * 10 - (status === 'offline' ? 30 : 0))
      return {
        id: `dev-${d.id}`,
        label: d.hostname || d.ip_address,
        ip: d.ip_address,
        mac: d.mac_address ?? '',
        type: classifyDevice(d.hostname, d.ip_address),
        x: positions[i].x,
        y: positions[i].y,
        status,
        latency: liveStatus === false ? 999 : Math.max(1, Math.min(300, 5 + alertCount * 8)),
        bandwidth: Math.max(50, 800 - i * 20),
        packetLoss: liveStatus === false ? 100 : Math.max(0, Number((alertCount * 0.2).toFixed(2))),
        health,
      }
    })

    // Edges: gateway → each device
    const deviceEdges: Edge[] = deviceNodes.map(d => ({
      from: 'gateway',
      to: d.id,
      latency: d.latency,
      loss: d.packetLoss,
    }))

    return { nodes: [gwNode, ...deviceNodes], edges: deviceEdges }
  }, [devices, alerts, gatewayIp, topoStatuses])

  // Auto-ping every 15s
  const pingNodes = useCallback(async () => {
    const ips = devices.map(d => d.ip_address).filter(Boolean)
    if (ips.length === 0) return
    try {
      const result = await pingIps(ips, 1000)
      const statuses: Record<string, boolean> = {}
      for (const r of result.results) {
        statuses[r.ip] = r.reachable
      }
      setTopoStatuses(statuses)
    } catch {
      // silent — keep last known status
    }
  }, [devices])

  useEffect(() => {
    // Initial ping after load
    if (devices.length > 0) void pingNodes()
    const interval = setInterval(pingNodes, 15000)
    return () => clearInterval(interval)
  }, [pingNodes, devices.length])

  const filteredNodes = search
    ? nodes.filter(n => n.label.toLowerCase().includes(search.toLowerCase()) || n.ip.toLowerCase().includes(search.toLowerCase()))
    : nodes

  const visibleIds = new Set(filteredNodes.map(n => n.id))
  const visibleEdges = edges.filter(e => visibleIds.has(e.from) && visibleIds.has(e.to))

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as Element).closest('.node-group')) return
    setDragging(true)
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
  }, [pan])

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
  }, [dragging, dragStart])

  const onMouseUp = useCallback(() => setDragging(false), [])

  const onlineCount = nodes.filter(n => n.status === 'online').length
  const warningCount = nodes.filter(n => n.status === 'warning').length
  const offlineCount = nodes.filter(n => n.status === 'offline').length

  // Types present in current nodes for legend
  const activeTypes = new Set(nodes.map(n => n.type))

  return (
    <div className="p-4 md:p-6 space-y-4 h-full flex flex-col">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">NETWORK TOPOLOGY</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            Dynamic topology — {devices.length} device{devices.length !== 1 ? 's' : ''} · auto-ping 15s
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative flex-1 sm:flex-none min-w-[120px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8899bb" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
            </svg>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search nodes..."
              className="glass-bright rounded-lg pl-9 pr-4 py-2 font-mono text-xs outline-none w-full sm:w-48"
              style={{ color: '#c8d8ee', border: '1px solid rgba(0,212,255,0.2)' }} />
          </div>
          <button onClick={() => { void loadData(); void pingNodes() }}
            className="glass-bright px-3 h-8 rounded font-mono text-xs transition-all hover:bg-cyan-400/10 flex items-center gap-1.5"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            <span className="hidden sm:inline">REFRESH</span>
          </button>
          <div className="flex gap-1">
            <button onClick={() => setZoom(z => Math.min(z + 0.2, 3))}
              className="glass-bright w-8 h-8 rounded flex items-center justify-center font-mono text-lg neon-cyan transition-all hover:bg-cyan-400/10"
              style={{ border: '1px solid rgba(0,212,255,0.25)' }}>+</button>
            <button onClick={() => setZoom(z => Math.max(z - 0.2, 0.4))}
              className="glass-bright w-8 h-8 rounded flex items-center justify-center font-mono text-lg neon-cyan transition-all hover:bg-cyan-400/10"
              style={{ border: '1px solid rgba(0,212,255,0.25)' }}>−</button>
            <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}
              className="glass-bright px-2 sm:px-3 h-8 rounded font-mono text-xs transition-all hover:bg-cyan-400/10"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#8899bb' }}>RESET</button>
          </div>
        </div>
      </div>

      {error ? <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div> : null}

      <div className="flex flex-col md:flex-row gap-4 flex-1 min-h-0">
        {/* SVG canvas */}
        <GlassCard className="flex-1 min-h-[300px] md:min-h-0 overflow-hidden relative" style={{ cursor: dragging ? 'grabbing' : 'grab' }}>
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="font-mono text-sm" style={{ color: '#8899bb' }}>Loading topology…</div>
            </div>
          ) : nodes.length <= 1 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#8899bb" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" /><path d="M12 8v4m0 4h.01" />
              </svg>
              <div className="font-mono text-sm text-center" style={{ color: '#8899bb' }}>
                No devices found in database.<br />
                Run a discovery and add devices to build the topology.
              </div>
            </div>
          ) : (
            <svg ref={svgRef} width="100%" height="100%"
              onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}
              onWheel={e => setZoom(z => Math.max(0.4, Math.min(3, z - e.deltaY * 0.001)))}>
              <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
                {/* Edges */}
                {visibleEdges.map((e, i) => {
                  const from = nodes.find(n => n.id === e.from)!
                  const to = nodes.find(n => n.id === e.to)!
                  const color = getEdgeColor(e.loss, e.latency)
                  const mx = (from.x + to.x) / 2
                  const my = (from.y + to.y) / 2
                  return (
                    <g key={i}>
                      <line x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                        stroke={color} strokeWidth={1.5} strokeOpacity={0.5}
                        strokeDasharray={e.loss > 1 ? '6 4' : 'none'} />
                      <text x={mx} y={my - 6} textAnchor="middle"
                        style={{ fontSize: 9, fill: color, fontFamily: 'JetBrains Mono', opacity: 0.8 }}>
                        {e.latency < 999 ? `${e.latency}ms` : 'DOWN'}
                      </text>
                    </g>
                  )
                })}

                {/* Nodes */}
                {filteredNodes.map(node => {
                  const color = nodeColors[node.type]
                  const sc = statusColor[node.status]
                  const isSelected = selected?.id === node.id
                  return (
                    <g key={node.id} className="node-group" style={{ cursor: 'pointer' }}
                      onClick={() => setSelected(s => s?.id === node.id ? null : node)}>
                      {/* Glow ring */}
                      <circle cx={node.x} cy={node.y} r={28}
                        fill={isSelected ? `${color}20` : 'transparent'}
                        stroke={isSelected ? color : 'transparent'}
                        strokeWidth={1.5} />
                      {/* Node circle */}
                      <circle cx={node.x} cy={node.y} r={20}
                        fill="rgba(8,25,55,0.85)"
                        stroke={color} strokeWidth={isSelected ? 2 : 1.5}
                        style={{ filter: `drop-shadow(0 0 8px ${color}60)` }} />
                      {/* Status dot */}
                      <circle cx={node.x + 14} cy={node.y - 14} r={5}
                        fill={sc} style={{ filter: `drop-shadow(0 0 4px ${sc})` }} />
                      {/* Icon */}
                      <svg x={node.x - 10} y={node.y - 10} width={20} height={20} viewBox="0 0 24 24" fill="none">
                        <path d={nodeIcons[node.type]} stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      {/* Label */}
                      <text x={node.x} y={node.y + 36} textAnchor="middle"
                        style={{ fontSize: 10, fill: '#c8d8ee', fontFamily: 'JetBrains Mono', fontWeight: 500 }}>
                        {node.label}
                      </text>
                      {/* IP under label */}
                      {node.ip ? (
                        <text x={node.x} y={node.y + 47} textAnchor="middle"
                          style={{ fontSize: 8, fill: '#667799', fontFamily: 'JetBrains Mono' }}>
                          {node.ip}
                        </text>
                      ) : null}
                      <text x={node.x} y={node.y + 58} textAnchor="middle"
                        style={{ fontSize: 9, fill: sc, fontFamily: 'JetBrains Mono' }}>
                        {node.health}%
                      </text>
                    </g>
                  )
                })}
              </g>
            </svg>
          )}

          {/* Legend */}
          <div className="absolute bottom-2 left-2 md:bottom-4 md:left-4 glass rounded-lg p-2 md:p-3">
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {Array.from(activeTypes).map(type => (
                <div key={type} className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 md:w-3 md:h-3 rounded-full" style={{ background: nodeColors[type], boxShadow: `0 0 6px ${nodeColors[type]}` }} />
                  <span className="font-mono text-[10px] md:text-xs capitalize" style={{ color: '#8899bb' }}>{type}</span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 border-t pt-1 mt-1" style={{ borderColor: 'rgba(0,212,255,0.1)' }}>
              {Object.entries(statusColor).map(([s, c]) => (
                <div key={s} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ background: c }} />
                  <span className="font-mono text-[9px] md:text-[10px] capitalize" style={{ color: '#8899bb' }}>{s}</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>

        {/* Node detail */}
        <div className="w-full md:w-[260px] shrink-0">
          {selected ? (
            <GlassCard className="p-4 space-y-4" glow="cyan">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`status-dot ${selected.status}`} />
                  <div className="font-display font-bold text-sm neon-cyan tracking-wider">{selected.label}</div>
                </div>
                <div className="font-mono text-xs capitalize px-2 py-0.5 rounded w-fit"
                  style={{ color: nodeColors[selected.type], background: `${nodeColors[selected.type]}15`, border: `1px solid ${nodeColors[selected.type]}30` }}>
                  {selected.type}
                </div>
                {selected.ip ? (
                  <div className="font-mono text-[11px] mt-1" style={{ color: '#8899bb' }}>IP: {selected.ip}</div>
                ) : null}
                {selected.mac ? (
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>MAC: {selected.mac}</div>
                ) : null}
              </div>
              {[
                { l: 'Latency', v: `${selected.latency}ms`, c: selected.latency > 100 ? '#ff3366' : '#00ff88' },
                { l: 'Bandwidth', v: `${selected.bandwidth} Mbps`, c: '#00d4ff' },
                { l: 'Packet Loss', v: `${selected.packetLoss}%`, c: selected.packetLoss > 0.5 ? '#ff3366' : '#00ff88' },
                { l: 'Health Score', v: `${selected.health}%`, c: selected.health > 80 ? '#00ff88' : selected.health > 50 ? '#ffaa00' : '#ff3366' },
              ].map(m => (
                <div key={m.l} className="flex justify-between items-center py-2" style={{ borderBottom: '1px solid rgba(0,212,255,0.06)' }}>
                  <span className="font-mono text-xs" style={{ color: '#8899bb' }}>{m.l}</span>
                  <span className="font-mono text-sm font-semibold" style={{ color: m.c }}>{m.v}</span>
                </div>
              ))}
              <div className="mt-2">
                <div className="font-mono text-xs mb-2" style={{ color: '#8899bb' }}>HEALTH</div>
                <div className="h-2 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
                  <div className="h-2 rounded-full" style={{
                    width: `${selected.health}%`,
                    background: selected.health > 80 ? '#00ff88' : selected.health > 50 ? '#ffaa00' : '#ff3366',
                  }} />
                </div>
              </div>
            </GlassCard>
          ) : (
            <GlassCard className="p-4 flex flex-col items-center justify-center text-center h-40">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#8899bb" strokeWidth="1.5">
                <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
              </svg>
              <p className="font-mono text-xs mt-3" style={{ color: '#8899bb' }}>Click a node to inspect its metrics</p>
            </GlassCard>
          )}

          {/* Summary stats */}
          <GlassCard className="p-4 mt-4 space-y-3">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">TOPOLOGY STATS</div>
            {[
              { l: 'Total Nodes', v: nodes.length },
              { l: 'Online', v: onlineCount, c: '#00ff88' },
              { l: 'Warning', v: warningCount, c: '#ffaa00' },
              { l: 'Offline', v: offlineCount, c: '#ff3366' },
              { l: 'Total Links', v: edges.length },
              { l: 'Devices', v: devices.length },
            ].map(s => (
              <div key={s.l} className="flex justify-between">
                <span className="font-mono text-xs" style={{ color: '#8899bb' }}>{s.l}</span>
                <span className="font-mono text-sm font-semibold" style={{ color: s.c ?? '#c8d8ee' }}>{s.v}</span>
              </div>
            ))}
          </GlassCard>
        </div>
      </div>
    </div>
  )
}
