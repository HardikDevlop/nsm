import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../../../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import SNMPHealthIndicator from '../components/SNMPHealthIndicator'
import { getSNMPInterfaceHistory, getSNMPInterfaces, type SNMPInterfaceHistory, type SNMPInterfaceStats } from '../../../lib/api'

type TimeRange = '1h' | '24h' | '7d' | '30d'

const TIME_RANGE_HOURS: Record<TimeRange, number> = {
  '1h': 1,
  '24h': 24,
  '7d': 168,
  '30d': 720,
}

function interfaceHealth(util: number | undefined, status: string): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (status !== 'UP') return 'critical'
  if (util === undefined || util === null) return 'unknown'
  if (util >= 90) return 'critical'
  if (util >= 75) return 'warning'
  return 'healthy'
}

function fmtBytes(bytes: number | undefined): string {
  if (!bytes) return '—'
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(2)} GB`
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function fmtSpeed(bps: number | undefined): string {
  if (!bps) return '—'
  if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(1)} Gbps`
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`
  if (bps >= 1000) return `${(bps / 1000).toFixed(1)} Kbps`
  return `${bps} bps`
}

export default function SNMPInterfaceDetails() {
  const { deviceId: deviceIdParam, interfaceId } = useParams<{ deviceId: string; interfaceId: string }>()
  const navigate = useNavigate()
  const deviceId = Number(deviceIdParam)
  const id = Number(interfaceId)

  const [timeRange, setTimeRange] = useState<TimeRange>('24h')
  const [history, setHistory] = useState<SNMPInterfaceHistory | null>(null)
  const [interfaceInfo, setInterfaceInfo] = useState<SNMPInterfaceStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [histData, ifaces] = await Promise.all([
        getSNMPInterfaceHistory(id, TIME_RANGE_HOURS[timeRange]),
        getSNMPInterfaces(deviceId),
      ])
      setHistory(histData)
      const iface = ifaces.find(i => i.interface_id === id)
      if (iface) setInterfaceInfo(iface)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load interface data')
    } finally {
      setLoading(false)
    }
  }, [deviceId, id, timeRange])

  useEffect(() => { void load() }, [load])

  const handleRefresh = () => { void load() }

  const chartDataRx = (history?.history ?? []).map(p => ({ timestamp: p.timestamp, value: p.rx_mbps }))
  const chartDataTx = (history?.history ?? []).map(p => ({ timestamp: p.timestamp, value: p.tx_mbps }))
  const chartDataUtil = (history?.history ?? []).map(p => ({ timestamp: p.timestamp, value: p.utilization }))

  if (loading) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading interface details...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-lg" style={{ color: '#ff3366' }}>Failed to Load Interface</div>
          <div className="font-mono text-sm mt-2" style={{ color: '#8899bb' }}>{error}</div>
          <button onClick={handleRefresh} className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Retry
          </button>
        </GlassCard>
      </div>
    )
  }

  if (!interfaceInfo) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-lg" style={{ color: '#ff3366' }}>Interface Not Found</div>
          <button onClick={() => navigate(`/snmp/devices/${deviceId}/interfaces`)} className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Back to Interfaces
          </button>
        </GlassCard>
      </div>
    )
  }

  const health = interfaceHealth(interfaceInfo.utilization_percent, interfaceInfo.status)

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/devices/${deviceId}`)} className="hover:text-cyan-400 transition-colors">
          DEVICE
        </button>
        <span>/</span>
        <button onClick={() => navigate(`/snmp/devices/${deviceId}/interfaces`)} className="hover:text-cyan-400 transition-colors">
          INTERFACES
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>{interfaceInfo.name}</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            {interfaceInfo.name}
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {interfaceInfo.description || 'No description'} · ifIndex: {interfaceInfo.if_index}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
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

      {/* Interface Summary */}
      <GlassCard className="p-4">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1 min-w-[250px]">
            <div className="flex items-center gap-3 mb-3">
              <h2 className="font-display font-bold text-lg tracking-wider neon-cyan">
                {interfaceInfo.name}
              </h2>
              <SNMPHealthIndicator health={interfaceHealth(interfaceInfo.utilization_percent, interfaceInfo.status)} showLabel size="md" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>DESCRIPTION</div>
                <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{interfaceInfo.description || '—'}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>INDEX</div>
                <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{interfaceInfo.if_index}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>MAC ADDRESS</div>
                <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{interfaceInfo.mac_address || '—'}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>MTU</div>
                <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{interfaceInfo.mtu || '—'}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>SPEED</div>
                <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{interfaceInfo.speed_display || (interfaceInfo.speed_bps ? `${(interfaceInfo.speed_bps / 1_000_000).toFixed(0)} Mbps` : '—')}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>ADMIN STATUS</div>
                <div className="font-mono text-xs">
                  <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${interfaceInfo.admin_status === 'UP' ? 'text-green-400 bg-green-400/15 border-green-400/30' : 'text-red-400 bg-red-400/15 border-red-400/30'}`}>
                    {interfaceInfo.admin_status}
                  </span>
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>OPER STATUS</div>
                <div className="font-mono text-xs">
                  <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${interfaceInfo.status === 'UP' ? 'text-green-400 bg-green-400/15 border-green-400/30' : 'text-red-400 bg-red-400/15 border-red-400/30'}`}>
                    {interfaceInfo.status}
                  </span>
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>LAST CHANGE</div>
                <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{interfaceInfo.last_change || '—'}</div>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-2 min-w-[200px]">
            <SNMPStatusBadge status="supported" />
            <div className="font-mono text-xs" style={{ color: '#667799' }}>
              Last Poll: {interfaceInfo.last_updated ? new Date(interfaceInfo.last_updated).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }) : '—'}
            </div>
          </div>
        </div>
      </GlassCard>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* RX/TX Chart */}
        <GlassCard className="p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">TRAFFIC (RX/TX)</div>
              <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                {history?.history?.length || 0} data points
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ color: '#00ff88', background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.3)' }}>RX</span>
              <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ color: '#ff6644', background: 'rgba(255,102,68,0.1)', border: '1px solid rgba(255,102,68,0.3)' }}>TX</span>
            </div>
          </div>
          <SNMPMetricChart
            data={[
              { ...chartDataRx, color: '#00ff88', label: 'RX' },
              { ...chartDataTx, color: '#ff6644', label: 'TX' },
            ]}
            height={200}
            unit="Mbps"
            label="Traffic"
            showArea
            showGrid
            showAxes
            noDataMessage="No Historical Data Yet"
          />
        </GlassCard>

        {/* Utilization Chart */}
        <GlassCard className="p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">UTILIZATION</div>
              <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                {history?.history?.length || 0} data points
              </div>
            </div>
            <div className="font-mono text-lg font-semibold" style={{ color: '#ffaa00' }}>
              {interfaceInfo.utilization_percent?.toFixed(1)}%
            </div>
          </div>
          <SNMPMetricChart
            data={chartDataUtil}
            height={200}
            color="#ffaa00"
            unit="%"
            label="Util %"
            showArea
            showGrid
            showAxes
            noDataMessage="No Historical Data Yet"
          />
        </GlassCard>
      </div>

      {/* Packets & Errors Chart */}
      <GlassCard className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">PACKETS & ERRORS</div>
            <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
              {history?.history?.length || 0} data points
            </div>
          </div>
        </div>
        <SNMPMetricChart
          data={[
            { ...(history?.history ?? []).map(p => ({ timestamp: p.timestamp, value: p.rx_mbps * 1000000 / 8 / 1500 })), color: '#00ff88', label: 'RX Pkts/s' },
            { ...(history?.history ?? []).map(p => ({ timestamp: p.timestamp, value: p.tx_mbps * 1000000 / 8 / 1500 })), color: '#ff6644', label: 'TX Pkts/s' },
            { ...(history?.history ?? []).map(p => ({ timestamp: p.timestamp, value: p.errors })), color: '#ff3366', label: 'Errors/s' },
          ]}
          height={200}
          unit="/s"
          label="Rate"
          showArea={false}
          showGrid
          showAxes
          noDataMessage="No Historical Data Yet"
        />
      </GlassCard>

      {/* History Table */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">POLL HISTORY</div>
        </div>
        {history?.history?.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ minWidth: 1000 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                  {['TIMESTAMP', 'RX (Mbps)', 'TX (Mbps)', 'UTIL %', 'RX PKTS', 'TX PKTS', 'ERRORS', 'DISCARDS'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                      style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...(history?.history ?? []).reverse()].map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      {new Date(row.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00ff88' }}>
                      {row.rx_mbps?.toFixed(2)} Mbps
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ff6644' }}>
                      {row.tx_mbps?.toFixed(2)} Mbps
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ffaa00' }}>
                      {row.utilization?.toFixed(1)}%
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#00ff88' }}>
                      {row.rx_packets ?? '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#ff6644' }}>
                      {row.tx_packets ?? '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#ff3366' }}>
                      {row.errors ?? '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#ffaa00' }}>
                      {row.discards ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="font-mono text-xs p-6 text-center" style={{ color: '#8899bb' }}>
            No historical data available for this time range.
          </div>
        )}
      </GlassCard>
    </div>
  )
}
