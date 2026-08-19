import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import GlassCard from '../../../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPVLANMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)

  const { data: caps, isLoading: capabilitiesLoading } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'vlan')

  const response = data as any
  const rawVlans = Array.isArray(response)
    ? response
    : Array.isArray(response?.data?.vlans)
      ? response.data.vlans
      : Array.isArray(response?.vlans)
        ? response.vlans
        : []
  const vlans = rawVlans.map((vlan: any) => ({
    ...vlan,
    // The collector calls this field `name`; keep the table contract stable.
    vlan_name: vlan.vlan_name ?? vlan.name,
    egress_ports: Array.isArray(vlan.egress_ports) ? vlan.egress_ports : [],
    untagged_ports: Array.isArray(vlan.untagged_ports) ? vlan.untagged_ports : [],
    tagged_ports: Array.isArray(vlan.tagged_ports) ? vlan.tagged_ports : [],
    port_count: vlan.port_count ?? vlan.egress_ports?.length ?? 0,
    last_updated: vlan.last_updated ?? response?.timestamp,
  }))
  const supported = caps?.vlan === true || response?.supported === true || vlans.length > 0

  if (!supported && !capabilitiesLoading && !isLoading) {
    return (
      <SNMPModuleShell module="vlan" title="VLAN Monitoring" unsupportedMessage="VLAN monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

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
            { key: 'egress_ports', label: 'Egress Ports' },
            { key: 'untagged_ports', label: 'Untagged Ports' },
            { key: 'tagged_ports', label: 'Tagged Ports' },
            { key: 'port_count', label: 'Port Count', sortable: true, type: 'number' },
            { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
          ]}
        />
      </GlassCard>
    </SNMPModuleShell>
  )
}
