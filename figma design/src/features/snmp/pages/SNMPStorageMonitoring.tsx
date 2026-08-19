import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getHealthColor, getStatusColor, formatBytes } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { useModuleData, useDeviceCapabilities, useMonitoringData } from '../modules/useSNMPModules'

function storageHealth(util: number | undefined): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (util === undefined || util === null) return 'unknown'
  if (util >= 95) return 'critical'
  if (util >= 85) return 'warning'
  return 'healthy'
}

export default function SNMPStorageMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('storage')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'storage')
  
  // NEW: Use our working monitoring API
  const { data: monitoringData, isLoading: monitoringLoading, error: monitoringError } = useMonitoringData(id)
  
  // Extract Storage data from all available APIs. Prefer DB/cache plus direct/live fallback.
  const storageModuleData = monitoringData?.modules?.storage
  const stats = data as any
  const storageData = storageModuleData?.data || stats?.data || {}
  const volumes = storageData?.volumes || stats?.data?.volumes || []
  const hasStorageData = Object.keys(storageData || {}).length > 0 || volumes.length > 0
  const supported =
    monitoringData?.capabilities?.storage === true ||
    caps?.storage === true ||
    stats?.supported === true ||
    storageModuleData?.supported === true ||
    hasStorageData

  // Debug logging
  console.log('Storage Module Debug:', {
    id,
    caps,
    supported,
    rawData: data,
    monitoringData,
    storageModuleData,
    isLoading,
    error,
    monitoringLoading,
    monitoringError
  })

  if (!supported) {
    return (
      <SNMPModuleShell module="storage" title="Storage Monitoring" unsupportedMessage="Storage monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const history = stats?.history || []
  const volumeCount = storageData?.volume_count || stats?.data?.volume_count || volumes.length
  const storageCollector = {
    collector: 'storage',
    supported: true,
    timestamp: stats?.timestamp || storageModuleData?.timestamp || storageData?.polled_at,
    data: storageData,
    missing: stats?.missing || [],
    warnings: stats?.warnings || [],
  }

  // Calculate overall storage health
  const overallUtilization = volumes.length > 0 ? 
    volumes.reduce((acc, vol) => acc + (vol.utilization_percent || 0), 0) / volumes.length : 0
  const health = storageHealth(overallUtilization)

  return (
    <SNMPModuleShell module="storage" title="Storage Monitoring" showMonitoringControls={true}>
      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        {[
          { label: 'Volumes', value: volumeCount.toString(), color: '#00d4ff' },
          { label: 'Total Space', value: volumes.length > 0 ? formatBytes(volumes.reduce((acc, v) => acc + (v.total_bytes || 0), 0)) : '—', color: '#7c3aed' },
          { label: 'Used Space', value: volumes.length > 0 ? formatBytes(volumes.reduce((acc, v) => acc + (v.used_bytes || 0), 0)) : '—', color: '#ffaa00' },
          { label: 'Free Space', value: volumes.length > 0 ? formatBytes(volumes.reduce((acc, v) => acc + (v.free_bytes || 0), 0)) : '—', color: '#00ff88' },
          { label: 'Avg Usage', value: overallUtilization ? `${overallUtilization.toFixed(1)}%` : '—', color: overallUtilization >= 95 ? '#ff3366' : overallUtilization >= 85 ? '#ffaa00' : '#00ff88' },
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
        {(storageData?.polled_at || stats?.data?.last_poll) && (
          <span className="font-mono text-xs" style={{ color: '#667799' }}>
            Last Poll: {new Date(storageData?.polled_at || stats.data.last_poll).toLocaleString()}
          </span>
        )}
        {monitoringData && (
          <span className="font-mono text-xs" style={{ color: '#00d4ff' }}>
            Device: {monitoringData.hostname}
          </span>
        )}
      </div>

      {/* Volume Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
        {volumes.map((volume, idx) => {
          const utilization = volume.utilization_percent || 0
          const h = storageHealth(utilization)
          const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
          
          return (
            <GlassCard key={volume.volume_id || volume.index || idx} className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="font-display font-bold text-sm neon-cyan">
                    {volume.mount_name || volume.filesystem || `Volume ${volume.index || idx + 1}`}
                  </div>
                  <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
                    {volume.type_label || volume.type || 'Storage Volume'}
                  </div>
                </div>
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: hColors[h], boxShadow: `0 0 6px ${hColors[h]}` }}
                />
              </div>

              {/* Usage Bar */}
              <div className="mb-3">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-mono text-xs" style={{ color: '#8899bb' }}>Usage</span>
                  <span className="font-mono text-xs font-bold" style={{ color: hColors[h] }}>
                    {utilization.toFixed(1)}%
                  </span>
                </div>
                <div className="w-full h-3 rounded-lg overflow-hidden" style={{ background: 'rgba(0,212,255,0.1)' }}>
                  <div 
                    className="h-full transition-all duration-1000 ease-out"
                    style={{ 
                      width: `${utilization}%`, 
                      background: hColors[h],
                      boxShadow: `0 0 8px ${hColors[h]}60`
                    }}
                  />
                </div>
              </div>

              {/* Storage Stats */}
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="font-mono text-xs" style={{ color: '#8899bb' }}>Total:</span>
                  <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>
                    {volume.total_bytes ? formatBytes(volume.total_bytes) : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="font-mono text-xs" style={{ color: '#8899bb' }}>Used:</span>
                  <span className="font-mono text-xs" style={{ color: '#ffaa00' }}>
                    {volume.used_bytes ? formatBytes(volume.used_bytes) : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="font-mono text-xs" style={{ color: '#8899bb' }}>Free:</span>
                  <span className="font-mono text-xs" style={{ color: '#00ff88' }}>
                    {volume.free_bytes ? formatBytes(volume.free_bytes) : '—'}
                  </span>
                </div>
              </div>
            </GlassCard>
          )
        })}
      </div>

      {/* Storage Utilization Chart */}
      <GlassCard className="p-4 mb-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">STORAGE UTILIZATION</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              {volumes.length} volumes monitored
            </div>
          </div>
          <div className="font-mono text-xs px-2 py-1 rounded" style={{ color: '#ffaa00', background: 'rgba(255,170,0,0.1)', border: '1px solid rgba(255,170,0,0.2)' }}>
            {overallUtilization.toFixed(1)}% avg
          </div>
        </div>
        <SNMPMetricChart
          data={history.map(p => ({ timestamp: p.timestamp, value: p.utilization || overallUtilization }))}
          height={200}
          color="#ffaa00"
          unit="%"
          label="Storage %"
          showArea
          showGrid
          showAxes
          noDataMessage="No Historical Data Yet"
        />
      </GlassCard>

      {/* Volume Details Table */}
      {volumes.length > 0 && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">VOLUME DETAILS</div>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                  {['Mount Point', 'Type', 'Total', 'Used', 'Free', 'Utilization', 'Health'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                      style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {volumes.map((vol, i) => {
                  const utilization = vol.utilization_percent || 0
                  const h = storageHealth(utilization)
                  const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                  return (
                    <tr key={vol.volume_id || i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                      <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>
                        {vol.mount_name || vol.filesystem || `Volume ${vol.index || i + 1}`}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>
                        {vol.type_label || vol.type || '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#7c3aed' }}>
                        {vol.total_bytes ? formatBytes(vol.total_bytes) : '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ffaa00' }}>
                        {vol.used_bytes ? formatBytes(vol.used_bytes) : '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00ff88' }}>
                        {vol.free_bytes ? formatBytes(vol.free_bytes) : '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs font-bold" style={{ color: hColors[h] }}>
                        {utilization.toFixed(1)}%
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

      {/* No Volumes */}
      {volumes.length === 0 && (
        <GlassCard className="p-8 text-center">
          <div className="font-mono text-sm mb-3" style={{ color: '#8899bb' }}>
            No storage volumes found
          </div>
          <div className="font-mono text-xs" style={{ color: '#667799' }}>
            This device may not support storage monitoring or no volumes are currently mounted.
          </div>
        </GlassCard>
      )}

      <SNMPCollectorDataCard name="storage" collector={storageCollector} />
    </SNMPModuleShell>
  )
}
