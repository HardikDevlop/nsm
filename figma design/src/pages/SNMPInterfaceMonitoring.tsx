import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getHealthColor, getStatusColor, formatBytes, formatSpeed } from '../modules/snmpModuleRegistry'
import GlassCard from '../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'
import { useLatestInterfaces } from '../hooks/useSnmpQueries'

function interfaceHealth(util: number | undefined, status: string): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (status !== 'UP') return 'critical'
  if (util === undefined || util === null) return 'unknown'
  if (util >= 90) return 'critical'
  if (util >= 75) return 'warning'
  return 'healthy'
}

export default function SNMPInterfaceMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('interfaces')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'interfaces')
  const { data: latestInterfaces } = useLatestInterfaces(id)

  const supported = caps?.interfaces === true

  if (!supported) {
    return (
      <SNMPModuleShell module="interfaces" title="Interface Monitoring" unsupportedMessage="Interface monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  // Backend returns data.interfaces array
  const interfaces = (data as any)?.data?.interfaces ?? (data as any[]) ?? (latestInterfaces || [])
  const upCount = interfaces.filter(i => (i.oper_status ?? '').toUpperCase() === 'UP').length
  const downCount = interfaces.filter(i => (i.oper_status ?? '').toUpperCase() === 'DOWN' || i.oper_status === 'down').length

  // Debug logging
  console.log('Interfaces Data:', { data, interfaces, latestInterfaces })

  return (
    <SNMPModuleShell module="interfaces" title="Interface Monitoring" showMonitoringControls={true}>
      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Total', value: interfaces.length, color: '#00d4ff' },
          { label: 'UP', value: upCount, color: '#00ff88' },
          { label: 'DOWN', value: downCount, color: downCount > 0 ? '#ff3366' : '#00ff88' },
          { label: 'Max Speed', value: formatSpeed(Math.max(...interfaces.map(i => i.speed_bps || 0))), color: '#ffaa00' },
        ].map(tile => (
          <GlassCard key={tile.label} className="p-4 text-center">
            <div className="font-display font-bold text-xl sm:text-2xl" style={{ color: tile.color }}>
              {tile.value}
            </div>
            <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{tile.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Interface Table */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">
            INTERFACES ({interfaces.length})
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full" style={{ minWidth: 1100 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                {[
                  { key: 'name', label: 'NAME', sortable: true },
                  { key: 'description', label: 'DESCRIPTION', sortable: true },
                  { key: 'status', label: 'STATUS' },
                  { key: 'speed', label: 'SPEED', sortable: true },
                  { key: 'mac', label: 'MAC', sortable: true },
                  { key: 'rx', label: 'RX', sortable: true },
                  { key: 'tx', label: 'TX', sortable: true },
                  { key: 'util', label: 'UTIL %', sortable: true },
                  { key: 'errors', label: 'ERRORS', sortable: true },
                  { key: 'discards', label: 'DISCARDS', sortable: true },
                ].map(col => (
                  <th
                    key={col.key}
                    className="text-left px-4 py-2.5 font-mono text-xs sticky top-0 select-none"
                    style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)', userSelect: 'none' }}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {interfaces.map((iface, index) => {
                const operStatus = (iface.oper_status ?? '').toUpperCase()
                const health = interfaceHealth(iface.utilization_percent, operStatus)
                const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                return (
                  <tr
                    key={iface.interface_id ?? iface.ifIndex ?? iface.name ?? index}
                    style={{
                      borderBottom: '1px solid rgba(0,212,255,0.04)',
                      background: index % 2 === 0 ? 'transparent' : 'rgba(0,212,255,0.01)',
                    }}
                  >
                    <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>
                      {iface.name ?? `Interface ${iface.ifIndex}`}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs truncate max-w-[200px]" style={{ color: '#8899bb' }}>
                      {iface.description ?? iface.alias ?? '—'}
                    </td>
                    <td className="px-4 py-2">
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
                        style={{
                          background: (iface.oper_status === 'UP' || iface.oper_status === 'up') ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)',
                          color: (iface.oper_status === 'UP' || iface.oper_status === 'up') ? '#00ff88' : '#ff3366',
                          border: `1px solid ${(iface.oper_status === 'UP' || iface.oper_status === 'up') ? 'rgba(0,255,136,0.3)' : 'rgba(255,51,102,0.3)'}`,
                        }}>
                        {(iface.oper_status ?? 'UNKNOWN').toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      {formatSpeed(iface.speed_bps)}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      {iface.mac_address ?? iface.mac ?? '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00ff88' }}>
                      {formatBytes((iface.rx_mbps ? iface.rx_mbps * 1_000_000 / 8 : iface.rx_octets) ?? (iface.in_octets ?? 0))}/s
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ff6644' }}>
                      {formatBytes((iface.tx_mbps ? iface.tx_mbps * 1_000_000 / 8 : iface.tx_octets) ?? (iface.out_octets ?? 0))}/s
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: iface.utilization_percent && iface.utilization_percent >= 90 ? '#ff3366' : iface.utilization_percent && iface.utilization_percent >= 75 ? '#ffaa00' : '#ffaa00' }}>
                      {iface.utilization_percent !== null && iface.utilization_percent !== undefined ? `${iface.utilization_percent.toFixed(1)}%` : '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: (iface.errors ?? iface.in_errors ?? 0) > 0 ? '#ff3366' : '#8899bb' }}>
                      {(iface.errors ?? iface.in_errors ?? 0)}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: (iface.discards ?? iface.in_discards ?? 0) > 0 ? '#ffaa00' : '#8899bb' }}>
                      {(iface.discards ?? iface.in_discards ?? 0)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </SNMPModuleShell>
  )
}