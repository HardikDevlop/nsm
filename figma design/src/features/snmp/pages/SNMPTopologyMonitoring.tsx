import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import { useMonitoringData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPTopologyMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('topology')!

  const { data: caps, isLoading: capabilitiesLoading, error: capabilitiesError } = useDeviceCapabilities(id)
  const { data: monitoringData, isLoading: monitoringLoading, error: monitoringError } = useMonitoringData(id)

  const supported = caps?.topology === true || caps?.lldp === true

  if (capabilitiesLoading || monitoringLoading) {
    return (
      <SNMPModuleShell module="topology" title="Topology" showMonitoringControls={false}>
        <GlassCard className="p-6 text-center font-mono text-xs" style={{ color: '#00d4ff' }}>Loading topology data...</GlassCard>
      </SNMPModuleShell>
    )
  }

  if (capabilitiesError || monitoringError) {
    return (
      <SNMPModuleShell module="topology" title="Topology" showMonitoringControls={false}>
        <GlassCard className="p-6 text-center font-mono text-xs" style={{ color: '#ff6b8a' }}>Unable to load topology data.</GlassCard>
      </SNMPModuleShell>
    )
  }

  if (!supported) {
    return (
      <SNMPModuleShell module="topology" title="Topology" unsupportedMessage="Topology is not available for this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const topology = monitoringData?.modules?.topology?.data || monitoringData?.modules?.topology || {}

  return (
    <SNMPModuleShell module="topology" title="Topology" showMonitoringControls={false}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">NETWORK TOPOLOGY</div>
        <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
          Stored topology snapshot. Devices: {topology?.devices?.length || 0}, Links: {topology?.links?.length || 0}
        </div>
      </GlassCard>
    </SNMPModuleShell>
  )
}
