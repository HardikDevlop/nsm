import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import {
  getSNMPInterfaces,
  getSNMPInterfaceHistory,
  getSNMPSystemInfo,
  type SNMPInterfaceStats,
  type SNMPInterfaceHistory,
  type SNMPSystemInfo,
} from '../lib/api'

type TimeRange = '1h' | '24h' | '7d' | '30d'
const TIME_RANGE_HOURS: Record<TimeRange, number> = { '1h': 1, '24h': 24, '7d': 168, '30d': 720 }

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtSpeed(bps: number | undefined): string {
  if (bps === undefined || bps === null) return '—'
  if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(0)} Gbps`
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(0)} Mbps`
  if (bps > 0) return `${bps.toLocaleString()} bps`
  return '—'
}

function fmtMbps(mbps: number | undefined): string {
  if (mbps === undefined || mbps === null) return '—'
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  return `${mbps.toFixed(2)} Mbps`
}

function fmtNum(n: number | undefined): string {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString()
}

function statusColor(s: 'UP' | 'DOWN' | 'UNKNOWN'): string {
  return s === 'UP' ? '#00ff88' : s === 'DOWN' ? '#ff3366' : '#8899bb'
}

function utilizationColor(pct: number | undefined): string {
  if (!pct) return '#8899bb'
  if (pct >= 90) return '#ff3366'
  if (pct >= 70) return '#ffaa00'
  return '#00d4ff'
}

// ── Interface Detail Panel ────────────────────────────────────────────────────

