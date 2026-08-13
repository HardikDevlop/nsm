import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getStatusColor } from '../modules/snmpModuleRegistry'
import GlassCard from '../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPRoutingMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('routing')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'routing')

  const supported = caps?.routing === true

  if (!supported) {
    return (
      <SNMPModuleShell module="routing" title="Routing Monitoring" unsupportedMessage="Routing monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const routes = (data as any[]) || []

  return (
    <SNMPModuleShell module="routing" title="Routing Monitoring" showMonitoringControls={true}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">ROUTING TABLE</div>
        <SNMPDynamicTable
          rows={routes}
          loading={isLoading}
          error={error instanceof Error ? error.message : null}
          emptyMessage="No routing data available."
          searchPlaceholder="Search destination, next hop, protocol..."
          columns={[
            { key: 'destination', label: 'Destination', sortable: true },
            { key: 'next_hop', label: 'Next Hop', sortable: true },
            { key: 'interface', label: 'Interface', sortable: true },
            { key: 'metric', label: 'Metric', sortable: true, type: 'number' },
            { key: 'protocol', label: 'Protocol', sortable: true },
            { key: 'type', label: 'Type', sortable: true },
            { key: 'status', label: 'Status', sortable: true, type: 'status' },
            { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
          ]}
        />
      </GlassCard>
    </SNMPModuleShell>
  )
}