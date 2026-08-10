import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import SNMPHealthIndicator from '../components/SNMPHealthIndicator'
import { getSNMPCPUStats, getSNMPSystemInfo, type SNMPCPUStats, type SNMPSystemInfo } from '../lib/api'

type TimeRange = '1h' | '24h' | '7d' | '30d'

const TIME_RANGE_HOURS: Record<TimeRange, number> = {
  '1h': 1,
  '24h': 24,
  '7d': 168,
  '30d': 720,
}

function cpuHealth(usage: number | undefined): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (usage === undefined || usage === null) return 'unknown'
  if (usage >= 90) return 'critical'
  if (usage >= 70) return 'warning'
  return 'healthy'
}

function fmt(val: number | undefined, suffix = '%'): string {
  if (val === undefined || val === null) return '—'
  return `${val.toFixed(1)}${suffix}`
}

export default function SNMPCPUMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [timeRange, setTimeRange] = useState<TimeRange>('24h')
  const [stats, setStats] = useState<SNMPCPUStats | null>(null)
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [cpuData, sysData] = await Promise.all([
        getSNMPCPUStats(id, TIME_RANGE_HOURS[timeRange]),
        getSNMPSystemInfo(id),
      ])
      setStats(cpuData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load CPU data')
    } finally {
      setLoading(false)
    }
  }, [id, timeRange])

  useEffect(() => { void load() }, [load])

  // Web auto-ping every 15 seconds — matches the backend PING_INTERVAL
  useEffect(() => {
    const t = setInterval(() => void load(), 15_000)
    return () => clearInterval(t)
  }, [load])

  const health = cpuHealth(stats?.current_usage)

  const chartData = (stats?.history ?? []).map(p => ({
    timestamp: p.timestamp,
    value: p.usage,
  }))

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>CPU</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            CPU MONITORING
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · auto-refresh 15s
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Time Range Selector */}
          <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
            {(['1h', '24h', '7d', '30d'] as TimeRange[]).map(range => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className="font-mono text-xs px-3 py-1.5 transition-all"
                style={{
                  background: timeRange === range ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: timeRange === range ? '#00d4ff' : '#8899bb',
                  borderRight: range !== '30d' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                }}
              >
                {range}
              </button>
            ))}
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
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading CPU data...</span>
        </div>
      )}

      {/* Not Supported State */}
      {!loading && stats && !stats.supported && (
        <GlassCard className="p-8 text-center space-y-3">
          <div className="font-display font-bold text-lg" style={{ color: '#8899bb' }}>
            CPU Monitoring Not Supported
          </div>
          <div className="font-mono text-sm" style={{ color: '#667799' }}>
            This device does not expose CPU information through SNMP.
          </div>
          {sysInfo && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4 max-w-sm mx-auto text-left">
              {[
                { l: 'Hostname', v: sysInfo.hostname },
                { l: 'Location', v: sysInfo.location },
                { l: 'Contact', v: sysInfo.contact },
              ].filter(i => i.v).map(item => (
                <div key={item.l}>
                  <div className="font-mono text-[10px]" style={{ color: '#556677' }}>{item.l}</div>
                  <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{item.v}</div>
                </div>
              ))}
            </div>
          )}
          <button
            onClick={() => navigate(`/snmp/dashboard/${id}`)}
            className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}
          >
            Back to Dashboard
          </button>
        </GlassCard>
      )}

      {/* Main CPU Content */}
      {!loading && stats?.supported && (
        <>
          {/* Stat Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {[
              { label: 'Current', value: fmt(stats.current_usage), color: stats.current_usage !== undefined && stats.current_usage >= 90 ? '#ff3366' : stats.current_usage !== undefined && stats.current_usage >= 70 ? '#ffaa00' : '#00ff88' },
              { label: 'Average', value: fmt(stats.average), color: '#00d4ff' },
              { label: 'Maximum', value: fmt(stats.maximum), color: '#ff6644' },
              { label: 'Minimum', value: fmt(stats.minimum), color: '#7c3aed' },
              { label: '95th %ile', value: fmt(stats.percentile_95), color: '#ffaa00' },
            ].map(tile => (
              <GlassCard key={tile.label} className="p-4 text-center">
                <div className="font-display font-bold text-xl sm:text-2xl" style={{ color: tile.color }}>
                  {tile.value}
                </div>
                <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{tile.label}</div>
              </GlassCard>
            ))}
          </div>

          {/* Health + Poll Info */}
          <div className="flex flex-wrap items-center gap-4">
            <SNMPHealthIndicator health={health} showLabel size="md" />
            <SNMPStatusBadge status="supported" />
            {stats.last_poll && (
              <span className="font-mono text-xs" style={{ color: '#667799' }}>
                Last Poll: {new Date(stats.last_poll).toLocaleString()}
              </span>
            )}
            {stats.poll_interval && (
              <span className="font-mono text-xs" style={{ color: '#667799' }}>
                Interval: {stats.poll_interval}s
              </span>
            )}
          </div>

          {/* Main Chart */}
          <GlassCard className="p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">CPU UTILIZATION</div>
                <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
                  {timeRange} history · {chartData.length} data points
                </div>
              </div>
              <div className="font-mono text-xs px-2 py-1 rounded" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
                {fmt(stats.current_usage)}
              </div>
            </div>
            <SNMPMetricChart
              data={chartData}
              height={200}
              color="#00d4ff"
              unit="%"
              label="CPU %"
              showArea
              showGrid
              showAxes
              noDataMessage="No Historical Data Yet"
            />
          </GlassCard>

          {/* Per Core */}
          {stats.per_core && stats.per_core.length > 0 && (
            <GlassCard className="p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">PER CORE USAGE</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
                {stats.per_core.map(core => {
                  const pct = core.usage
                  const coreColor = pct >= 90 ? '#ff3366' : pct >= 70 ? '#ffaa00' : '#00ff88'
                  return (
                    <div key={core.core} className="text-center">
                      {/* Circular gauge using SVG */}
                      <svg width="56" height="56" viewBox="0 0 56 56" className="mx-auto">
                        <circle cx="28" cy="28" r="22" fill="none" stroke="rgba(0,212,255,0.1)" strokeWidth="4" />
                        <circle
                          cx="28" cy="28" r="22"
                          fill="none"
                          stroke={coreColor}
                          strokeWidth="4"
                          strokeDasharray={`${(pct / 100) * 138.2} 138.2`}
                          strokeLinecap="round"
                          transform="rotate(-90 28 28)"
                          style={{ transition: 'stroke-dasharray 0.5s ease' }}
                        />
                        <text x="28" y="33" textAnchor="middle" fontSize="11" fontFamily="monospace" fill={coreColor}>
                          {pct.toFixed(0)}%
                        </text>
                      </svg>
                      <div className="font-mono text-[10px] mt-1" style={{ color: '#8899bb' }}>
                        Core {core.core}
                      </div>
                    </div>
                  )
                })}
              </div>
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
                      {['Timestamp', 'CPU Usage', 'Health'].map(h => (
                        <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                          style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...chartData].reverse().map((row, i) => {
                      const h = cpuHealth(row.value)
                      const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                          <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>
                            {new Date(row.timestamp).toLocaleString()}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#00d4ff' }}>
                            {row.value.toFixed(1)}%
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
