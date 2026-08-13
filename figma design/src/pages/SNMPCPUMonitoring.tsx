import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getHealthColor, getStatusColor, formatBytes, formatSpeed } from '../modules/snmpModuleRegistry'
import GlassCard from '../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import SNMPMetricChart from '../components/SNMPMetricChart'
import { useModuleData, useDeviceCapabilities, useMonitoringData } from '../modules/useSNMPModules'
import { useLatestCPU } from '../hooks/useSnmpQueries'

export default function SNMPCPUMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('cpu')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'cpu')
  const { data: latestCPU } = useLatestCPU(id)
  
  // NEW: Use our working monitoring API
  const { data: monitoringData, isLoading: monitoringLoading, error: monitoringError } = useMonitoringData(id)
  
  // Extract CPU data from monitoring API response
  const cpuModuleData = monitoringData?.modules?.cpu
  const supported = monitoringData?.capabilities?.cpu === true || caps?.cpu === true

  // Debug logging
  console.log('CPU Module Debug:', {
    id,
    caps,
    supported,
    rawData: data,
    latestCPU,
    monitoringData,
    cpuModuleData,
    isLoading,
    error,
    monitoringLoading,
    monitoringError
  })

  if (!supported) {
    return (
      <SNMPModuleShell module="cpu" title="CPU Monitoring" unsupportedMessage="CPU monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const stats = data as any
  const history = stats?.history || []
  
  // Use data from our working monitoring API first
  const cpuData = cpuModuleData?.data
  const currentUsage = cpuData?.utilization_percent ?? latestCPU?.current_usage ?? stats?.data?.overall_percent ?? stats?.overall_percent
  const health = currentUsage !== undefined && currentUsage >= 90 ? 'critical' : currentUsage !== undefined && currentUsage >= 70 ? 'warning' : 'healthy'

  // Debug logging
  console.log('CPU Stats Data:', { 
    data, 
    stats, 
    currentUsage, 
    latestCPU, 
    cpuData,
    monitoringData 
  })

  return (
    <SNMPModuleShell module="cpu" title="CPU Monitoring" showMonitoringControls={true}>
      {/* Stat Tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        {[
          { label: 'Current', value: currentUsage !== undefined ? `${currentUsage.toFixed(1)}%` : '—', color: currentUsage !== undefined && currentUsage >= 90 ? '#ff3366' : currentUsage !== undefined && currentUsage >= 70 ? '#ffaa00' : '#00ff88' },
          { label: 'Average', value: (cpuData?.average_percent ?? stats?.data?.average_percent ?? stats?.average) !== undefined ? `${(cpuData?.average_percent ?? stats?.data?.average_percent ?? stats?.average).toFixed(1)}%` : '—', color: '#00d4ff' },
          { label: 'Load 1m', value: (cpuData?.load_avg?.['1min'] ?? stats?.data?.load_avg?.['1min'] ?? stats?.load_1min) !== undefined ? `${(cpuData?.load_avg?.['1min'] ?? stats?.data?.load_avg?.['1min'] ?? stats?.load_1min).toFixed(2)}` : '—', color: '#ffaa00' },
          { label: 'Load 5m', value: (cpuData?.load_avg?.['5min'] ?? stats?.data?.load_avg?.['5min'] ?? stats?.load_5min) !== undefined ? `${(cpuData?.load_avg?.['5min'] ?? stats?.data?.load_avg?.['5min'] ?? stats?.load_5min).toFixed(2)}` : '—', color: '#7c3aed' },
          { label: 'Source', value: cpuData ? 'DB Latest' : stats?.data?.source ?? stats?.source ?? '—', color: '#00d4ff' },
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
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <div
          className="w-3 h-3 rounded-full"
          style={{ background: getHealthColor(health), boxShadow: `0 0 8px ${getHealthColor(health)}` }}
          title={`Health: ${health}`}
        />
        <span className="font-mono text-xs" style={{ color: '#8899bb' }}>Health: {health.toUpperCase()}</span>
        {(cpuData?.polled_at || stats?.timestamp) && (
          <span className="font-mono text-xs" style={{ color: '#667799' }}>
            Last Poll: {new Date(cpuData?.polled_at || stats.timestamp).toLocaleString()}
          </span>
        )}
        {stats?.data?.display && (
          <span className="font-mono text-xs" style={{ color: '#00d4ff' }}>
            Display: {stats.data.display}
          </span>
        )}
      </div>

      {/* Main Chart */}
      <GlassCard className="p-4 mb-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">CPU UTILIZATION</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              {history.length} data points
            </div>
          </div>
          <div className="font-mono text-xs px-2 py-1 rounded" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
            {currentUsage?.toFixed(1)}%
          </div>
        </div>
        <SNMPMetricChart
          data={history.map(p => ({ timestamp: p.timestamp, value: p.usage }))}
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
      {(cpuData?.per_core || (stats?.data?.per_core && stats.data.per_core.length > 0)) && (
        <GlassCard className="p-4 mb-4">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">PER CORE USAGE</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            {Object.entries(cpuData?.per_core || {}).length > 0 
              ? Object.entries(cpuData.per_core).map(([coreId, usage]: [string, any]) => {
                  const pct = typeof usage === 'number' ? usage : usage?.usage ?? 0
                  const coreColor = pct >= 90 ? '#ff3366' : pct >= 70 ? '#ffaa00' : '#00ff88'
                  return (
                    <div key={coreId} className="text-center">
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
                        Core {coreId}
                      </div>
                    </div>
                  )
                })
              : stats.data.per_core.map((core: any, idx: number) => {
                  const pct = core.usage ?? core
                  const coreColor = pct >= 90 ? '#ff3366' : pct >= 70 ? '#ffaa00' : '#00ff88'
                  return (
                    <div key={core.core ?? idx} className="text-center">
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
                        Core {core.core ?? idx}
                      </div>
                    </div>
                  )
                })
            }
          </div>
        </GlassCard>
      )}

      {/* History Table */}
      {history.length > 0 && (
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
                {[...history].reverse().map((row, i) => {
                  const h = row.usage >= 90 ? 'critical' : row.usage >= 70 ? 'warning' : 'healthy'
                  const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>
                        {new Date(row.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#00d4ff' }}>
                        {row.usage.toFixed(1)}%
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
    </SNMPModuleShell>
  )
}