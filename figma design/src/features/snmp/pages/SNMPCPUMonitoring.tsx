import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig, getHealthColor } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { useDeviceCapabilities, useMonitoringData } from '../modules/useSNMPModules'
import { useLatestCPU } from '../hooks/useSnmpQueries'

function normalizePerCore(value: any): Array<{ id: string; percent: number }> {
  if (!value) return []
  if (Array.isArray(value)) {
    return value
      .map((core, index) => ({
        id: String(core?.index ?? core?.core ?? index),
        percent: Number(core?.percent ?? core?.usage ?? core),
      }))
      .filter(core => Number.isFinite(core.percent))
  }
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([id, percent]) => ({ id, percent: Number((percent as any)?.percent ?? (percent as any)?.usage ?? percent) }))
      .filter(core => Number.isFinite(core.percent))
  }
  return []
}

export default function SNMPCPUMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('cpu')!

  const { data: caps } = useDeviceCapabilities(id)
  const { data: latestCPU } = useLatestCPU(id)
  const { data: monitoringData, isLoading: monitoringLoading, error: monitoringError } = useMonitoringData(id)
  
  const cpuModuleData = monitoringData?.modules?.cpu
  const stats = cpuModuleData as any
  const history = stats?.history || []
  const cpuData = stats?.data || latestCPU || {}
  const currentUsage = cpuData?.overall_percent ?? cpuData?.utilization_percent ?? latestCPU?.current_usage ?? stats?.overall_percent
  const perCore = normalizePerCore(cpuData?.per_core ?? latestCPU?.per_core)
  const historyValues = history
    .map((point: any) => Number(point?.usage ?? point?.value))
    .filter((value: number) => Number.isFinite(value))
  const averageUsage = cpuData?.average_percent != null
    ? Number(cpuData.average_percent)
    : historyValues.length > 0
      ? historyValues.reduce((sum: number, value: number) => sum + value, 0) / historyValues.length
      : currentUsage
  const hasCpuData = Object.keys(cpuData || {}).length > 0 || perCore.length > 0 || currentUsage !== undefined
  const supported =
    monitoringData?.capabilities?.cpu === true ||
    caps?.cpu === true ||
    cpuModuleData?.supported === true ||
    hasCpuData

  if (!supported) {
    return (
      <SNMPModuleShell module="cpu" title="CPU Monitoring" unsupportedMessage="CPU monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const health = currentUsage !== undefined && currentUsage >= 90 ? 'critical' : currentUsage !== undefined && currentUsage >= 70 ? 'warning' : 'healthy'
  const cpuCollector = {
    collector: 'cpu',
    supported: true,
    timestamp: cpuModuleData?.timestamp || cpuData?.polled_at,
    data: cpuData,
    missing: cpuModuleData?.missing || [],
    warnings: cpuModuleData?.warnings || [],
  }

  return (
    <SNMPModuleShell module="cpu" title="CPU Monitoring" showMonitoringControls={true}>
      {/* Health + Poll Info */}
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <div
          className="w-3 h-3 rounded-full"
          style={{ background: getHealthColor(health), boxShadow: `0 0 8px ${getHealthColor(health)}` }}
          title={`Health: ${health}`}
        />
        <span className="font-mono text-xs" style={{ color: 'var(--t-text)' }}>Health: {health.toUpperCase()}</span>
        {cpuData?.polled_at && (
            <span className="font-mono text-xs" style={{ color: 'var(--t-text)' }}>
            Last Poll: {new Date(cpuData.polled_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
          </span>
        )}
        {cpuData?.display && (
          <span className="font-mono text-xs" style={{ color: '#00d4ff' }}>
            Display: {cpuData.display}
          </span>
        )}
      </div>

      {/* Main Chart */}
      <GlassCard className="p-4 mb-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-display font-bold text-sm tracking-wider" style={{ color: 'var(--t-text)' }}>CPU UTILIZATION</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-text)' }}>
              {history.length} data points
            </div>
          </div>
          <div className="font-mono text-xs px-2 py-1 rounded" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
            {currentUsage?.toFixed(1)}%
          </div>
        </div>
        {history.length < 2 ? (
          <div className="cpu-live-summary rounded-lg p-5 flex flex-col md:flex-row items-center gap-6">
            <div className="cpu-main-gauge" style={{ background: `conic-gradient(#00d4ff ${Math.max(0, Math.min(100, currentUsage ?? 0)) * 3.6}deg, #dbeafe 0deg)` }}>
              <div><strong>{currentUsage?.toFixed(1) ?? '—'}%</strong><span>CURRENT</span></div>
            </div>
            <div className="flex-1 w-full grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[['STATUS', health.toUpperCase()], ['CORES', String(cpuData?.core_count ?? (perCore.length || '—'))], ['AVERAGE', averageUsage != null && Number.isFinite(Number(averageUsage)) ? `${Number(averageUsage).toFixed(1)}%` : '—'], ['HISTORY', 'COLLECTING']].map(([label, value]) => (
                <div key={label} className="cpu-summary-stat"><span>{label}</span><strong>{value}</strong></div>
              ))}
            </div>
          </div>
        ) : <SNMPMetricChart
          data={history.map(p => ({ timestamp: p.timestamp, value: p.usage }))}
          height={200} color="#00d4ff" unit="%" label="CPU %" showArea showGrid showAxes noDataMessage="No Historical Data Yet"
        />}
      </GlassCard>

      {/* Per Core */}
      {perCore.length > 0 && (
        <GlassCard className="p-4 mb-4">
          <div className="font-display font-bold text-sm tracking-wider mb-4" style={{ color: 'var(--t-text)' }}>PER CORE USAGE</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            {perCore.map(core => {
                  const pct = core.percent
                  const coreColor = pct >= 90 ? '#ff3366' : pct >= 70 ? '#ffaa00' : '#00ff88'
                  return (
                    <div key={core.id} className="per-core-usage-tile text-center rounded-xl border p-3">
                      <div className="cpu-core-gauge mx-auto" style={{ background: `conic-gradient(${coreColor} ${Math.max(0, Math.min(100, pct)) * 3.6}deg, #dbeafe 0deg)` }}>
                        <div className="cpu-core-gauge-inner">
                          <span style={{ color: coreColor }}>{pct.toFixed(0)}%</span>
                        </div>
                      </div>
                      <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--t-text)' }}>
                        Core {core.id}
                      </div>
                    </div>
                  )
            })}
          </div>
        </GlassCard>
      )}

      <SNMPCollectorDataCard name="cpu" collector={cpuCollector} />

      {/* History Table */}
      {history.length > 0 && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-display font-bold text-sm tracking-wider" style={{ color: 'var(--t-text)' }}>POLL HISTORY</div>
          </div>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                  {['Timestamp', 'CPU Usage', 'Health'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                      style={{ color: 'var(--t-text)', background: 'var(--t-table-header)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().map((row, i) => {
                  const h = row.usage >= 90 ? 'critical' : row.usage >= 70 ? 'warning' : 'healthy'
                  const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--t-text)' }}>
                        {new Date(row.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#00d4ff' }}>
                        {row.usage.toFixed(1)}%
                      </td>
                      <td className="px-4 py-2">
                        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded uppercase"
                          style={{ color: hColors[h], background: `${hColors[h]}15` }}>
                          {h}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}
    </SNMPModuleShell>
  )
}
