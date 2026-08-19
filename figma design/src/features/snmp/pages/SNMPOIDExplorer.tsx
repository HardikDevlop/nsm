import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getStatusColor } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPDynamicTable from '../components/SNMPDynamicTable'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'

export default function SNMPOIDExplorer() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('oids')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'oids')

  const supported = caps?.oids === true || caps?.inventory === true

  if (!supported) {
    return (
      <SNMPModuleShell module="oids" title="OID Explorer" unsupportedMessage="OID Explorer is not available for this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const oids = (data as any[]) || []

  return (
    <SNMPModuleShell module="oids" title="OID Explorer" showMonitoringControls={false}>
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">OID CACHE</div>
        <SNMPDynamicTable
          rows={oids}
          loading={isLoading}
          error={error instanceof Error ? error.message : null}
          emptyMessage="No OID data available."
          searchPlaceholder="Search OID, name, label..."
          columns={[
            { key: 'oid', label: 'OID', sortable: true },
            { key: 'oid_name', label: 'Name', sortable: true },
            { key: 'supported', label: 'Supported', sortable: true, type: 'status' },
            { key: 'vendor_specific', label: 'Vendor Specific', sortable: true, type: 'status' },
            { key: 'last_seen', label: 'Last Seen', sortable: true, type: 'timestamp' },
          ]}
        />
      </GlassCard>
    </SNMPModuleShell>
  )
}