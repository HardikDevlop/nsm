import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import GlassCard from '../../../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPLLDPMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)

  const { data: caps, isLoading: capabilitiesLoading } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'lldp')

  const response = data as any
  const neighbors = Array.isArray(response)
    ? response
    : Array.isArray(response?.data?.neighbors)
      ? response.data.neighbors
      : Array.isArray(response?.neighbors)
        ? response.neighbors
        : []
  const normalizedNeighbors = neighbors.map((neighbor: any) => ({
    ...neighbor,
    local_port: neighbor.local_port ?? neighbor.local_port_desc ?? neighbor.local_port_num,
    remote_device: neighbor.remote_device ?? neighbor.remote_sys_name ?? neighbor.remote_chassis_id,
    remote_port: neighbor.remote_port ?? neighbor.remote_port_id ?? neighbor.remote_port_desc,
    remote_system_name: neighbor.remote_system_name ?? neighbor.remote_sys_name,
    remote_mgmt_ip: neighbor.remote_mgmt_ip ?? neighbor.mgmt_address,
    capabilities: neighbor.capabilities ?? neighbor.capabilities_supported ?? [],
    last_updated: neighbor.last_updated ?? response?.timestamp,
  }))
  const supported = caps?.lldp === true || response?.supported === true || normalizedNeighbors.length > 0

  if (!supported && !capabilitiesLoading && !isLoading) {
    return (
      <SNMPModuleShell module="lldp" title="LLDP Monitoring" unsupportedMessage="LLDP monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  return (
    <SNMPModuleShell module="lldp" title="LLDP Monitoring" showMonitoringControls={true}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">LLDP NEIGHBORS</div>
        <SNMPDynamicTable
          rows={normalizedNeighbors}
          loading={isLoading}
          error={error instanceof Error ? error.message : null}
          emptyMessage="No LLDP neighbor data available."
          searchPlaceholder="Search local port, remote device, management IP..."
          columns={[
            { key: 'local_port', label: 'Local Interface', sortable: true },
            { key: 'remote_device', label: 'Remote Device', sortable: true },
            { key: 'remote_port', label: 'Remote Interface', sortable: true },
            { key: 'remote_system_name', label: 'System Name', sortable: true },
            { key: 'remote_mgmt_ip', label: 'Management IP', sortable: true },
            { key: 'capabilities', label: 'Capabilities' },
            { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
          ]}
        />
      </GlassCard>
    </SNMPModuleShell>
  )
}
