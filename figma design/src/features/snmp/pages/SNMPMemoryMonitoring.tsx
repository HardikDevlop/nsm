import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getHealthColor, getStatusColor, formatBytes } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { useDeviceCapabilities, useMonitoringData } from '../modules/useSNMPModules'
import { useLatestMemory } from '../hooks/useSnmpQueries'

function memoryHealth(util: number | undefined): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (util === undefined || util === null) return 'unknown'
  if (util >= 90) return 'critical'
  if (util >= 75) return 'warning'
  return 'healthy'
}

export default function SNMPMemoryMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('memory')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data: latestMemory } = useLatestMemory(id)
  const { data: monitoringData, isLoading: monitoringLoading, error: monitoringError } = useMonitoringData(id)
  
  const memoryModuleData = monitoringData?.modules?.memory
  const stats = memoryModuleData as any
  const memoryData = memoryModuleData?.data || latestMemory || {}
  const hasMemoryData = Object.keys(memoryData || {}).length > 0
  const supported =
    monitoringData?.capabilities?.memory === true ||
    caps?.memory === true ||
    memoryModuleData?.supported === true ||
    hasMemoryData

  if (!supported) {
    return (
      <SNMPModuleShell module="memory" title="Memory Monitoring" unsupportedMessage="Memory monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const history = stats?.history || []
  const utilization = memoryData?.utilization_percent ?? latestMemory?.utilization_percent
  const totalBytes = memoryData?.total_bytes ?? latestMemory?.total_bytes
  const usedBytes = memoryData?.used_bytes ?? latestMemory?.used_bytes
  const freeBytes = memoryData?.free_bytes ?? latestMemory?.free_bytes
  
  const health = memoryHealth(utilization)
  const memoryCollector = {
    collector: 'memory',
    supported: true,
    timestamp: memoryModuleData?.timestamp || memoryData?.polled_at,
    data: memoryData,
    missing: memoryModuleData?.missing || [],
    warnings: memoryModuleData?.warnings || [],
  }

  return (
    <SNMPModuleShell module="memory" title="Memory Monitoring" showMonitoringControls={true}>
      {/* Stat Tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        {[
          { label: 'Total', value: totalBytes ? formatBytes(totalBytes) : '—', color: '#00d4ff' },
          { label: 'Used', value: usedBytes ? formatBytes(usedBytes) : '—', color: utilization && utilization >= 90 ? '#ff3366' : utilization && utilization >= 75 ? '#ffaa00' : '#00ff88' },
          { label: 'Free', value: freeBytes ? formatBytes(freeBytes) : '—', color: '#7c3aed' },
          { label: 'Utilization', value: utilization !== undefined ? `${utilization.toFixed(1)}%` : '—', color: utilization && utilization >= 90 ? '#ff3366' : utilization && utilization >= 75 ? '#ffaa00' : '#00ff88' },
          { label: 'Source', value: memoryData ? 'DB Latest' : '—', color: '#ffaa00' },
        ].map(tile => (
          <GlassCard key={tile.label} className="p-4 text-center">
            <div className="font-display font-bold text-xl sm:text-2xl" style={{ color: tile.color }}>
              {tile.value}
            </div>
            <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-text)' }}>{tile.label}</div>
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
        <span className="font-mono text-xs" style={{ color: 'var(--t-text)' }}>Health: {health.toUpperCase()}</span>
        {memoryData?.polled_at && (
          <span className="font-mono text-xs" style={{ color: 'var(--t-text)' }}>
            Last Poll: {new Date(memoryData.polled_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
          </span>
        )}
      </div>

      {/* Swap */}
      {((memoryData?.swap_total ?? latestMemory?.swap_total) !== undefined && (memoryData?.swap_total ?? latestMemory?.swap_total) > 0) && (
        <GlassCard className="p-4 mb-4">
          <div className="font-display font-bold text-sm tracking-wider mb-4" style={{ color: 'var(--t-text)' }}>SWAP</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded" style={{ background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.1)' }}>
              <div className="font-mono text-[10px]" style={{ color: 'var(--t-text)' }}>TOTAL</div>
              <div className="font-mono text-xs font-semibold" style={{ color: 'var(--t-text)' }}>{formatBytes(memoryData?.swap_total ?? latestMemory?.swap_total)}</div>
            </div>
            <div className="p-3 rounded" style={{ background: 'rgba(0,255,136,0.05)', border: '1px solid rgba(0,255,136,0.1)' }}>
              <div className="font-mono text-[10px]" style={{ color: 'var(--t-text)' }}>FREE</div>
              <div className="font-mono text-xs font-semibold" style={{ color: 'var(--t-text)' }}>{formatBytes(memoryData?.swap_free ?? latestMemory?.swap_free)}</div>
            </div>
            <div className="p-3 rounded" style={{ background: 'rgba(124,58,237,0.05)', border: '1px solid rgba(124,58,237,0.1)' }}>
              <div className="font-mono text-[10px]" style={{ color: 'var(--t-text)' }}>USED</div>
              <div className="font-mono text-xs font-semibold" style={{ color: 'var(--t-text)' }}>{formatBytes(((memoryData?.swap_total ?? latestMemory?.swap_total) || 0) - ((memoryData?.swap_free ?? latestMemory?.swap_free) || 0))}</div>
            </div>
          </div>
        </GlassCard>
      )}

      <SNMPCollectorDataCard name="memory" collector={memoryCollector} />

      {/* History Table */}
      {history.length > 0 && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-display font-bold text-sm tracking-wider" style={{ color: 'var(--t-text)' }}>POLL HISTORY</div>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                  {['Timestamp', 'Used', 'Free', 'Utilization', 'Health'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                      style={{ color: 'var(--t-text)', background: 'var(--t-table-header)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().map((row, i) => {
                  const h = memoryHealth(row.utilization)
                  const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                      <td className="px-4 py-2 font-mono text-[10px]" style={{ color: 'var(--t-text)' }}>
                        {new Date(row.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--t-text)' }}>
                        {formatBytes(history[i]?.used ?? 0)}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--t-text)' }}>
                        {formatBytes(history[i]?.free ?? 0)}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#00d4ff' }}>
                        {row.utilization.toFixed(1)}%
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
