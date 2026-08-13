import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getStatusColor } from '../modules/snmpModuleRegistry'
import GlassCard from '../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPPollingMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('polling')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'polling')

  const supported = true // Polling is always available

  return (
    <SNMPModuleShell module="polling" title="Polling History" showMonitoringControls={false}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">POLLING HISTORY</div>
        <SNMPDynamicTable
          rows={(data as any[]) || []}
          loading={isLoading}
          error={error instanceof Error ? error.message : null}
          emptyMessage="No polling history available."
          searchPlaceholder="Search module, status, error..."
          columns={[
            { key: 'timestamp', label: 'Timestamp', sortable: true, type: 'timestamp' },
            { key: 'collector', label: 'Module', sortable: true },
            { key: 'status', label: 'Status', sortable: true, type: 'status' },
            { key: 'duration_ms', label: 'Duration (ms)', sortable: true, type: 'number' },
            { key: 'error', label: 'Error', sortable: true },
          ]}
        />
      </GlassCard>
    </SNMPModuleShell>
  )
}