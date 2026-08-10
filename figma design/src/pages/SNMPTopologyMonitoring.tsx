import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import {
  getSNMPLLDPNeighbors,
  getSNMPRoutingTable,
  getSNMPVLANs,
  getSNMPSystemInfo,
  type SNMPLLDPNeighbor,
  type SNMPRoutingEntry,
  type SNMPVLANInfo,
  type SNMPSystemInfo,
} from '../lib/api'

type ActiveTab = 'lldp' | 'routing' | 'vlans'

// ── Helpers ───────────────────────────────────────────────────────────────────

function EmptyState({ message, onBack }: { message: string; onBack: () => void }) {
  return (
    <div className="py-10 text-center">
      <div className="font-mono text-sm mb-2" style={{ color: '#8899bb' }}>{message}</div>
      <div className="font-mono text-xs" style={{ color: '#667799' }}>No Data Available From Device</div>
    </div>
  )
}

// ── LLDP Table ────────────────────────────────────────────────────────────────

function LLDPTable({ neighbors, deviceId }: { neighbors: SNMPLLDPNeighbor[]; deviceId: number }) {
  const [search, setSearch] = useState('')

  const filtered = neighbors.filter(n => {
    const q = search.toLowerCase()
    return !q ||
      n.remote_device.toLowerCase().includes(q) ||
      n.remote_port.toLowerCase().includes(q) ||
      n.local_port.toLowerCase().includes(q) ||
      (n.remote_mgmt_ip ?? '').toLowerCase().includes(q)
  })

  if (neighbors.length === 0) {
    return <EmptyState message="No LLDP Neighbors Found" onBack={() => {}} />
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00d4ff' }}>{neighbors.length}</div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Neighbors</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00ff88' }}>
            {new Set(neighbors.map(n => n.local_port)).size}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Local Ports</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#7c3aed' }}>
            {neighbors.filter(n => n.remote_mgmt_ip).length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>With Mgmt IP</div>
        </GlassCard>
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Search neighbors..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full px-3 py-2 rounded font-mono text-xs"
        style={{ background: 'rgba(8,25,55,0.6)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }}
      />

      {/* Neighbor Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(n => (
          <GlassCard key={n.id} className="p-4 space-y-3">
            <div className="flex items-start gap-3">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8">
                  <path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-mono text-sm font-bold truncate" style={{ color: '#c8d8ee' }}>
                  {n.remote_device}
                </div>
                {n.remote_system_name && n.remote_system_name !== n.remote_device && (
                  <div className="font-mono text-[10px] truncate" style={{ color: '#667799' }}>
                    {n.remote_system_name}
                  </div>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { l: 'Local Port', v: n.local_port },
                { l: 'Remote Port', v: n.remote_port },
                { l: 'Mgmt IP', v: n.remote_mgmt_ip ?? '—' },
                { l: 'Updated', v: new Date(n.last_updated).toLocaleTimeString() },
              ].map(f => (
                <div key={f.l}>
                  <div className="font-mono text-[9px]" style={{ color: '#556677' }}>{f.l}</div>
                  <div className="font-mono text-xs truncate" style={{ color: '#c8d8ee' }}>{f.v}</div>
                </div>
              ))}
            </div>
            {n.capabilities && n.capabilities.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {n.capabilities.map(cap => (
                  <span
                    key={cap}
                    className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.2)' }}
                  >
                    {cap}
                  </span>
                ))}
              </div>
            )}
          </GlassCard>
        ))}
      </div>
    </div>
  )
}

// ── Routing Table ─────────────────────────────────────────────────────────────

function RoutingTable({ routes }: { routes: SNMPRoutingEntry[] }) {
  const [search, setSearch] = useState('')
  const [protoFilter, setProtoFilter] = useState<string>('all')

  const protocols = Array.from(new Set(routes.map(r => r.protocol).filter(Boolean))) as string[]

  const filtered = routes.filter(r => {
    const matchProto = protoFilter === 'all' || r.protocol === protoFilter
    const q = search.toLowerCase()
    const matchSearch = !q ||
      (r.destination ?? '').toLowerCase().includes(q) ||
      (r.next_hop ?? '').toLowerCase().includes(q) ||
      (r.interface ?? '').toLowerCase().includes(q)
    return matchProto && matchSearch
  })

  if (routes.length === 0) {
    return <EmptyState message="No Routing Entries Found" onBack={() => {}} />
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00d4ff' }}>{routes.length}</div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Routes</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00ff88' }}>
            {routes.filter(r => r.status === 'active').length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Active</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#7c3aed' }}>
            {protocols.length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Protocols</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#ffaa00' }}>
            {routes.filter(r => r.destination === '0.0.0.0/0' || r.destination === '0.0.0.0').length > 0 ? '✓' : '—'}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Default Route</div>
        </GlassCard>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search routes..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-[160px] px-3 py-1.5 rounded font-mono text-xs"
          style={{ background: 'rgba(8,25,55,0.6)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }}
        />
        {protocols.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {['all', ...protocols].map(p => (
              <button
                key={p}
                onClick={() => setProtoFilter(p)}
                className="font-mono text-xs px-2.5 py-1 rounded transition-all"
                style={{
                  background: protoFilter === p ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: protoFilter === p ? '#00d4ff' : '#8899bb',
                  border: `1px solid ${protoFilter === p ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                }}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        )}
        <span className="font-mono text-xs" style={{ color: '#667799' }}>{filtered.length} shown</span>
      </div>

      {/* Table */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table className="w-full" style={{ minWidth: 520 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                {['Destination', 'Next Hop', 'Interface', 'Protocol', 'Metric', 'Status'].map(h => (
                  <th
                    key={h}
                    className="text-left px-4 py-3 font-mono text-xs sticky top-0"
                    style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => (
                <tr key={r.id} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                  <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#00d4ff' }}>
                    {r.destination || '—'}
                    {(r.destination === '0.0.0.0/0' || r.destination === '0.0.0.0') && (
                      <span className="ml-2 font-mono text-[9px] px-1.5 py-0.5 rounded"
                        style={{ color: '#00ff88', background: 'rgba(0,255,136,0.1)' }}>
                        DEFAULT
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#c8d8ee' }}>{r.next_hop || '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#8899bb' }}>{r.interface || '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#7c3aed' }}>{r.protocol || '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#8899bb' }}>
                    {r.metric !== undefined ? r.metric : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <SNMPStatusBadge status={r.status === 'active' ? 'active' : 'inactive'} size="xs" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

// ── VLAN Table ────────────────────────────────────────────────────────────────

function VLANTable({ vlans }: { vlans: SNMPVLANInfo[] }) {
  const [search, setSearch] = useState('')

  const filtered = vlans.filter(v => {
    const q = search.toLowerCase()
    return !q ||
      String(v.vlan_id).includes(q) ||
      (v.vlan_name ?? '').toLowerCase().includes(q)
  })

  if (vlans.length === 0) {
    return <EmptyState message="No VLANs Found" onBack={() => {}} />
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00d4ff' }}>{vlans.length}</div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Total VLANs</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00ff88' }}>
            {vlans.filter(v => v.status === 'active').length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Active</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#8899bb' }}>
            {vlans.filter(v => v.status === 'inactive').length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Inactive</div>
        </GlassCard>
      </div>

      <input
        type="text"
        placeholder="Search VLANs by ID or name..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full px-3 py-2 rounded font-mono text-xs"
        style={{ background: 'rgba(8,25,55,0.6)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(v => (
          <GlassCard key={v.id} className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="font-mono text-sm font-bold px-2 py-0.5 rounded"
                  style={{ background: 'rgba(124,58,237,0.15)', color: '#7c3aed', border: '1px solid rgba(124,58,237,0.3)' }}
                >
                  VLAN {v.vlan_id}
                </span>
                {v.vlan_name && (
                  <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{v.vlan_name}</span>
                )}
              </div>
              <SNMPStatusBadge status={v.status === 'active' ? 'active' : 'inactive'} size="xs" />
            </div>

            {(v.tagged_ports && v.tagged_ports.length > 0) && (
              <div>
                <div className="font-mono text-[9px] mb-1" style={{ color: '#556677' }}>TAGGED PORTS</div>
                <div className="flex flex-wrap gap-1">
                  {v.tagged_ports.map(p => (
                    <span
                      key={p}
                      className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff' }}
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(v.untagged_ports && v.untagged_ports.length > 0) && (
              <div>
                <div className="font-mono text-[9px] mb-1" style={{ color: '#556677' }}>UNTAGGED PORTS</div>
                <div className="flex flex-wrap gap-1">
                  {v.untagged_ports.map(p => (
                    <span
                      key={p}
                      className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(0,255,136,0.1)', color: '#00ff88' }}
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="font-mono text-[9px]" style={{ color: '#445566' }}>
              Updated: {new Date(v.last_updated).toLocaleString()}
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SNMPTopologyMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [tab, setTab] = useState<ActiveTab>('lldp')
  const [neighbors, setNeighbors] = useState<SNMPLLDPNeighbor[]>([])
  const [routes, setRoutes] = useState<SNMPRoutingEntry[]>([])
  const [vlans, setVlans] = useState<SNMPVLANInfo[]>([])
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [lldpData, routeData, vlanData, sysData] = await Promise.all([
        getSNMPLLDPNeighbors(id),
        getSNMPRoutingTable(id),
        getSNMPVLANs(id),
        getSNMPSystemInfo(id),
      ])
      setNeighbors(lldpData)
      setRoutes(routeData)
      setVlans(vlanData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topology data')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const t = setInterval(() => void load(), 120_000)
    return () => clearInterval(t)
  }, [load])

  const tabs: Array<{ key: ActiveTab; label: string; count: number }> = [
    { key: 'lldp', label: 'LLDP Neighbors', count: neighbors.length },
    { key: 'routing', label: 'Routing Table', count: routes.length },
    { key: 'vlans', label: 'VLANs', count: vlans.length },
  ]

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>Topology</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            TOPOLOGY & NETWORK
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · LLDP · Routing · VLANs · auto-refresh 2m
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="glass-bright px-3 py-1.5 rounded font-mono text-xs transition-all hover:bg-cyan-400/10 flex items-center gap-1.5"
          style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
          REFRESH
        </button>
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded"
          style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading topology data...</span>
        </div>
      )}

      {!loading && (
        <>
          {/* Tab Switcher */}
          <div className="flex flex-wrap gap-2">
            {tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className="font-mono text-xs px-4 py-2 rounded transition-all flex items-center gap-2"
                style={{
                  background: tab === t.key ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: tab === t.key ? '#00d4ff' : '#8899bb',
                  border: `1px solid ${tab === t.key ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                }}
              >
                {t.label}
                <span
                  className="font-mono text-[9px] px-1.5 py-0.5 rounded-full"
                  style={{
                    background: tab === t.key ? 'rgba(0,212,255,0.2)' : 'rgba(136,153,187,0.15)',
                    color: tab === t.key ? '#00d4ff' : '#8899bb',
                  }}
                >
                  {t.count}
                </span>
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {tab === 'lldp' && <LLDPTable neighbors={neighbors} deviceId={id} />}
          {tab === 'routing' && <RoutingTable routes={routes} />}
          {tab === 'vlans' && <VLANTable vlans={vlans} />}
        </>
      )}
    </div>
  )
}
