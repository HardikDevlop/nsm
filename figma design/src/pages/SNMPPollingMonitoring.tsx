import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import {
  getSNMPPollingHistory,
  getSNMPPollingStatistics,
  getSNMPSystemInfo,
  type SNMPPollingHistory,
  type SNMPPollingStatistics,
  type SNMPSystemInfo,
} from '../lib/api'

type TimeRange = '1h' | '6h' | '24h' | '7d'
const TIME_RANGE_HOURS: Record<TimeRange, number> = { '1h': 1, '6h': 6, '24h': 24, '7d': 168 }

function fmtDuration(ms: number | undefined): string {
  if (ms === undefined || ms === null) return '—'
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export default function SNMPPollingMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [timeRange, setTimeRange] = useState<TimeRange>('24h')
  const [stats, setStats] = useState<SNMPPollingStatistics | null>(null)
  const [history, setHistory] = useState<SNMPPollingHistory[]>([])
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [collectorFilter, setCollectorFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'failure'>('all')

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [statsData, historyData, sysData] = await Promise.all([
        getSNMPPollingStatistics(id),
        getSNMPPollingHistory(id, TIME_RANGE_HOURS[timeRange]),
        getSNMPSystemInfo(id),
      ])
      setStats(statsData)
      setHistory(historyData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load polling data')
    } finally {
      setLoading(false)
    }
  }, [id, timeRange])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    // Web auto-ping every 15 seconds — matches the backend PING_INTERVAL
    const t = setInterval(() => void load(), 15_000)
    return () => clearInterval(t)
  }, [load])

  // Available collectors from stats
  const collectors = stats?.by_collector.map(c => c.collector) ?? []

  // Filter history
  const filtered = history.filter(h => {
    const matchCollector = collectorFilter === 'all' || h.collector === collectorFilter
    const matchStatus = statusFilter === 'all' || h.status === statusFilter
    return matchCollector && matchStatus
  })

  const successRate = stats ? stats.success_rate : 0
  const successColor = successRate >= 95 ? '#00ff88' : successRate >= 80 ? '#ffaa00' : '#ff3366'

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>Polling</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            POLLING MONITORING
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · auto-refresh 15s
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Time Range */}
          <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
            {(['1h', '6h', '24h', '7d'] as TimeRange[]).map(r => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className="font-mono text-xs px-3 py-1.5 transition-all"
                style={{
                  background: timeRange === r ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: timeRange === r ? '#00d4ff' : '#8899bb',
                  borderRight: r !== '7d' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                }}
              >
                {r}
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
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading polling data...</span>
        </div>
      )}

      {!loading && stats && (
        <>
          {/* Summary Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: '#00d4ff' }}>
                {stats.total_polls}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Total Polls</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: '#00ff88' }}>
                {stats.success_count}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Success</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: stats.failure_count > 0 ? '#ff3366' : '#8899bb' }}>
                {stats.failure_count}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Failures</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: successColor }}>
                {stats.success_rate.toFixed(1)}%
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Success Rate</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: '#7c3aed' }}>
                {fmtDuration(stats.average_duration_ms)}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Avg Duration</div>
            </GlassCard>
          </div>

          {/* Success Rate Bar */}
          <GlassCard className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">POLLING SUCCESS RATE</div>
              <span className="font-mono text-xs font-bold" style={{ color: successColor }}>
                {stats.success_rate.toFixed(1)}%
              </span>
            </div>
            <div className="h-3 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(stats.success_rate, 100)}%`,
                  background: `linear-gradient(90deg, ${successColor}99, ${successColor})`,
                }}
              />
            </div>
            <div className="flex justify-between mt-2 font-mono text-[10px]" style={{ color: '#667799' }}>
              <span>0%</span>
              <span>{stats.success_count} / {stats.total_polls} successful</span>
              <span>100%</span>
            </div>
          </GlassCard>

          {/* Performance Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { l: 'Minimum', v: fmtDuration(stats.min_duration_ms), c: '#00ff88' },
              { l: 'Average', v: fmtDuration(stats.average_duration_ms), c: '#00d4ff' },
              { l: 'Maximum', v: fmtDuration(stats.max_duration_ms), c: '#ff6644' },
            ].map(s => (
              <GlassCard key={s.l} className="p-4">
                <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>{s.l} Duration</div>
                <div className="font-display font-bold text-2xl" style={{ color: s.c }}>{s.v}</div>
              </GlassCard>
            ))}
          </div>

          {/* Per-Collector Stats */}
          {stats.by_collector.length > 0 && (
            <GlassCard className="p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">
                PER-COLLECTOR STATISTICS
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {stats.by_collector.map(c => {
                  const rate = c.success_rate
                  const rateColor = rate >= 95 ? '#00ff88' : rate >= 80 ? '#ffaa00' : '#ff3366'
                  return (
                    <div
                      key={c.collector}
                      className="p-3 rounded"
                      style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(0,212,255,0.08)' }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-xs font-semibold uppercase" style={{ color: '#c8d8ee' }}>
                          {c.collector}
                        </span>
                        <span className="font-mono text-[10px] font-bold" style={{ color: rateColor }}>
                          {rate.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full overflow-hidden mb-2" style={{ background: 'rgba(0,0,0,0.3)' }}>
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${Math.min(rate, 100)}%`, background: rateColor }}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <div className="font-mono text-[9px]" style={{ color: '#556677' }}>Polls</div>
                          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>{c.polls}</div>
                        </div>
                        <div>
                          <div className="font-mono text-[9px]" style={{ color: '#556677' }}>Avg</div>
                          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                            {fmtDuration(c.avg_duration_ms)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </GlassCard>
          )}

          {/* Filters */}
          {history.length > 0 && (
            <div className="flex flex-wrap items-center gap-3">
              {/* Collector Filter */}
              {collectors.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  <button
                    onClick={() => setCollectorFilter('all')}
                    className="font-mono text-xs px-2.5 py-1 rounded transition-all"
                    style={{
                      background: collectorFilter === 'all' ? 'rgba(0,212,255,0.15)' : 'transparent',
                      color: collectorFilter === 'all' ? '#00d4ff' : '#8899bb',
                      border: `1px solid ${collectorFilter === 'all' ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                    }}
                  >
                    All
                  </button>
                  {collectors.map(col => (
                    <button
                      key={col}
                      onClick={() => setCollectorFilter(col)}
                      className="font-mono text-xs px-2.5 py-1 rounded transition-all uppercase"
                      style={{
                        background: collectorFilter === col ? 'rgba(0,212,255,0.15)' : 'transparent',
                        color: collectorFilter === col ? '#00d4ff' : '#8899bb',
                        border: `1px solid ${collectorFilter === col ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                      }}
                    >
                      {col}
                    </button>
                  ))}
                </div>
              )}

              {/* Status Filter */}
              <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
                {(['all', 'success', 'failure'] as const).map(s => (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s)}
                    className="font-mono text-xs px-3 py-1 transition-all capitalize"
                    style={{
                      background: statusFilter === s ? 'rgba(0,212,255,0.15)' : 'transparent',
                      color: statusFilter === s ? '#00d4ff' : '#8899bb',
                      borderRight: s !== 'failure' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>

              <span className="font-mono text-xs" style={{ color: '#667799' }}>{filtered.length} shown</span>
            </div>
          )}

          {/* History Table */}
          {history.length > 0 && (
            <GlassCard className="overflow-hidden">
              <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">
                  POLLING HISTORY ({timeRange})
                </div>
              </div>
              <div className="max-h-[500px] overflow-y-auto overflow-x-auto">
                <table className="w-full" style={{ minWidth: 600 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                      {['Timestamp', 'Collector', 'Status', 'Duration', 'Objects', 'Error'].map(h => (
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
                    {filtered.map(poll => (
                      <tr key={poll.id} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#8899bb' }}>
                          {new Date(poll.timestamp).toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs uppercase" style={{ color: '#00d4ff' }}>
                          {poll.collector}
                        </td>
                        <td className="px-4 py-2.5">
                          <SNMPStatusBadge status={poll.status === 'success' ? 'ok' : 'error'} size="xs" />
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#c8d8ee' }}>
                          {fmtDuration(poll.duration_ms)}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#8899bb' }}>
                          {poll.objects_collected ?? '—'}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs max-w-xs truncate" style={{ color: '#ff6644' }}>
                          {poll.error || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}

          {history.length === 0 && (
            <div className="font-mono text-xs text-center py-8" style={{ color: '#8899bb' }}>
              No polling history available for selected time range.
            </div>
          )}
        </>
      )}
    </div>
  )
}
