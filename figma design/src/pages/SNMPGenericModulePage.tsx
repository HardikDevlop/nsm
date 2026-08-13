import { useLocation, useParams } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig } from '../modules/snmpModuleRegistry'
import { useLiveSNMPPoll, useMonitoringData, useModuleData } from '../modules/useSNMPModules'

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

  const { data: livePoll, isFetching: liveLoading, error: liveError } = useLiveSNMPPoll(id)
  const { data: monitoringData } = useMonitoringData(id)
  const { data: directData, isLoading: directLoading, error: directError } = useModuleData(id, config ? moduleName : null)

  const liveCollector = livePoll?.collectors?.[moduleName]
  const dbModule = monitoringData?.modules?.[moduleName]
  const directCollector = directData
    ? {
        collector: moduleName,
        supported: (directData as any)?.supported ?? true,
        timestamp: (directData as any)?.timestamp,
        data: (directData as any)?.data ?? directData,
        reason: (directData as any)?.reason,
        missing: (directData as any)?.missing,
        warnings: (directData as any)?.warnings,
      }
    : null
  const dbCollector = dbModule
    ? {
        collector: moduleName,
        supported: dbModule.supported === true,
        timestamp: monitoringData?.timestamp,
        data: dbModule.data,
        reason: dbModule.supported ? undefined : 'No latest data stored for this module yet.',
      }
    : null

  const collectors = [liveCollector, directCollector, dbCollector].filter(Boolean)
  const collector =
    collectors.find(c => c.supported === true && hasCollectorData(c)) ||
    collectors.find(hasCollectorData) ||
    collectors.find(c => c.supported === true) ||
    collectors[0]
  const supported = collector?.supported === true
  const title = titleize(config?.label || moduleName)

  return (
    <SNMPModuleShell
      module={moduleName}
      title={title}
      showMonitoringControls={Boolean(config)}
      unsupportedMessage={`${title} is not supported by this device.`}
      allowUnsupportedContent
    >
      {(liveLoading || directLoading || liveError || directError || livePoll?.collection_ms) && (
        <GlassCard className="p-3">
          <div className="flex flex-wrap items-center gap-3 font-mono text-xs">
            <span style={{ color: liveLoading || directLoading ? '#ffaa00' : liveError && directError ? '#ff3366' : '#00ff88' }}>
              {liveLoading || directLoading ? 'Loading SNMP data...' : liveError && directError ? 'SNMP data unavailable' : supported ? 'Data loaded' : 'Not supported'}
            </span>
            {livePoll?.collection_ms != null && <span style={{ color: '#8899bb' }}>{livePoll.collection_ms} ms</span>}
            {liveError && <span className="truncate" style={{ color: '#ffaa00' }}>Live: {liveError.message}</span>}
            {directError && <span className="truncate" style={{ color: '#ffaa00' }}>Module: {directError.message}</span>}
          </div>
        </GlassCard>
      )}

      {collector ? (
        <SNMPCollectorDataCard name={moduleName} collector={collector} />
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
