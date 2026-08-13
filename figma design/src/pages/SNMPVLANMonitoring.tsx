import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getStatusColor } from '../modules/snmpModuleRegistry'
import GlassCard from '../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPVLANMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('vlan')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'vlan')

  const supported = caps?.vlan === true

  if (!supported) {
    return (
      <SNMPModuleShell module="vlan" title="VLAN Monitoring" unsupportedMessage="VLAN monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const vlans = (data as any[]) || []

  return (
    <SNMPModuleShell module="vlan" title="VLAN Monitoring" showMonitoringControls={true}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">VLAN INVENTORY</div>
        <SNMPDynamicTable
          rows={vlans}
          loading={isLoading}
          error={error instanceof Error ? error.message : null}
          emptyMessage="No VLAN data available."
          searchPlaceholder="Search VLAN ID, name, status, ports..."
          columns={[
            { key: 'vlan_id', label: 'VLAN ID', sortable: true, type: 'number' },
            { key: 'vlan_name', label: 'Name', sortable: true },
            { key: 'status', label: 'Status', sortable: true, type: 'status' },
            { key: 'tagged_ports', label: 'Tagged Ports' },
            { key: 'untagged_ports', label: 'Untagged Ports' },
            { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
          ]}
        />
      </GlassCard>
    </SNMPModuleShell>
  )
}