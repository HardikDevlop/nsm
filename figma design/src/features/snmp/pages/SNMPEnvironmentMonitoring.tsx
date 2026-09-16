import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { getModuleConfig } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { useDeviceCapabilities } from '../modules/useSNMPModules'
import { useLatestEnvironment } from '../hooks/useSnmpQueries'

const SENSOR_TYPE_CONFIG: Record<
  string,
  { label: string; icon: string; defaultUnit: string; color: string }
> = {
  temperature: {
    label: 'Temperature',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    defaultUnit: '°C',
    color: '#ff6644',
  },
  fan: {
    label: 'Fan',
    icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    defaultUnit: 'RPM',
    color: '#00d4ff',
  },
  voltage: {
    label: 'Voltage',
    icon: 'M13 10V3L4 14h7v7l9-11h-7z',
    defaultUnit: 'V',
    color: '#ffaa00',
  },
  power: {
    label: 'Power',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z',
    defaultUnit: 'W',
    color: '#7c3aed',
  },
  humidity: {
    label: 'Humidity',
    icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z',
    defaultUnit: '%',
    color: '#00bfff',
  },
  other: {
    label: 'Sensor',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z',
    defaultUnit: '',
    color: '#8899bb',
  },
}

const STATUS_COLORS = {
  ok: '#00ff88',
  warning: '#ffaa00',
  critical: '#ff3366',
  unknown: '#8899bb',
}

function fmtValue(value: number | undefined, unit: string | undefined, type: string): string {
  if (value === undefined || value === null) return '—'
  const u = unit || SENSOR_TYPE_CONFIG[type]?.defaultUnit || ''
  return `${value.toFixed(1)}${u}`
}

