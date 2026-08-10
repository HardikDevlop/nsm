import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import SNMPHealthIndicator from '../components/SNMPHealthIndicator'
import { getSNMPMemoryStats, getSNMPSystemInfo, type SNMPMemoryStats, type SNMPSystemInfo } from '../lib/api'

type TimeRange = '1h' | '24h' | '7d' | '30d'

const TIME_RANGE_HOURS: Record<TimeRange, number> = {
  '1h': 1,
  '24h': 24,
  '7d': 168,
  '30d': 720,
}

function memHealth(pct: number | undefined): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (pct === undefined || pct === null) return 'unknown'
  if (pct >= 90) return 'critical'
  if (pct >= 75) return 'warning'
  return 'healthy'
}

function fmtBytes(bytes: number | undefined): string {
  if (bytes === undefined || bytes === null) return '—'
  const abs = Math.abs(bytes)
  if (abs >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(2)} GB`
  if (abs >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (abs >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function fmtPct(val: number | undefined): string {
  if (val === undefined || val === null) return '—'
  return `${val.toFixed(1)}%`
}

export default function SNMPMemoryMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [timeRange, setTimeRange] = useState<TimeRange>('24h')
  const [stats, setStats] = useState<SNMPMemoryStats | null>(null)
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [memData, sysData] = await Promise.all([
        getSNMPMemoryStats(id, TIME_RANGE_HOURS[timeRange]),
        getSNMPSystemInfo(id),
      ])
      setStats(memData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memory data')
    } finally {
      setLoading(false)
    }
  }, [id, timeRange])

  useEffect(() => { void load() }, [load])

  useEffect(() => { void load() }, [load])

  // Web auto-ping every 15 seconds — matches the backend PING_INTERVAL
  useEffect(() => {
    const t = setInterval(() => void load(), 15_000)
    return () => clearInterval(t)
  }, [load])

  const health = memHealth(stats?.utilization_percent)

  const chartData = (stats?.history ?? []).map(p => ({
    timestamp: p.timestamp,
    value: p.utilization,
    value2: p.used,
  }))

  // Usage bar segments
  const segments: Array<{ label: string; bytes: number | undefined; color: string }> = [
    { label: 'Used', bytes: stats?.used_bytes, color: '#00d4ff' },
    { label: 'Cached', bytes: stats?.cached_bytes, color: '#7c3aed' },
    { label: 'Buffers', bytes: stats?.buffer_bytes, color: '#ffaa00' },
    { label: 'Free', bytes: stats?.free_bytes, color: '#00ff88' },
  ]
  const total = stats?.total_bytes || 1
  const swapPct = stats?.swap_total
    ? ((stats.swap_used ?? 0) / stats.swap_total) * 100
    : undefined

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">SNMP</button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>Memory</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">MEMORY MONITORING</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · auto-refresh 15s
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
            {(['1h', '24h', '7d', '30d'] as TimeRange[]).map(range => (
              <button key={range} onClick={() => setTimeRange(range)}
                className="font-mono text-xs px-3 py-1.5 transition-all"
                style={{
                  background: timeRange === range ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: timeRange === range ? '#00d4ff' : '#8899bb',
                  borderRight: range !== '30d' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                }}>
                {range}
              </button>
            ))}
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
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading memory data...</span>
        </div>
      )}

      {/* Not Supported */}
      {!loading && stats && !stats.supported && (
        <GlassCard className="p-8 text-center space-y-3">
          <div className="font-display font-bold text-lg" style={{ color: '#8899bb' }}>
            Memory Monitoring Not Supported
          </div>
          <div className="font-mono text-sm" style={{ color: '#667799' }}>
            This device does not expose memory information through SNMP.
          </div>
          <button onClick={() => navigate(`/snmp/dashboard/${id}`)}
            className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Back to Dashboard
          </button>
        </GlassCard>
      )}

      {!loading && stats?.supported && (
        <>
          {/* Stat Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { label: 'Total', value: fmtBytes(stats.total_bytes), color: '#8899bb' },
              { label: 'Used', value: fmtBytes(stats.used_bytes), color: '#00d4ff' },
              { label: 'Free', value: fmtBytes(stats.free_bytes), color: '#00ff88' },
              { label: 'Cached', value: fmtBytes(stats.cached_bytes), color: '#7c3aed' },
              { label: 'Buffers', value: fmtBytes(stats.buffer_bytes), color: '#ffaa00' },
              { label: 'Utilization', value: fmtPct(stats.utilization_percent), color: memHealth(stats.utilization_percent) === 'critical' ? '#ff3366' : memHealth(stats.utilization_percent) === 'warning' ? '#ffaa00' : '#00ff88' },
            ].map(tile => (
              <GlassCard key={tile.label} className="p-4 text-center">
                <div className="font-display font-bold text-lg sm:text-xl" style={{ color: tile.color }}>
                  {tile.value}
                </div>
                <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{tile.label}</div>
              </GlassCard>
            ))}
          </div>

          {/* Health Row */}
          <div className="flex flex-wrap items-center gap-4">
            <SNMPHealthIndicator health={health} showLabel size="md" />
            <SNMPStatusBadge status="supported" />
            {stats.last_poll && (
              <span className="font-mono text-xs" style={{ color: '#667799' }}>
                Last Poll: {new Date(stats.last_poll).toLocaleString()}
              </span>
            )}
          </div>

          {/* Usage Bar */}
          <GlassCard className="p-4">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">MEMORY BREAKDOWN</div>
            <div className="h-8 rounded-lg overflow-hidden flex mb-3" style={{ background: 'rgba(0,0,0,0.3)' }}>
              {segments.filter(s => s.bytes && s.bytes > 0).map(seg => (
                <div
                  key={seg.label}
                  style={{
                    width: `${((seg.bytes || 0) / total) * 100}%`,
                    background: seg.color,
                    opacity: 0.85,
                    transition: 'width 0.5s ease',
                  }}
                  title={`${seg.label}: ${fmtBytes(seg.bytes)}`}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-4">
              {segments.filter(s => s.bytes !== undefined).map(seg => (
                <div key={seg.label} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ background: seg.color }} />
                  <span className="font-mono text-xs" style={{ color: '#8899bb' }}>
                    {seg.label}: <span style={{ color: '#c8d8ee' }}>{fmtBytes(seg.bytes)}</span>
                  </span>
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Utilization Chart */}
          <GlassCard className="p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">UTILIZATION OVER TIME</div>
                <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
                  {timeRange} · {chartData.length} samples
                </div>
              </div>
              <div className="font-mono text-xs px-2 py-1 rounded"
                style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
                {fmtPct(stats.utilization_percent)}
              </div>
            </div>
            <SNMPMetricChart
              data={chartData}
              height={200}
              color="#00d4ff"
              unit="%"
              label="Utilization"
              showArea
              showGrid
              showAxes
              noDataMessage="No Historical Data Yet"
            />
          </GlassCard>

          {/* Swap */}
          {stats.swap_total !== undefined && (
            <GlassCard className="p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">SWAP USAGE</div>
              <div className="flex flex-wrap gap-6">
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Swap Total</div>
                  <div className="font-mono text-lg font-bold" style={{ color: '#8899bb' }}>
                    {fmtBytes(stats.swap_total)}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Swap Used</div>
                  <div className="font-mono text-lg font-bold" style={{ color: '#ffaa00' }}>
                    {fmtBytes(stats.swap_used)}
                  </div>
                </div>
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Swap Utilization</div>
                  <div className="font-mono text-lg font-bold" style={{ color: swapPct && swapPct > 80 ? '#ff3366' : '#00ff88' }}>
                    {fmtPct(swapPct)}
                  </div>
                </div>
              </div>
              {swapPct !== undefined && (
                <div className="mt-3 h-3 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(swapPct, 100)}%`,
                      background: swapPct > 80 ? '#ff3366' : '#ffaa00',
                    }}
                  />
                </div>
              )}
            </GlassCard>
          )}

          {/* History Table */}
          {chartData.length > 0 && (
            <GlassCard className="overflow-hidden">
              <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">POLL HISTORY</div>
              </div>
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                      {['Timestamp', 'Utilization', 'Used', 'Free', 'Health'].map(h => (
                        <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                          style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...stats.history].reverse().map((row, i) => {
                      const h = memHealth(row.utilization)
                      const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                          <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>
                            {new Date(row.timestamp).toLocaleString()}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#00d4ff' }}>
                            {row.utilization.toFixed(1)}%
                          </td>
                          <td className="px-4 py-2 font-mono text-xs" style={{ color: '#c8d8ee' }}>
                            {fmtBytes(row.used)}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs" style={{ color: '#c8d8ee' }}>
                            {fmtBytes(row.free)}
                          </td>
                          <td className="px-4 py-2">
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded uppercase"
                              style={{ color: hColors[h], background: `${hColors[h]}15` }}>
                              {h}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}
        </>
      )}
    </div>
  )
}
