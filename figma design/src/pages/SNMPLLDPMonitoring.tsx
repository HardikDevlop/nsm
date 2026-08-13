import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getStatusColor } from '../modules/snmpModuleRegistry'
import GlassCard from '../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPLLDPMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('lldp')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'lldp')

  const supported = caps?.lldp === true

  if (!supported) {
    return (
      <SNMPModuleShell module="lldp" title="LLDP Monitoring" unsupportedMessage="LLDP monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const neighbors = (data as any[]) || []

  return (
    <SNMPModuleShell module="lldp" title="LLDP Monitoring" showMonitoringControls={true}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">LLDP NEIGHBORS</div>
        <SNMPDynamicTable
          rows={neighbors}
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