export default function SNMPEnvironmentMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)
  const moduleConfig = getModuleConfig('environment')!

  const { data: latestEnv, isLoading: environmentLoading, error: environmentError } = useLatestEnvironment(id)
  const { data: caps, isLoading: capabilitiesLoading, error: capabilitiesError } = useDeviceCapabilities(id)

  const sensors = Array.isArray(latestEnv) ? latestEnv : []
  const supported = caps?.environment === true || sensors.length > 0

  if (environmentLoading || capabilitiesLoading) {
    return (
      <SNMPModuleShell module="environment" title="Environment Monitoring" showMonitoringControls={false}>
        <GlassCard className="p-6 text-center font-mono text-xs" style={{ color: '#00d4ff' }}>Loading environment data...</GlassCard>
      </SNMPModuleShell>
    )
  }

  if (environmentError || capabilitiesError) {
    return (
      <SNMPModuleShell module="environment" title="Environment Monitoring" showMonitoringControls={false}>
        <GlassCard className="p-6 text-center font-mono text-xs" style={{ color: '#ff6b8a' }}>Unable to load environment data.</GlassCard>
      </SNMPModuleShell>
    )
  }

  if (!supported) {
    return (
      <SNMPModuleShell module="environment" title="Environment Monitoring" unsupportedMessage="Environment monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const presentTypes = Array.from(new Set(sensors.map(s => s.sensor_type)))
  const criticalCount = sensors.filter(s => s.status === 'critical').length
  const warningCount = sensors.filter(s => s.status === 'warning').length

  const sensorGroups = presentTypes.reduce<Record<string, any[]>>((acc, type) => {
    acc[type] = sensors.filter(s => s.sensor_type === type)
    return acc
  }, {})
  return (
    <SNMPModuleShell module="environment" title="Environment Monitoring" showMonitoringControls={true}>
      {/* Summary tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00d4ff' }}>{sensors.length}</div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Total Sensors</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#00ff88' }}>
            {sensors.filter(s => s.status === 'ok').length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>OK</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: warningCount > 0 ? '#ffaa00' : '#8899bb' }}>
            {warningCount}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Warning</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: criticalCount > 0 ? '#ff3366' : '#8899bb' }}>
            {criticalCount}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Critical</div>
        </GlassCard>
        <GlassCard className="p-4 text-center">
          <div className="font-display font-bold text-2xl" style={{ color: '#7c3aed' }}>
            {presentTypes.length}
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Sensor Types</div>
        </GlassCard>
      </div>

      {/* Sensor Cards — grouped by type */}
      {presentTypes.map(type => {
        const group = sensorGroups[type] ?? []
        const cfg = SENSOR_TYPE_CONFIG[type] || SENSOR_TYPE_CONFIG.other
        return (
          <div key={type}>
            <div className="flex items-center gap-2 mb-3">
              <div
                className="w-6 h-6 rounded flex items-center justify-center"
                style={{ background: `${cfg.color}18` }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="1.8">
                  <path d={cfg.icon} />
                </svg>
              </div>
              <span className="font-display font-bold text-sm tracking-wider" style={{ color: cfg.color }}>
                {cfg.label.toUpperCase()} ({group.length})
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mb-6">
              {group.map(s => (
                <GlassCard
                  key={s.sensor_id}
                  className="p-4 cursor-pointer transition-all hover:bg-cyan-400/5"
                  role="button"
                  tabIndex={0}
                >
                  <div className="flex items-start gap-3 mb-3">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                      style={{ background: `${cfg.color}18`, border: `1px solid ${cfg.color}40` }}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="1.8">
                        <path d={cfg.icon} />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-xs font-bold truncate" style={{ color: '#c8d8ee' }}>
                        {s.sensor_name}
                      </div>
                      <div className="font-mono text-[10px]" style={{ color: '#667799' }}>{cfg.label}</div>
                    </div>
                    <div
                      className="w-2.5 h-2.5 rounded-full shrink-0 mt-1"
                      style={{ background: STATUS_COLORS[s.status as keyof typeof STATUS_COLORS] || '#8899bb', boxShadow: `0 0 6px ${STATUS_COLORS[s.status as keyof typeof STATUS_COLORS] || '#8899bb'}` }}
                      title={`Status: ${s.status}`}
                    />
                  </div>

                  <div className="mb-3">
                    <div className="font-display font-bold text-2xl" style={{ color: cfg.color }}>
                      {fmtValue(s.current_value, s.unit, s.sensor_type)}
                    </div>
                    <SNMPStatusBadge status={s.status} size="xs" />
                  </div>

                  {(s.threshold_warning !== undefined || s.threshold_critical !== undefined) && (
                    <div className="flex gap-4 mb-3">
                      {s.threshold_warning !== undefined && (
                        <div>
                          <div className="font-mono text-[9px]" style={{ color: '#556677' }}>Warn</div>
                          <div className="font-mono text-xs" style={{ color: '#ffaa00' }}>
                            {s.threshold_warning}{s.unit || cfg.defaultUnit}
                          </div>
                        </div>
                      )}
                      {s.threshold_critical !== undefined && (
                        <div>
                          <div className="font-mono text-[9px]" style={{ color: '#556677' }}>Crit</div>
                          <div className="font-mono text-xs" style={{ color: '#ff3366' }}>
                            {s.threshold_critical}{s.unit || cfg.defaultUnit}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Mini sparkline */}
                  {s.history && s.history.length >= 2 && (
                    <SNMPMetricChart
                      data={s.history.slice(-8).map(p => ({ timestamp: p.timestamp, value: p.value }))}
                      height={40}
                      color={cfg.color}
                      showArea={false}
                      showGrid={false}
                      showAxes={false}
                      noDataMessage=""
                    />
                  )}

                  <div
                    className="flex items-center justify-between mt-3 pt-2"
                    style={{ borderTop: '1px solid rgba(0,212,255,0.06)' }}
                  >
                    <span className="font-mono text-[9px]" style={{ color: '#445566' }}>
                      {new Date(s.last_updated).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
                    </span>
                    <span className="font-mono text-[10px] flex items-center gap-1" style={{ color: '#00d4ff' }}>
                      History
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                    </span>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>
        )
      })}

      <SNMPCollectorDataCard name="environment" collector={environmentCollector} />
    </SNMPModuleShell>
  )
}
