import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getHealthColor, getStatusColor, formatBytes, formatSpeed } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import SNMPMetricChart from '../components/SNMPMetricChart'
import { useDeviceCapabilities, useMonitoringData } from '../modules/useSNMPModules'

export default function SNMPInterfacesMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('interfaces')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data: monitoringData, isLoading: monitoringLoading, error: monitoringError } = useMonitoringData(id)
  
  // Extract Interfaces data from monitoring API response
  const interfacesModuleData = monitoringData?.modules?.interfaces
  const supported = monitoringData?.capabilities?.interfaces === true || caps?.interfaces === true

  if (!supported) {
    return (
      <SNMPModuleShell module="interfaces" title="Interface Monitoring" unsupportedMessage="Interface monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  // Use data from our working monitoring API first
  const interfaceData = interfacesModuleData?.data
  const interfaces = interfaceData?.interfaces || []
  const totalCount = interfaceData?.interface_count || interfaces.length
  const upCount = interfaceData?.up_count || interfaces.filter(i => i.oper_status === 'up').length
  const downCount = interfaceData?.down_count || interfaces.filter(i => i.oper_status !== 'up').length
  
  const health = downCount > upCount ? 'critical' : downCount > 0 ? 'warning' : 'healthy'

  return (
    <SNMPModuleShell module="interfaces" title="Interface Monitoring" showMonitoringControls={true}>
      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
        {[
          { label: 'Total', value: totalCount.toString(), color: '#00d4ff' },
          { label: 'Up', value: upCount.toString(), color: '#00ff88' },
          { label: 'Down', value: downCount.toString(), color: downCount > 0 ? '#ff3366' : '#8899bb' },
          { label: 'Utilization', value: interfaces.length > 0 ? `${(interfaces.reduce((acc, i) => acc + (i.utilization_percent || 0), 0) / interfaces.length).toFixed(1)}%` : '—', color: '#ffaa00' },
          { label: 'Speed Range', value: interfaces.length > 0 ? `${Math.min(...interfaces.map(i => i.speed_bps || 0)) / 1e6}M-${Math.max(...interfaces.map(i => i.speed_bps || 0)) / 1e9}G` : '—', color: '#7c3aed' },
          { label: 'Source', value: interfaceData ? 'DB Latest' : '—', color: '#00d4ff' },
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
        {interfaceData?.polled_at && (
          <span className="font-mono text-xs" style={{ color: '#667799' }}>
            Last Poll: {new Date(interfaceData.polled_at).toLocaleString()}
          </span>
        )}
        {monitoringData && (
          <span className="font-mono text-xs" style={{ color: '#00d4ff' }}>
            Device: {monitoringData.hostname}
          </span>
        )}
      </div>

      {/* Interface Utilization Chart */}
      <GlassCard className="p-4 mb-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">INTERFACE UTILIZATION</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              {interfaces.filter(i => i.oper_status === 'up').length} active interfaces
            </div>
          </div>
          <div className="font-mono text-xs px-2 py-1 rounded" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
            {upCount}/{totalCount} UP
          </div>
        </div>
        
        {/* Interface bars */}
        <div className="space-y-2">
          {interfaces.length === 0 ? (
            <div className="py-8 text-center font-mono text-xs" style={{ color: '#8899bb' }}>
              No interface samples are available yet. Start monitoring to collect live SNMP data.
            </div>
          ) : interfaces.slice(0, 8).map((iface, idx) => {
            const utilization = iface.utilization_percent || 0
            const statusColor = iface.oper_status === 'up' ? (utilization >= 90 ? '#ff3366' : utilization >= 70 ? '#ffaa00' : '#00ff88') : '#666666'
            
            return (
              <div key={iface.ifIndex || idx} className="flex items-center gap-3">
                <div className="w-24 font-mono text-xs" style={{ color: '#8899bb' }}>
                  {iface.name || `Port ${iface.ifIndex}`}
                </div>
                <div className="flex-1 h-6 rounded overflow-hidden" style={{ background: 'rgba(0,212,255,0.1)' }}>
                  <div 
                    className="h-full transition-all duration-1000 ease-out flex items-center justify-end pr-2"
                    style={{ 
                      width: `${utilization}%`, 
                      background: statusColor,
                      minWidth: utilization > 0 ? '20px' : '0px'
                    }}
                  >
                    {utilization > 10 && (
                      <span className="font-mono text-xs text-white font-bold">
                        {utilization.toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>
                <div className="w-16 font-mono text-xs text-right" style={{ color: statusColor }}>
                  {iface.oper_status?.toUpperCase() || 'UNKNOWN'}
                </div>
                <div className="w-20 font-mono text-xs text-right" style={{ color: '#8899bb' }}>
                  {iface.speed_label || '—'}
                </div>
              </div>
            )
          })}
        </div>
      </GlassCard>

      {/* Interface Details Table */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">INTERFACE DETAILS</div>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                {['Interface', 'Status', 'Speed', 'MAC Address', 'RX Bytes', 'TX Bytes', 'Utilization'].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                    style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {interfaces.map((iface, i) => {
                const statusColor = iface.oper_status === 'up' ? '#00ff88' : iface.oper_status === 'down' ? '#ff3366' : '#8899bb'
                const utilization = iface.utilization_percent || 0
                const utilizationColor = utilization >= 90 ? '#ff3366' : utilization >= 70 ? '#ffaa00' : '#00ff88'
                
                return (
                  <tr key={iface.ifIndex || i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                    <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>
                      {iface.name || `Interface ${iface.ifIndex}`}
                    </td>
                    <td className="px-4 py-2">
                      <span className="font-mono text-xs px-2 py-0.5 rounded uppercase"
                        style={{ color: statusColor, background: `${statusColor}20` }}>
                        {iface.oper_status || 'unknown'}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>
                      {iface.speed_label || formatSpeed(iface.speed_bps) || '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>
                      {iface.mac || '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00d4ff' }}>
                      {iface.in_octets ? formatBytes(iface.in_octets) : '0'}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ffaa00' }}>
                      {iface.out_octets ? formatBytes(iface.out_octets) : '0'}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs font-bold" style={{ color: utilizationColor }}>
                      {utilization.toFixed(1)}%
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Traffic History Chart */}
      {history.length > 0 && (
        <GlassCard className="p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">TRAFFIC HISTORY</div>
              <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
                {history.length} data points
              </div>
            </div>
          </div>
          <SNMPMetricChart
            data={history.map(p => ({ timestamp: p.timestamp, value: p.total_mbps || p.utilization }))}
            height={200}
            color="#00d4ff"
            unit="Mbps"
            label="Traffic"
            showArea
            showGrid
            showAxes
            noDataMessage="No Historical Data Yet"
          />
        </GlassCard>
      )}
    </SNMPModuleShell>
  )
}
