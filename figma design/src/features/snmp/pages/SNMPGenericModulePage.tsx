import { useLocation, useParams } from 'react-router'
import GlassCard from '../../../components/GlassCard'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig } from '../modules/snmpModuleRegistry'
import { useModuleData, useMonitoringData } from '../modules/useSNMPModules'

const TITLE: Record<string, string> = {
  mac_table: 'MAC Table',
  cdp: 'CDP',
  arp: 'ARP',
}

function titleize(text: string): string {
  return TITLE[text] || text.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function hasCollectorData(collector: any): boolean {
  const data = collector?.data
  if (!data) return false
  if (Array.isArray(data)) return data.length > 0
  if (typeof data === 'object') return Object.keys(data).length > 0
  return true
}

export default function SNMPGenericModulePage() {
  const { deviceId, moduleId } = useParams<{ deviceId: string; moduleId: string }>()
  const location = useLocation()
  const id = Number(deviceId)
  const routeModule = location.pathname.split('/').filter(Boolean).at(-1)
  const moduleName = moduleId || routeModule || 'system'
  const config = getModuleConfig(moduleName)

  // MAC tables need the authoritative endpoint because the generic monitoring
  // snapshot intentionally contains only persisted metrics, not live FDB/ARP.
  const isMacTable = moduleName === 'mac_table'
  const { data: monitoringData, isLoading: isMonitoringLoading, error: monitoringError } = useMonitoringData(id, !isMacTable)
  const { data: macTableData, isLoading: isMacTableLoading, isFetching: isMacTableFetching, error: macTableError, refetch: refetchMacTable } = useModuleData(id, isMacTable ? 'mac_table' : null)
  const { data: arpTableData, isFetching: isArpTableFetching, refetch: refetchArpTable } = useModuleData(id, isMacTable ? 'arp' : null)
  const dbModule = monitoringData?.modules?.[moduleName]
  const arpEntries = moduleName === 'mac_table'
    ? ((arpTableData?.data?.entries) || [])
    : []

  const dbCollector = isMacTable
    ? macTableData
    : dbModule
    ? {
        collector: moduleName,
        supported: dbModule.supported === true,
        timestamp: monitoringData?.timestamp,
        data: dbModule.data,
        reason: dbModule.supported ? undefined : 'No latest data stored for this module yet.',
      }
    : null

  const collectors = [dbCollector].filter(Boolean)
  const collector = collectors.find(c => c.supported === true && hasCollectorData(c)) ||
    collectors.find(hasCollectorData) ||
    collectors.find(c => c.supported === true) ||
    collectors[0]
  const supported = collector?.supported === true
  const title = titleize(config?.label || moduleName)
  const isLoading = isMacTable ? isMacTableLoading : isMonitoringLoading
  const error = isMacTable ? macTableError : monitoringError

  return (
    <SNMPModuleShell
      module={moduleName}
      title={title}
      showMonitoringControls={Boolean(config)}
      unsupportedMessage={`${title} is not supported by this device.`}
      allowUnsupportedContent
    >
      {isLoading ? (
        <GlassCard className="p-8 text-center">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading {title.toLowerCase()}...</div>
        </GlassCard>
      ) : error ? (
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold" style={{ color: '#ff3366' }}>Unable to load {title}</div>
          <div className="font-mono text-xs mt-2" style={{ color: '#8899bb' }}>{error.message}</div>
        </GlassCard>
      ) : collector ? (
        <SNMPCollectorDataCard
          name={moduleName}
          collector={collector}
          arpEntries={arpEntries}
          refreshing={isMacTable && (isMacTableFetching || isArpTableFetching)}
          onRefresh={isMacTable ? () => { void Promise.all([refetchMacTable(), refetchArpTable()]) } : undefined}
        />
      ) : (
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-base" style={{ color: '#8899bb' }}>No {title} data yet.</div>
          <div className="font-mono text-xs mt-2" style={{ color: '#667799' }}>
            Start monitoring or refresh after SNMP discovery completes.
          </div>
        </GlassCard>
      )}
    </SNMPModuleShell>
  )
}
