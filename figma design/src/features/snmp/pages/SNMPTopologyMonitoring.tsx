import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPTopologyMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('topology')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'topology')

  const supported = caps?.topology === true || caps?.lldp === true

  if (!supported) {
    return (
      <SNMPModuleShell module="topology" title="Topology" unsupportedMessage="Topology is not available for this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const topology = data as any

  return (
    <SNMPModuleShell module="topology" title="Topology" showMonitoringControls={false}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">NETWORK TOPOLOGY</div>
        <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
          Topology visualization coming soon. Devices: {topology?.devices?.length || 0}, Links: {topology?.links?.length || 0}
        </div>
      </GlassCard>
    </SNMPModuleShell>
  )
}