function InterfaceDetail({
  iface,
  deviceId,
  onClose,
}: {
  iface: SNMPInterfaceStats
  deviceId: number
  onClose: () => void
}) {
  const [timeRange, setTimeRange] = useState<TimeRange>('24h')
  const [history, setHistory] = useState<SNMPInterfaceHistory | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getSNMPInterfaceHistory(iface.id, TIME_RANGE_HOURS[timeRange])
      setHistory(data)
    } catch { /* history may not exist yet */ }
    finally { setLoading(false) }
  }, [iface.id, timeRange])

  useEffect(() => { void load() }, [load])

  const chartData = (history?.history ?? []).map(p => ({
    timestamp: p.timestamp,
    value: p.rx_mbps,
    value2: p.tx_mbps,
  }))

  const utilizPct = iface.utilization_percent
  const statusC = statusColor(iface.status)

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl space-y-4"
        style={{ background: 'rgba(8,25,55,0.98)', border: '1px solid rgba(0,212,255,0.2)' }}>

        {/* Header */}
        <div className="flex items-start justify-between p-5" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="font-display font-bold text-lg neon-cyan">{iface.name}</h2>
              <span className="font-mono text-xs px-2 py-0.5 rounded-full font-bold"
                style={{ color: statusC, background: `${statusC}18`, border: `1px solid ${statusC}40` }}>
                {iface.status}
              </span>
            </div>
            <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
              Index: {iface.if_index} · Speed: {fmtSpeed(iface.speed_bps)} · MTU: {iface.mtu ?? '—'}
            </div>
            {iface.mac_address && (
              <div className="font-mono text-xs mt-0.5" style={{ color: '#667799' }}>MAC: {iface.mac_address}</div>
            )}
          </div>
          <button onClick={onClose}
            className="p-2 rounded-lg transition-all hover:bg-white/5"
            style={{ color: '#8899bb' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-5 pb-5 space-y-4">
          {/* Live Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { l: 'RX', v: fmtMbps(iface.rx_mbps), c: '#00d4ff' },
              { l: 'TX', v: fmtMbps(iface.tx_mbps), c: '#00ff88' },
              { l: 'Errors', v: fmtNum(iface.errors), c: iface.errors ? '#ff6644' : '#00ff88' },
              { l: 'Discards', v: fmtNum(iface.discards), c: iface.discards ? '#ffaa00' : '#00ff88' },
            ].map(s => (
              <GlassCard key={s.l} className="p-3 text-center">
                <div className="font-display font-bold text-lg" style={{ color: s.c }}>{s.v}</div>
                <div className="font-mono text-[10px] mt-0.5" style={{ color: '#8899bb' }}>{s.l}</div>
              </GlassCard>
            ))}
          </div>

          {/* Utilization Bar */}
          {utilizPct !== undefined && (
            <div>
              <div className="flex justify-between mb-1">
                <span className="font-mono text-xs" style={{ color: '#8899bb' }}>Bandwidth Utilization</span>
                <span className="font-mono text-xs font-bold" style={{ color: utilizationColor(utilizPct) }}>
                  {utilizPct.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
                <div className="h-full rounded-full transition-all"
                  style={{ width: `${Math.min(utilizPct, 100)}%`, background: utilizationColor(utilizPct) }} />
              </div>
            </div>
          )}

          {/* Time Range + Chart */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="font-display font-bold text-sm neon-cyan">TRAFFIC HISTORY</div>
              <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
                {(['1h', '24h', '7d', '30d'] as TimeRange[]).map(r => (
                  <button key={r} onClick={() => setTimeRange(r)}
                    className="font-mono text-[10px] px-2.5 py-1 transition-all"
                    style={{
                      background: timeRange === r ? 'rgba(0,212,255,0.15)' : 'transparent',
                      color: timeRange === r ? '#00d4ff' : '#8899bb',
                      borderRight: r !== '30d' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                    }}>{r}</button>
                ))}
              </div>
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <span className="font-mono text-xs" style={{ color: '#00d4ff' }}>Loading history...</span>
              </div>
            ) : (
              <SNMPMetricChart
                data={chartData}
                height={160}
                color="#00d4ff"
                color2="#00ff88"
                label="RX"
                label2="TX"
                unit=" Mbps"
                showArea
                showGrid
                showAxes
                noDataMessage="No Historical Data Yet"
              />
            )}
          </div>

          {/* Statistics */}
          {history?.statistics && (
            <div className="grid grid-cols-3 gap-3">
              {[
                { l: 'Peak', v: fmtMbps(history.statistics.peak_mbps), c: '#ff6644' },
                { l: 'Average', v: fmtMbps(history.statistics.average_mbps), c: '#00d4ff' },
                { l: '95th %ile', v: fmtMbps(history.statistics.percentile_95_mbps), c: '#ffaa00' },
              ].map(s => (
                <GlassCard key={s.l} className="p-3 text-center">
                  <div className="font-mono font-bold text-base" style={{ color: s.c }}>{s.v}</div>
                  <div className="font-mono text-[10px] mt-0.5" style={{ color: '#8899bb' }}>{s.l}</div>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Interface Card ────────────────────────────────────────────────────────────

function InterfaceCard({
  iface,
  onClick,
}: {
  iface: SNMPInterfaceStats
  onClick: () => void
}) {
  const statusC = statusColor(iface.status)
  const utilizPct = iface.utilization_percent
  const ucColor = utilizationColor(utilizPct)

  return (
    <GlassCard
      className="p-4 cursor-pointer transition-all hover:bg-cyan-400/5"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
    >
      {/* Name + Status */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <div className="font-mono text-sm font-bold truncate" style={{ color: '#c8d8ee' }}>
            {iface.name}
          </div>
          {iface.description && iface.description !== iface.name && (
            <div className="font-mono text-[10px] truncate mt-0.5" style={{ color: '#667799' }}>
              {iface.description}
            </div>
          )}
        </div>
        <span className="font-mono text-[10px] px-2 py-0.5 rounded font-bold shrink-0"
          style={{ color: statusC, background: `${statusC}18`, border: `1px solid ${statusC}40` }}>
          {iface.status}
        </span>
      </div>

      {/* Speed + MAC */}
      <div className="flex items-center gap-3 mb-3">
        <span className="font-mono text-[10px]" style={{ color: '#667799' }}>
          {fmtSpeed(iface.speed_bps)}
        </span>
        {iface.mac_address && (
          <span className="font-mono text-[10px] truncate" style={{ color: '#556677' }}>
            {iface.mac_address}
          </span>
        )}
      </div>

      {/* Traffic */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <div className="font-mono text-[9px] mb-0.5" style={{ color: '#556677' }}>RX</div>
          <div className="font-mono text-xs font-semibold" style={{ color: '#00d4ff' }}>
            {fmtMbps(iface.rx_mbps)}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] mb-0.5" style={{ color: '#556677' }}>TX</div>
          <div className="font-mono text-xs font-semibold" style={{ color: '#00ff88' }}>
            {fmtMbps(iface.tx_mbps)}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] mb-0.5" style={{ color: '#556677' }}>Errors</div>
          <div className="font-mono text-xs font-semibold"
            style={{ color: (iface.errors ?? 0) > 0 ? '#ff6644' : '#8899bb' }}>
            {fmtNum(iface.errors)}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] mb-0.5" style={{ color: '#556677' }}>Discards</div>
          <div className="font-mono text-xs font-semibold"
            style={{ color: (iface.discards ?? 0) > 0 ? '#ffaa00' : '#8899bb' }}>
            {fmtNum(iface.discards)}
          </div>
        </div>
      </div>

      {/* Utilization Bar */}
      {utilizPct !== undefined && (
        <div>
          <div className="flex justify-between mb-1">
            <span className="font-mono text-[9px]" style={{ color: '#556677' }}>Utilization</span>
            <span className="font-mono text-[9px]" style={{ color: ucColor }}>{utilizPct.toFixed(1)}%</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
            <div className="h-full rounded-full"
              style={{ width: `${Math.min(utilizPct, 100)}%`, background: ucColor }} />
          </div>
        </div>
      )}

      {/* View Link */}
      <div className="flex justify-end mt-3 pt-2" style={{ borderTop: '1px solid rgba(0,212,255,0.06)' }}>
        <span className="font-mono text-[10px] flex items-center gap-1" style={{ color: '#00d4ff' }}>
          View Details
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </GlassCard>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SNMPInterfaceMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [interfaces, setInterfaces] = useState<SNMPInterfaceStats[]>([])
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [selected, setSelected] = useState<SNMPInterfaceStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'UP' | 'DOWN'>('all')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [ifData, sysData] = await Promise.all([
        getSNMPInterfaces(id),
        getSNMPSystemInfo(id),
      ])
      setInterfaces(ifData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load interfaces')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    // Web auto-ping every 15 seconds — matches the backend PING_INTERVAL
    const t = setInterval(() => void load(), 15_000)
    return () => clearInterval(t)
  }, [load])

  const filtered = interfaces.filter(iface => {
    const matchesFilter = filter === 'all' || iface.status === filter
    const searchTerm = search.trim().toLowerCase()
    const matchesSearch = !searchTerm ||
      iface.name.toLowerCase().includes(searchTerm) ||
      (iface.description ?? '').toLowerCase().includes(searchTerm) ||
      (iface.mac_address ?? '').toLowerCase().includes(searchTerm)
    return matchesFilter && matchesSearch
  })

  const upCount = interfaces.filter(i => i.status === 'UP').length
  const downCount = interfaces.filter(i => i.status === 'DOWN').length
  const totalTraffic = interfaces.reduce((acc, i) => acc + (i.rx_mbps ?? 0) + (i.tx_mbps ?? 0), 0)
  const totalErrors = interfaces.reduce((acc, i) => acc + (i.errors ?? 0), 0)

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>Interfaces</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            INTERFACE MONITORING
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · {interfaces.length} interfaces · auto-refresh 15s
          </p>
        </div>
        <button onClick={() => void load()}
          className="glass-bright px-3 py-1.5 rounded font-mono text-xs transition-all hover:bg-cyan-400/10 flex items-center gap-1.5"
          style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
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

      {/* Summary Tiles */}
      {!loading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { l: 'Total', v: interfaces.length, c: '#00d4ff' },
            { l: 'UP', v: upCount, c: '#00ff88' },
            { l: 'DOWN', v: downCount, c: downCount > 0 ? '#ff3366' : '#8899bb' },
            { l: 'Errors', v: totalErrors, c: totalErrors > 0 ? '#ff6644' : '#8899bb' },
          ].map(t => (
            <GlassCard key={t.l} className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: t.c }}>{t.v}</div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{t.l}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Filters + Search */}
      {!loading && interfaces.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
            {(['all', 'UP', 'DOWN'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className="font-mono text-xs px-3 py-1.5 transition-all"
                style={{
                  background: filter === f ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: filter === f ? '#00d4ff' : '#8899bb',
                  borderRight: f !== 'DOWN' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                }}>
                {f.toUpperCase()}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Search interfaces..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 min-w-[180px] px-3 py-1.5 rounded font-mono text-xs"
            style={{
              background: 'rgba(8,25,55,0.6)',
              border: '1px solid rgba(0,212,255,0.2)',
              color: '#c8d8ee',
              outline: 'none',
            }}
          />
          <span className="font-mono text-xs" style={{ color: '#8899bb' }}>
            {filtered.length} shown
          </span>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading interfaces...</span>
        </div>
      )}

      {!loading && interfaces.length === 0 && (
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-lg mb-2" style={{ color: '#8899bb' }}>
            No Interfaces Found
          </div>
          <div className="font-mono text-sm" style={{ color: '#667799' }}>
            No Data Available From Device
          </div>
        </GlassCard>
      )}

      {!loading && filtered.length === 0 && interfaces.length > 0 && (
        <div className="font-mono text-xs text-center py-8" style={{ color: '#8899bb' }}>
          No interfaces match your filter.
        </div>
      )}

      {/* Interface Cards Grid */}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(iface => (
            <InterfaceCard
              key={iface.id}
              iface={iface}
              onClick={() => setSelected(iface)}
            />
          ))}
        </div>
      )}

      {/* Traffic Summary */}
      {!loading && interfaces.length > 0 && (
        <GlassCard className="p-4">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">AGGREGATE TRAFFIC</div>
          <div className="flex flex-wrap gap-6">
            <div>
              <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Total Throughput</div>
              <div className="font-mono text-lg font-bold" style={{ color: '#00d4ff' }}>
                {fmtMbps(totalTraffic)}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Total Errors</div>
              <div className="font-mono text-lg font-bold" style={{ color: totalErrors > 0 ? '#ff6644' : '#8899bb' }}>
                {totalErrors.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Active Interfaces</div>
              <div className="font-mono text-lg font-bold" style={{ color: '#00ff88' }}>
                {upCount} / {interfaces.length}
              </div>
            </div>
          </div>
        </GlassCard>
      )}

      {/* Interface Detail Modal */}
      {selected && (
        <InterfaceDetail
          iface={selected}
          deviceId={id}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
